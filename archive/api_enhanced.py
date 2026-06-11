# api_enhanced.py — TRANC3 Enhanced FastAPI application
# Exposes: MCP RPC, Workflow, DeepMind Planning, Health, Skills, Code Gen
#
# DEPRECATED — do not extend this file.
# All unique routes (code/*, skills/*, plan, reason, healing/*) have been
# migrated to src/routers/enhanced_capabilities.py and are now included in
# the canonical entry point api.py. This file is kept only to avoid breaking
# tests/test_enhanced_api.py until those tests are migrated. New development
# must go directly to api.py and its router tree.

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from Dimensional.error_handlers import safe_error_detail

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tranc3.api")

# ─── Environment Config ────────────────────────────────────────────────────────

_ENV = os.getenv("ENVIRONMENT", "development")
_DEBUG = os.getenv("DEBUG", "false").lower() == "true"
_API_KEY = os.getenv("TRANC3_API_KEY", "")  # set in production
_JWT_SECRET = os.getenv("JWT_SECRET", "")  # must be set in production
_REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

# Comma-separated list of allowed origins; "*" only for dev
_RAW_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*" if _ENV != "production" else "")
_ALLOWED_ORIGINS: List[str] = (
    ["*"] if _RAW_ORIGINS == "*" else [o.strip() for o in _RAW_ORIGINS.split(",") if o.strip()]
)
if _ENV == "production" and not _ALLOWED_ORIGINS:
    raise RuntimeError("ALLOWED_ORIGINS must be set in production. Got empty string.")


# ─── Auth ─────────────────────────────────────────────────────────────────────

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


def _verify_api_key(key: Optional[str]) -> bool:
    if not _API_KEY:
        return True  # not configured → skip (dev mode)
    return key == _API_KEY


def _verify_jwt(token: str) -> Optional[Dict]:
    if not _JWT_SECRET:
        return {"sub": "anonymous"}
    try:
        from jose import jwt as jose_jwt

        return jose_jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None


async def require_auth(
    api_key: Optional[str] = Security(_api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> Dict:
    """Dependency: allow if API key valid OR bearer JWT valid (or auth disabled)."""
    if not _REQUIRE_AUTH:
        return {"sub": "anonymous", "auth": "disabled"}

    if api_key and _verify_api_key(api_key):
        return {"sub": "api_key", "auth": "api_key"}

    if bearer:
        payload = _verify_jwt(bearer.credentials)
        if payload:
            return payload

    raise HTTPException(status_code=401, detail="Authentication required")


# ─── Rate Limiting (in-memory, per-IP sliding window) ─────────────────────────

_rate_store: Dict[str, List[float]] = {}
_RATE_WINDOW = int(os.getenv("RATE_WINDOW_SECONDS", "60"))
_RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_WINDOW", "120"))  # requests per window


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    return (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else "unknown")
    )


async def rate_limit(request: Request) -> None:
    """Dependency: enforce sliding-window rate limit per client IP."""
    ip = _client_ip(request)
    now = time.monotonic()
    window_start = now - _RATE_WINDOW
    hits = [t for t in _rate_store.get(ip, []) if t > window_start]
    hits.append(now)
    _rate_store[ip] = hits
    if len(hits) > _RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {_RATE_LIMIT} requests per {_RATE_WINDOW}s",
            headers={"Retry-After": str(_RATE_WINDOW)},
        )


# Composite dependency: auth + rate limit
async def protected(
    auth: Dict = Depends(require_auth),
    _rl: None = Depends(rate_limit),
) -> Dict:
    return auth


# ─── Request / Response Models ─────────────────────────────────────────────────


class ThinkRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8192)
    context: Dict[str, Any] = {}
    personality: Optional[str] = None


class WorkflowRequest(BaseModel):
    workflow: Dict[str, Any]
    inputs: Dict[str, Any] = {}


class MCPToolRequest(BaseModel):
    tool: str = Field(..., min_length=1, max_length=128)
    params: Dict[str, Any] = {}


class SkillSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    top_k: int = Field(default=10, ge=1, le=50)
    category: Optional[str] = None


class CodeGenRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=2048)
    language: str = Field(default="python", pattern=r"^[a-zA-Z0-9_+#-]{1,32}$")
    context: str = Field(default="", max_length=4096)
    constraints: List[str] = Field(default=[], max_length=20)


class CodeImproveRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=32768)
    feedback: str = Field(default="", max_length=2048)
    language: str = Field(default="python", pattern=r"^[a-zA-Z0-9_+#-]{1,32}$")


class PlanRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=2048)
    state: Dict[str, Any] = {}
    constraints: List[str] = Field(default=[], max_length=20)


class FeedbackRequest(BaseModel):
    quality_score: float = Field(..., ge=0.0, le=1.0)
    user_satisfaction: float = Field(..., ge=0.0, le=1.0)
    session_id: str = Field(default="default", max_length=128)


class PersonalityRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


class SpawnRequest(BaseModel):
    personality_id: str = Field(..., min_length=1, max_length=64)
    repo_name: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    output_dir: str = Field(default="./spawned", max_length=256)


# ─── Application Lifespan ──────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.core.startup_validator import validate_startup

    validate_startup()
    from src.main_enhanced import enhanced

    await enhanced.initialize()
    await enhanced.start_background_services()
    enhanced.print_banner()
    app.state.enhanced = enhanced
    yield
    logger.info("TRANC3 Enhanced shutting down")


# ─── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="TRANC3 Enhanced API",
    description="MCP + Workflow + DeepMind + Self-Healing + Enhanced Skills",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _ENV != "production" else None,  # hide Swagger in prod
    redoc_url="/redoc" if _ENV != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "X-API-Key", "Content-Type"],
)


# ─── Public Endpoints (no auth) ────────────────────────────────────────────────


@app.get("/", tags=["core"])
async def root():
    return {
        "system": "TRANC3 Enhanced",
        "version": "3.0.0",
        "status": "operational",
        "timestamp": time.time(),
    }


@app.get("/health", tags=["core"])
async def health(request: Request):
    """Public health check — safe to expose without auth."""
    enhanced = request.app.state.enhanced
    return await enhanced.get_system_health()


# ─── Protected Core ────────────────────────────────────────────────────────────


@app.post("/think", tags=["core"], dependencies=[Depends(protected)])
async def think(req: ThinkRequest, request: Request):
    enhanced = request.app.state.enhanced
    result = await enhanced.think(req.prompt, req.context)
    if req.personality:
        try:
            from src.personality.matrix import EnhancedPersonalityMatrix

            matrix = EnhancedPersonalityMatrix({})
            vec = matrix.get_personality_vector(req.personality)
            result["personality_vector"] = vec.tolist()
            result["personality"] = req.personality
        except Exception as _exc:
            logger.debug("suppressed %s", _exc, exc_info=False)
    return result


# ─── MCP ───────────────────────────────────────────────────────────────────────


@app.post("/mcp/tool", tags=["mcp"], dependencies=[Depends(protected)])
async def call_mcp_tool(req: MCPToolRequest, request: Request):
    enhanced = request.app.state.enhanced
    result = await enhanced.call_mcp_tool(req.tool, req.params)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/mcp/tools", tags=["mcp"])
async def list_mcp_tools():
    try:
        from src.mcp.tools import registry

        return {"tools": registry.list_tools()}
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


@app.post("/mcp/rpc", tags=["mcp"], dependencies=[Depends(protected)])
async def mcp_rpc(body: Dict[str, Any], request: Request):
    """JSON-RPC 2.0 endpoint for MCP clients."""
    try:
        from src.mcp.server import handle_rpc

        return await handle_rpc(body, request.app.state.enhanced)
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32603, "message": safe_error_detail(e, 500)},
        }


