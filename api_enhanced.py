# api_enhanced.py — TRANC3 Enhanced FastAPI application
# Exposes: MCP RPC, Workflow, DeepMind Planning, Health, Skills, Code Gen

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tranc3.api")


# ─── Request / Response Models ─────────────────────────────────────────────────

class ThinkRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = {}

class WorkflowRequest(BaseModel):
    workflow: Dict[str, Any]
    inputs: Dict[str, Any] = {}

class MCPToolRequest(BaseModel):
    tool: str
    params: Dict[str, Any] = {}

class SkillSearchRequest(BaseModel):
    query: str
    top_k: int = 10
    category: Optional[str] = None

class CodeGenRequest(BaseModel):
    description: str
    language: str = "python"
    context: str = ""
    constraints: List[str] = []

class CodeImproveRequest(BaseModel):
    code: str
    feedback: str = ""
    language: str = "python"

class PlanRequest(BaseModel):
    goal: str
    state: Dict[str, Any] = {}
    constraints: List[str] = []

class FeedbackRequest(BaseModel):
    quality_score: float
    user_satisfaction: float
    session_id: str = "default"


# ─── Application Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Core ──────────────────────────────────────────────────────────────────────

@app.get("/", tags=["core"])
async def root():
    return {
        "system": "TRANC3 Enhanced",
        "version": "3.0.0",
        "status": "operational",
        "timestamp": time.time(),
    }

@app.post("/think", tags=["core"])
async def think(req: ThinkRequest, request: Request):
    enhanced = request.app.state.enhanced
    result = await enhanced.think(req.prompt, req.context)
    return result

@app.get("/health", tags=["core"])
async def health(request: Request):
    enhanced = request.app.state.enhanced
    return await enhanced.get_system_health()


# ─── MCP ───────────────────────────────────────────────────────────────────────

@app.post("/mcp/tool", tags=["mcp"])
async def call_mcp_tool(req: MCPToolRequest, request: Request):
    enhanced = request.app.state.enhanced
    result = await enhanced.call_mcp_tool(req.tool, req.params)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@app.get("/mcp/tools", tags=["mcp"])
async def list_mcp_tools(request: Request):
    try:
        from src.mcp.tools import registry
        return {"tools": registry.list_tools()}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/mcp/rpc", tags=["mcp"])
async def mcp_rpc(body: Dict[str, Any], request: Request):
    """JSON-RPC 2.0 endpoint for MCP clients."""
    try:
        from src.mcp.server import handle_rpc
        return await handle_rpc(body, request.app.state.enhanced)
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32603, "message": str(e)},
        }

@app.get("/mcp/sse", tags=["mcp"])
async def mcp_sse(request: Request):
    """SSE stream for real-time MCP events."""
    async def event_stream():
        yield "data: {\"type\": \"connected\", \"server\": \"tranc3-mcp\"}\n\n"
        try:
            from src.workflow.executor import event_bus
            queue: asyncio.Queue = asyncio.Queue()

            async def cb(data):
                await queue.put(data)

            event_bus.subscribe("*", cb)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    import json
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"type\": \"ping\"}\n\n"
        except Exception as e:
            yield f"data: {{\"type\": \"error\", \"message\": \"{e}\"}}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ─── Workflow ──────────────────────────────────────────────────────────────────

@app.post("/workflow/execute", tags=["workflow"])
async def execute_workflow(req: WorkflowRequest, request: Request):
    enhanced = request.app.state.enhanced
    result = await enhanced.execute_workflow(req.workflow, req.inputs)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result

@app.get("/workflow/templates", tags=["workflow"])
async def workflow_templates():
    """Return pre-built workflow templates."""
    try:
        from src.workflow.builder import (
            spark_ignition_workflow,
            self_healing_workflow,
            ml_training_workflow,
        )
        return {
            "templates": [
                spark_ignition_workflow().to_dict(),
                self_healing_workflow().to_dict(),
                ml_training_workflow().to_dict(),
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/workflow/status/{execution_id}", tags=["workflow"])
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
        raise HTTPException(status_code=500, detail=str(e))


# ─── Planning / DeepMind ────────────────────────────────────────────────────────

@app.post("/plan", tags=["deepmind"])
async def plan(req: PlanRequest, request: Request):
    try:
        from src.deepmind.planning import planner
        result = await planner.plan_action(req.goal, req.state, req.constraints)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/reason", tags=["deepmind"])
async def chain_of_thought(req: PlanRequest):
    try:
        from src.deepmind.planning import ChainOfThoughtReasoner
        reasoner = ChainOfThoughtReasoner()
        result = await reasoner.reason(req.goal)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


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
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/skills/stats", tags=["skills"])
async def skill_stats():
    try:
        from src.skills.enhanced_registry import registry
        return registry.get_stats()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/skills/detect-bundle", tags=["skills"])
async def detect_bundle(req: ThinkRequest):
    try:
        from src.skills.enhanced_registry import registry
        bundle = await registry.detect_and_load_bundle(req.prompt)
        if bundle:
            return {"bundle": bundle.id, "name": bundle.name, "skills": bundle.skills}
        return {"bundle": None}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ─── Code Generation ───────────────────────────────────────────────────────────

@app.post("/code/generate", tags=["code"])
async def generate_code(req: CodeGenRequest):
    try:
        from src.skills.code_generator import code_generator, CodeGenerationRequest
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
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/code/improve", tags=["code"])
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
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/code/explain", tags=["code"])
async def explain_code(req: CodeImproveRequest):
    try:
        from src.skills.code_generator import code_generator
        explanation = await code_generator.explain_code(req.code)
        return {"explanation": explanation}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ─── Self-Healing ──────────────────────────────────────────────────────────────

@app.get("/healing/dashboard", tags=["healing"])
async def healing_dashboard(request: Request):
    enhanced = request.app.state.enhanced
    return await enhanced.get_system_health()

@app.post("/healing/repair", tags=["healing"])
async def trigger_repair(request: Request):
    try:
        from src.healing.self_repair import repair_engine
        context = {"triggered_by": "api", "timestamp": time.time()}
        results = await repair_engine.evaluate_and_repair(context)
        return {"repairs_applied": results}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/healing/bots", tags=["healing"])
async def bot_stats():
    try:
        from src.healing.nanocode_bots import dispatcher
        return dispatcher.get_bot_stats()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ─── Evolution ─────────────────────────────────────────────────────────────────

@app.get("/evolution/stats", tags=["evolution"])
async def evolution_stats(request: Request):
    enhanced = request.app.state.enhanced
    evolution = enhanced._subsystems.get("evolution")
    if not evolution:
        raise HTTPException(status_code=503, detail="Evolution engine not initialized")
    return evolution.get_stats()

@app.post("/evolution/feedback", tags=["evolution"])
async def record_feedback(req: FeedbackRequest, request: Request):
    enhanced = request.app.state.enhanced
    evolution = enhanced._subsystems.get("evolution")
    if not evolution:
        raise HTTPException(status_code=503, detail="Evolution engine not initialized")
    evolution.record_feedback({
        "quality_score": req.quality_score,
        "user_satisfaction": req.user_satisfaction,
        "session_id": req.session_id,
    })
    return {"recorded": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_enhanced:app", host="0.0.0.0", port=8000, reload=True)
