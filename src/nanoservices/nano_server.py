# src/nanoservices/nano_server.py
# TRANC3 Nanoservice HTTP Server — serves all nanoservice endpoints over HTTP.
#
# This turns NanoServiceRegistry from a stub into a real API surface.
# Every endpoint is backed by the WorkerPool / BotRegistry.
#
# Run standalone:
#   python -m src.nanoservices.nano_server            # port 8001
#   NANO_PORT=8002 python -m src.nanoservices.nano_server
#
# Or mount as a sub-application inside the main FastAPI app:
#   from src.nanoservices.nano_server import nano_app
#   app.mount("/nano", nano_app)

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.nanoservices.nano_registry import NanoServiceRegistry
from src.workers.bot_registry import BotRegistry, get_registry

logger = logging.getLogger(__name__)

_NANO_PORT = int(os.getenv("NANO_PORT", "8001"))
_BOTS_URL = os.getenv("TRANC3_BOTS_URL", "")  # e.g. https://tranc3-bots.fly.dev
_CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173,https://trancendos.com,https://www.trancendos.com",
    ),
).split(",")


# ─── Pydantic request models ──────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    prompt: str
    personality: str = "tranc3-base"
    system_prompt: Optional[str] = None
    max_tokens: int = Field(256, ge=1, le=4096)
    temperature: float = Field(0.8, ge=0.0, le=2.0)
    top_p: float = Field(0.9, ge=0.0, le=1.0)


class EmbedRequest(BaseModel):
    text: str
    pooling: str = "mean"
    dims: int = Field(256, ge=8, le=4096)


class EmotionRequest(BaseModel):
    text: str


class TokenizeRequest(BaseModel):
    action: str = "encode"  # "encode" | "decode"
    text: str = ""
    ids: List[int] = []
    skip_special: bool = True


class ConsciousnessRequest(BaseModel):
    text: str


class PersonalityRequest(BaseModel):
    profile: str = "tranc3-base"
    dim: int = Field(128, ge=8, le=2048)


class PredictRequest(BaseModel):
    text: str
    top_k: int = Field(5, ge=1, le=100)
    predict_type: str = "next_token"


# ─── App factory ─────────────────────────────────────────────────────────────

_registry: Optional[BotRegistry] = None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _registry
    _registry = get_registry()
    await _registry.start()
    logger.info(
        "Nanoservice server ready — bots: %s",
        [b["name"] for b in _registry.list_bots()],
    )
    yield
    await _registry.stop()
    logger.info("Nanoservice server shutdown")


nano_app = FastAPI(
    title="TRANC3 Nanoservices",
    version="1.0.0",
    description="Self-owned TRANC3 inference nanoservices. No external AI APIs.",
    lifespan=_lifespan,
)

nano_app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _run(bot_name: str, **kwargs) -> dict:
    # If TRANC3_BOTS_URL is configured, proxy to the standalone bots service first.
    if _BOTS_URL:
        try:
            import httpx

            url = _BOTS_URL.rstrip("/") + "/" + bot_name
            async with httpx.AsyncClient(timeout=60.0) as http:
                r = await http.post(url, json=kwargs)
                if r.status_code < 500:
                    return r.json()
        except Exception as exc:
            logger.warning("Bots proxy to %s failed (%s) — falling back to local", bot_name, exc)

    if _registry is None:
        raise HTTPException(503, detail="Worker registry not initialised")
    result = await _registry.run(bot_name, **kwargs)
    if "error" in result and "status" in result:
        raise HTTPException(500, detail=result["error"])
    return result


# ─── Health ───────────────────────────────────────────────────────────────────


@nano_app.get("/health")
async def health():
    if _registry:
        return await _registry.health()
    return {"status": "initialising"}


@nano_app.get("/services")
async def list_services():
    reg = NanoServiceRegistry()
    return {"services": reg.list_all()}


# ─── /nano/generate ───────────────────────────────────────────────────────────


@nano_app.post("/generate")
async def generate(req: GenerateRequest):
    """Text generation / chat."""
    t0 = time.monotonic()
    out = await _run(
        "generate",
        prompt=req.prompt,
        personality=req.personality,
        system_prompt=req.system_prompt,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        top_p=req.top_p,
    )
    out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return out


@nano_app.get("/generate/health")
async def generate_health():
    return {"service": "generate", "status": "ok"}


# ─── /nano/embed ──────────────────────────────────────────────────────────────


@nano_app.post("/embed")
async def embed(req: EmbedRequest):
    """Vector embedding."""
    return await _run("embed", text=req.text, pooling=req.pooling, dims=req.dims)


@nano_app.get("/embed/health")
async def embed_health():
    return {"service": "embed", "status": "ok"}


# ─── /nano/emotion ────────────────────────────────────────────────────────────


@nano_app.post("/emotion")
async def emotion(req: EmotionRequest):
    """Emotion detection."""
    return await _run("emotion", text=req.text)


@nano_app.get("/emotion/health")
async def emotion_health():
    return {"service": "emotion", "status": "ok"}


# ─── /nano/tokenize ───────────────────────────────────────────────────────────


@nano_app.post("/tokenize")
async def tokenize(req: TokenizeRequest):
    """Tokenization / decoding."""
    return await _run(
        "tokenize",
        action=req.action,
        text=req.text,
        ids=req.ids,
        skip_special=req.skip_special,
    )


@nano_app.get("/tokenize/health")
async def tokenize_health():
    return {"service": "tokenize", "status": "ok"}


# ─── /nano/consciousness ──────────────────────────────────────────────────────