@app.get("/mcp/sse", tags=["mcp"])
async def mcp_sse(request: Request):
    """SSE stream — public so MCP clients can subscribe without auth overhead."""

    async def event_stream():
        yield f"data: {json.dumps({'type': 'connected', 'server': 'tranc3-mcp'})}\n\n"
        try:
            from src.workflow.executor import event_bus

            queue: asyncio.Queue = asyncio.Queue(maxsize=128)

            async def cb(data: Any):
                try:
                    queue.put_nowait(data)
                except asyncio.QueueFull as _exc:
                    logger.debug("suppressed %s", _exc, exc_info=False)

            event_bus.subscribe("*", cb)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping', 'ts': time.time()})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': safe_error_detail(e, 500)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Workflow ──────────────────────────────────────────────────────────────────


@app.post("/workflow/execute", tags=["workflow"], dependencies=[Depends(protected)])
async def execute_workflow(req: WorkflowRequest, request: Request):
    enhanced = request.app.state.enhanced
    result = await enhanced.execute_workflow(req.workflow, req.inputs)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.get("/workflow/templates", tags=["workflow"])
async def workflow_templates():
    """Public — returns built-in workflow templates."""
    try:
        from src.workflow.builder import (
            ml_training_workflow,
            self_healing_workflow,
            spark_ignition_workflow,
        )

        return {
            "templates": [
                spark_ignition_workflow().to_dict(),
                self_healing_workflow().to_dict(),
                ml_training_workflow().to_dict(),
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


@app.get("/workflow/status/{execution_id}", tags=["workflow"], dependencies=[Depends(protected)])
async def workflow_status(execution_id: str, request: Request):
    try:
        from src.workflow.executor import executor

        state = await executor.get_status(execution_id)
        if not state:
            raise HTTPException(status_code=404, detail="Execution not found")
        return {
            "execution_id": state.execution_id,
            "status": state.status,
            "node_statuses": state.node_statuses,
            "error": state.error,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=safe_error_detail(e, 500))


# ─── Planning / DeepMind ────────────────────────────────────────────────────────


@app.post("/plan", tags=["deepmind"], dependencies=[Depends(protected)])
async def plan(req: PlanRequest):
    try:
        from src.deepmind.planning import planner

        result = await planner.plan_action(req.goal, req.state, req.constraints)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


@app.post("/reason", tags=["deepmind"], dependencies=[Depends(protected)])
async def chain_of_thought(req: PlanRequest):
    try:
        from src.deepmind.planning import ChainOfThoughtReasoner

        reasoner = ChainOfThoughtReasoner()
        result = await reasoner.reason(req.goal)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


# ─── Skills ────────────────────────────────────────────────────────────────────


@app.post("/skills/search", tags=["skills"])
async def search_skills(req: SkillSearchRequest):
    try:
        from src.skills.enhanced_registry import registry

        results = await registry.search(req.query, top_k=req.top_k, category=req.category)
        return {
            "results": [
                {
                    "skill": r.skill.to_dict(),
                    "score": r.score,
                    "match_reason": r.match_reason,
                }
                for r in results
            ],
            "total": len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


@app.get("/skills/stats", tags=["skills"])
async def skill_stats():
    try:
        from src.skills.enhanced_registry import registry

        return registry.get_stats()
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


@app.post("/skills/detect-bundle", tags=["skills"])
async def detect_bundle(req: ThinkRequest):
    try:
        from src.skills.enhanced_registry import registry

        bundle = await registry.detect_and_load_bundle(req.prompt)
        if bundle:
            return {"bundle": bundle.id, "name": bundle.name, "skills": bundle.skills}
        return {"bundle": None}
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


# ─── Code Generation ───────────────────────────────────────────────────────────


@app.post("/code/generate", tags=["code"], dependencies=[Depends(protected)])
async def generate_code(req: CodeGenRequest):
    try:
        from src.skills.code_generator import CodeGenerationRequest, code_generator

        request = CodeGenerationRequest(
            language=req.language,
            description=req.description,
            context=req.context,
            constraints=req.constraints,
        )
        result = await code_generator.generate(request)
        return {
            "code": result.code,
            "tests": result.tests,
            "explanation": result.explanation,
            "quality_score": result.quality_score,
            "issues": result.issues,
            "improvements": result.improvements,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


@app.post("/code/improve", tags=["code"], dependencies=[Depends(protected)])
async def improve_code(req: CodeImproveRequest):
    try:
        from src.skills.code_generator import code_generator

        result = await code_generator.improver.improve(req.code, req.feedback, req.language)
        return {
            "code": result.code,
            "explanation": result.explanation,
            "quality_score": result.quality_score,
            "improvements": result.improvements,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


@app.post("/code/explain", tags=["code"])
async def explain_code(req: CodeImproveRequest):
    try:
        from src.skills.code_generator import code_generator

        explanation = await code_generator.explain_code(req.code)
        return {"explanation": explanation}
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


# ─── Self-Healing ──────────────────────────────────────────────────────────────


@app.get("/healing/dashboard", tags=["healing"])
async def healing_dashboard(request: Request):
    """Public health dashboard — intended for monitoring tools."""
    enhanced = request.app.state.enhanced
    return await enhanced.get_system_health()


@app.post("/healing/repair", tags=["healing"], dependencies=[Depends(protected)])
async def trigger_repair(request: Request):
    try:
        from src.healing.self_repair import repair_engine

        context = {"triggered_by": "api", "timestamp": time.time()}
        results = await repair_engine.evaluate_and_repair(context)
        return {"repairs_applied": results}
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


@app.get("/healing/bots", tags=["healing"])
async def bot_stats():
    try:
        from src.healing.nanocode_bots import dispatcher

        return dispatcher.get_bot_stats()
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


# ─── Evolution ─────────────────────────────────────────────────────────────────


@app.get("/evolution/stats", tags=["evolution"])
async def evolution_stats(request: Request):
    enhanced = request.app.state.enhanced
    evolution = enhanced._subsystems.get("evolution")
    if not evolution:
        raise HTTPException(status_code=503, detail="Evolution engine not initialized")
    return evolution.get_stats()


@app.post("/evolution/feedback", tags=["evolution"], dependencies=[Depends(protected)])
async def record_feedback(req: FeedbackRequest, request: Request):
    enhanced = request.app.state.enhanced
    evolution = enhanced._subsystems.get("evolution")
    if not evolution:
        raise HTTPException(status_code=503, detail="Evolution engine not initialized")
    evolution.record_feedback(
        {
            "quality_score": req.quality_score,
            "user_satisfaction": req.user_satisfaction,
            "session_id": req.session_id,
        }
    )
    return {"recorded": True}


# ─── Personality ───────────────────────────────────────────────────────────────


@app.get("/personality/list", tags=["personality"])
async def list_personalities():
    try:
        from src.personality.matrix import EnhancedPersonalityMatrix

        matrix = EnhancedPersonalityMatrix({})
        return {"personalities": matrix.list_personalities()}
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


@app.post("/personality/vector", tags=["personality"])
async def get_personality_vector(req: PersonalityRequest):
    try:
        from src.personality.matrix import EnhancedPersonalityMatrix

        matrix = EnhancedPersonalityMatrix({})
        vec = matrix.get_personality_vector(req.name)
        return {
            "personality": req.name,
            "vector": vec.tolist(),
            "description": matrix.get_personality_description(req.name),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


@app.post("/personality/spawn", tags=["personality"], dependencies=[Depends(protected)])
async def spawn_personality(req: SpawnRequest):
    """Generate a new Tranc3 repo scaffold with a specific personality."""
    try:
        from src.personality.spawner import PersonalitySpawner

        spawner = PersonalitySpawner()
        result = spawner.spawn(req.personality_id, req.repo_name, req.output_dir)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=safe_error_detail(e, 503))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api_enhanced:app", host="0.0.0.0", port=port, reload=_DEBUG)  # nosec B104 — Docker container binding
