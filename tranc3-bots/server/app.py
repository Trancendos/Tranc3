# server/app.py — Tranc3 Bots HTTP server (FastAPI).
#
# Endpoints mirror each BotType so Tranc3 (or any client) can call bots over HTTP.
# Run: uvicorn server.app:app --host 0.0.0.0 --port 8080
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from bots.registry import BotRegistry, get_registry
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_registry: Optional[BotRegistry] = None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _registry
    _registry = get_registry()
    await _registry.start()
    logger.info("Bots service started")
    yield
    await _registry.stop()
    logger.info("Bots service stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tranc3 Bots",
        description="Self-owned worker bots for the Tranc3 AI system.",
        version="1.0.0",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _register_routes(app)
    return app


def _reg() -> BotRegistry:
    if _registry is None:
        raise HTTPException(503, "Bot registry not initialised")
    return _registry


# ── Request / response models ──────────────────────────────────────────────────


class GenericRequest(BaseModel):
    payload: Dict[str, Any] = {}


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 256
    temperature: float = 0.7
    personality: Optional[str] = None


class EmbedRequest(BaseModel):
    text: str
    dim: int = 128


class EmotionRequest(BaseModel):
    text: str


class TokenizeRequest(BaseModel):
    text: str


class ConsciousnessRequest(BaseModel):
    text: str


class PersonalityRequest(BaseModel):
    text: str


class PredictRequest(BaseModel):
    context: str
    steps: int = 1


class CodeRequest(BaseModel):
    task: str
    language: str = "python"


class MemoryRequest(BaseModel):
    action: str  # store | retrieve | list
    key: str = ""
    value: Any = None


class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    source: str = "local"


class SummariseRequest(BaseModel):
    text: str
    ratio: float = 0.3


# ── Route registration ─────────────────────────────────────────────────────────


def _register_routes(app: FastAPI):

    @app.get("/health")
    async def health():
        return await _reg().health()

    @app.post("/generate")
    async def generate(req: GenerateRequest):
        return await _reg().run("generate", timeout=60.0, **req.model_dump())

    @app.post("/embed")
    async def embed(req: EmbedRequest):
        return await _reg().run("embed", timeout=15.0, **req.model_dump())

    @app.post("/emotion")
    async def emotion(req: EmotionRequest):
        return await _reg().run("emotion", timeout=15.0, **req.model_dump())

    @app.post("/tokenize")
    async def tokenize(req: TokenizeRequest):
        return await _reg().run("tokenize", timeout=10.0, **req.model_dump())

    @app.post("/consciousness")
    async def consciousness(req: ConsciousnessRequest):
        return await _reg().run("consciousness", timeout=20.0, **req.model_dump())

    @app.post("/personality")
    async def personality(req: PersonalityRequest):
        return await _reg().run("personality", timeout=10.0, **req.model_dump())

    @app.post("/predict")
    async def predict(req: PredictRequest):
        return await _reg().run("predict", timeout=15.0, **req.model_dump())

    @app.post("/code")
    async def code(req: CodeRequest):
        return await _reg().run("code", timeout=30.0, **req.model_dump())

    @app.post("/memory")
    async def memory(req: MemoryRequest):
        return await _reg().run("memory", timeout=10.0, **req.model_dump())

    @app.get("/monitor")
    async def monitor():
        return await _reg().run("monitor", timeout=10.0)

    @app.post("/search")
    async def search(req: SearchRequest):
        return await _reg().run("search", timeout=15.0, **req.model_dump())

    @app.post("/summarise")
    async def summarise(req: SummariseRequest):
        return await _reg().run("summarise", timeout=30.0, **req.model_dump())

    # Generic passthrough — useful for future bot types
    @app.post("/run/{bot_type}")
    async def run_bot(bot_type: str, req: GenericRequest):
        try:
            return await _reg().run(bot_type, timeout=60.0, **req.payload)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from None
        except RuntimeError as exc:
            raise HTTPException(500, str(exc)) from None


app = create_app()