@nano_app.post("/consciousness")
async def consciousness(req: ConsciousnessRequest):
    """Consciousness / awareness scoring."""
    return await _run("consciousness", text=req.text)


@nano_app.get("/consciousness/health")
async def consciousness_health():
    return {"service": "consciousness", "status": "ok"}


# ─── /nano/personality ────────────────────────────────────────────────────────


@nano_app.post("/personality")
async def personality(req: PersonalityRequest):
    """Personality vector lookup."""
    return await _run("personality", profile=req.profile, dim=req.dim)


@nano_app.get("/personality/health")
async def personality_health():
    return {"service": "personality", "status": "ok"}


# ─── /nano/predict ────────────────────────────────────────────────────────────


@nano_app.post("/predict")
async def predict(req: PredictRequest):
    """Next-token / intent prediction."""
    return await _run(
        "predict",
        text=req.text,
        top_k=req.top_k,
        predict_type=req.predict_type,
    )


@nano_app.get("/predict/health")
async def predict_health():
    return {"service": "predict", "status": "ok"}


# ─── /nano/memory (stub — delegated to vector DB) ────────────────────────────


class MemoryRequest(BaseModel):
    action: str = "store"  # "store" | "recall" | "search"
    text: str = ""
    key: str = ""
    top_k: int = 5


@nano_app.post("/memory")
async def memory(req: MemoryRequest):
    """Vector memory store/recall (Qdrant-backed)."""
    try:
        from src.database.vector_store import VectorStore

        vs = VectorStore()
        if req.action == "store":
            embed = await _run("embed", text=req.text)
            doc_id = await vs.store(req.key or req.text[:50], embed["embedding"])
            return {"stored": True, "id": doc_id}
        elif req.action in ("recall", "search"):
            embed = await _run("embed", text=req.text)
            results = await vs.search(embed["embedding"], top_k=req.top_k)
            return {"results": results}
        else:
            raise HTTPException(400, detail=f"Unknown memory action: {req.action}")
    except ImportError:
        return {"error": "Vector store not configured", "action": req.action}
    return None


@nano_app.get("/memory/health")
async def memory_health():
    return {"service": "memory", "status": "ok"}


# ─── /nano/translate (lightweight LangDetect + generation-based) ──────────────


class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "en"
    source_lang: Optional[str] = None


@nano_app.post("/translate")
async def translate(req: TranslateRequest):
    """Translation via Tranc3 generation with language prompt."""
    detected = None
    if req.source_lang is None:
        try:
            from langdetect import detect

            detected = detect(req.text)
        except Exception:
            detected = "unknown"
    src = req.source_lang or detected or "unknown"
    prompt = (
        f"Translate the following text from {src} to {req.target_lang}. "
        f"Return only the translation, nothing else.\n\nText: {req.text}"
    )
    result = await _run("generate", prompt=prompt, temperature=0.3, max_tokens=256)
    return {
        "original": req.text,
        "translation": result.get("response", ""),
        "source_lang": src,
        "target_lang": req.target_lang,
    }


@nano_app.get("/translate/health")
async def translate_health():
    return {"service": "translate", "status": "ok"}


# ─── /nano/quantum (stub — routes to quantum module) ─────────────────────────


@nano_app.post("/quantum")
async def quantum(request: Request):
    body = await request.json()
    try:
        from src.quantum.quantum_engine import QuantumOptimizationEngine

        qo = QuantumOptimizationEngine()
        action = body.get("action", "rng")
        if action == "attention":
            qubits = body.get("qubits", 4)
            # Use quantum_attention_scores with dummy tensors for nano endpoint
            import torch

            dummy = torch.randn(1, 1, qubits, 8)
            result = qo.quantum_attention_scores(dummy, dummy)
            return {"attention": result.shape}
        elif action == "optimize":
            params = body.get("params", {})
            return {"result": "optimization_stubs_pending", "params": params}
        else:
            raise HTTPException(400, detail=f"Unknown quantum action: {action}")
    except ImportError:
        return {"error": "Quantum module not available", "action": body.get("action")}
    return None


@nano_app.get("/quantum/health")
async def quantum_health():
    return {"service": "quantum", "status": "ok"}


# ─── /nano/evolution ─────────────────────────────────────────────────────────


@nano_app.post("/evolution")
async def evolution(request: Request):
    body = await request.json()
    try:
        from src.evolution.model_evolution import ModelEvolution

        ev = ModelEvolution()
        action = body.get("action", "fitness")
        if action == "fitness":
            score = ev.evaluate_fitness()
            return {"fitness": score}
        elif action == "evolve":
            result = await ev.evolve_generation(body.get("population", 10))
            return {"result": result}
        else:
            raise HTTPException(400, detail=f"Unknown evolution action: {action}")
    except ImportError:
        return {"error": "Evolution module not available", "action": body.get("action")}
    return None


@nano_app.get("/evolution/health")
async def evolution_health():
    return {"service": "evolution", "status": "ok"}


# ─── Error handler ────────────────────────────────────────────────────────────


@nano_app.exception_handler(Exception)
async def _generic_error(request: Request, exc: Exception):
    logger.exception("Nanoservice error at %s: %s", request.url.path, exc)
    return JSONResponse(status_code=500, content={"error": str(exc), "path": str(request.url.path)})


# ─── Standalone entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    uvicorn.run(
        "src.nanoservices.nano_server:nano_app",
        host="0.0.0.0",  # nosec B104
        port=_NANO_PORT,
        reload=False,
        log_level="info",
    )
