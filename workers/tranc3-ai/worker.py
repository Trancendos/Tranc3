"""
Tranc3 AI Worker — Self-Hosted Python Replacement for Cloudflare Worker

Replaces: cloudflare/tranc3-ai/src/index.js
Runs as: FastAPI application on Fly.io or bare metal
Zero external AI service dependencies — self-owned inference.

Routes:
  GET  /                          → API info
  GET  /health                    → health check
  GET  /api/v1/ai/models          → list available models
  POST /api/v1/ai/chat            → chat / text generation
  POST /api/v1/ai/embeddings      → text embeddings
  POST /api/v1/ai/analyze-emotion → emotion detection
  POST /api/v1/ai/consciousness   → consciousness scoring
  POST /api/v1/ai/tokenize        → tokenization
  POST /api/v1/ai/predict         → next-token prediction

Inference strategy (priority — NO external AI APIs):
  1. TRANC3_BACKEND_URL → full Tranc3 Python backend (FastAPI + WorkerPool)
  2. TRANC3_NANO_URL    → Tranc3 nanoservices HTTP server (nano_server.py)
  3. Deterministic stub → honest "model not trained yet" response
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# ── Constants ──────────────────────────────────────────────────

TRANC3_MODELS: dict[str, dict[str, Any]] = {
    "tranc3-base": {
        "name": "Tranc3 Base",
        "backend": "tranc3-own",
        "capabilities": ["chat", "emotion", "consciousness"],
    },
    "tranc3-fast": {"name": "Tranc3 Fast", "backend": "tranc3-own", "capabilities": ["chat"]},
    "tranc3-embeddings": {
        "name": "Tranc3 Embeddings",
        "backend": "tranc3-own",
        "capabilities": ["embeddings"],
    },
    "dorris-fontaine": {
        "name": "Dorris Fontaine",
        "backend": "tranc3-own",
        "capabilities": ["chat", "finance"],
    },
    "cornelius-macintyre": {
        "name": "Cornelius MacIntyre",
        "backend": "tranc3-own",
        "capabilities": ["chat", "orchestration"],
    },
    "the-guardian": {
        "name": "The Guardian",
        "backend": "tranc3-own",
        "capabilities": ["chat", "security"],
    },
    "vesper-nightingale": {
        "name": "Vesper Nightingale",
        "backend": "tranc3-own",
        "capabilities": ["chat", "healthcare"],
    },
    "atlas-meridian": {
        "name": "Atlas Meridian",
        "backend": "tranc3-own",
        "capabilities": ["chat", "infrastructure"],
    },
}

BACKEND_URL = os.getenv("TRANC3_BACKEND_URL", "")
NANO_URL = os.getenv("TRANC3_NANO_URL", "")
AUTH_URL = os.getenv("TRANC3_AUTH_URL", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

ALLOWED_ORIGINS = [
    "https://trancendos.com",
    "https://www.trancendos.com",
    "https://infinity-portal.pages.dev",
    "https://infinity-portal.com",
    "http://localhost:5173",
    "http://localhost:3000",
]

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
}

# ── App ────────────────────────────────────────────────────────

app = FastAPI(
    title="Tranc3 AI Worker",
    version="2.0.0",
    description="Self-hosted AI inference — replaces Cloudflare Worker. Zero external dependencies.",
)

# OpenTelemetry instrumentation
try:
    from src.observability.worker_setup import instrument_worker

    instrument_worker(app, service_name="tranc3.tranc3-ai")
except Exception:
    pass  # OTel is optional — never block startup

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS
    + [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    max_age=86400,
)


# ── Backend call (self-owned) ──────────────────────────────────


async def call_nano(endpoint: str, payload: dict) -> dict | None:
    """Call self-owned backend or nanoservice — priority: backend → nano → None."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try full backend first
        if BACKEND_URL:
            try:
                resp = await client.post(
                    f"{BACKEND_URL}/nano/{endpoint}",
                    json=payload,
                    headers={"Content-Type": "application/json", "X-Tranc3-Edge": "self-hosted"},
                )
                if resp.status_code == 200:
                    return resp.json()
            except httpx.HTTPError:
                pass

        # Try dedicated nanoservices server
        if NANO_URL:
            try:
                resp = await client.post(
                    f"{NANO_URL}/{endpoint}",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    return resp.json()
            except httpx.HTTPError:
                pass

    return None


# ── Stub responses (no external AI — honest, useful) ───────────


def stub_chat(messages: list[dict], model: str = "tranc3-base") -> dict:
    last_msg = messages[-1].get("content", "") if messages else ""
    return {
        "id": str(uuid.uuid4()),
        "object": "chat.completion",
        "model": model,
        "backend": "tranc3-stub",
        "trained": False,
        "message": "TRANC3 model weights not yet trained. Run: python train.py",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": (
                        f"TRANC3 ({model}) is initialising. "
                        "Model weights are not yet trained. "
                        "Run `python train.py` on your Tranc3 backend to produce weights. "
                        f'Your message: "{last_msg[:80]}"'
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def stub_embedding(input_text: str | list[str]) -> dict:
    texts = [input_text] if isinstance(input_text, str) else input_text
    return {
        "object": "list",
        "model": "tranc3-embeddings",
        "backend": "tranc3-stub",
        "trained": False,
        "data": [
            {
                "object": "embedding",
                "index": i,
                "embedding": [0.0] * 256,  # Placeholder
            }
            for i in range(len(texts))
        ],
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


def stub_emotion(text: str) -> dict:
    t = text.lower()
    emotions = {
        "joy": bool(re.search(r"happy|great|excellent|wonderful|love|yay|amazing", t)),
        "sadness": bool(re.search(r"sad|unhappy|terrible|awful|cry|miss|depressed", t)),
        "anger": bool(re.search(r"angry|furious|hate|rage|frustrated|annoyed", t)),
        "fear": bool(re.search(r"scared|afraid|fear|worried|anxious|nervous", t)),
        "surprise": bool(re.search(r"wow|amazing|unexpected|shocked|unbelievable", t)),
        "disgust": bool(re.search(r"disgusting|horrible|gross|nasty|repulsive", t)),
    }
    scores = {k: 0.6 if v else 0.05 for k, v in emotions.items()}
    total = sum(scores.values()) or 1
    norm = {k: round(v / total, 4) for k, v in scores.items()}
    dominant = max(norm, key=norm.get)  # type: ignore[arg-type]
    return {
        "dominant": dominant,
        "scores": norm,
        "model": "tranc3-rule-based",
        "backend": "tranc3-stub",
    }


# ── Auth ───────────────────────────────────────────────────────


async def verify_auth(authorization: str | None) -> dict | None:
    if not authorization or not authorization.startswith("Bearer "):
        if ENVIRONMENT == "test":
            return {"userId": "test-user", "role": "admin"}
        return None

    # Dev bypass when no auth URL is configured
    if not AUTH_URL and ENVIRONMENT != "production":
        return {"userId": "dev", "role": "admin"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{AUTH_URL}/api/v1/auth/me",
                headers={"Authorization": authorization},
            )
            if resp.status_code == 200:
                user = resp.json()
                return {
                    "userId": user.get("id"),
                    "role": user.get("role"),
                    "email": user.get("email"),
                }
        except httpx.HTTPError:
            pass
    return None


# ── Routes ─────────────────────────────────────────────────────


@app.get("/")
async def root():
    return {
        "name": "Tranc3 AI Worker (Self-Hosted)",
        "version": "2.0.0",
        "backend": "self-hosted" if BACKEND_URL else "stub",
        "note": "Self-owned inference — no external AI services. Replaces Cloudflare Worker.",
        "routes": {
            "models": "GET  /api/v1/ai/models",
            "chat": "POST /api/v1/ai/chat",
            "embeddings": "POST /api/v1/ai/embeddings",
            "emotion": "POST /api/v1/ai/analyze-emotion",
            "consciousness": "POST /api/v1/ai/consciousness",
            "tokenize": "POST /api/v1/ai/tokenize",
            "predict": "POST /api/v1/ai/predict",
        },
    }


@app.get("/health")
async def health():
    has_backend = bool(BACKEND_URL)
    has_nano = bool(NANO_URL)
    backend_ok = False
    nano_ok = False

    async with httpx.AsyncClient(timeout=5.0) as client:
        if has_backend:
            try:
                resp = await client.get(f"{BACKEND_URL}/health")
                backend_ok = resp.status_code == 200
            except httpx.HTTPError:
                pass
        if has_nano:
            try:
                resp = await client.get(f"{NANO_URL}/health")
                nano_ok = resp.status_code == 200
            except httpx.HTTPError:
                pass

    mode = "tranc3-backend" if backend_ok else "tranc3-nano" if nano_ok else "stub"

    return {
        "status": "ok",
        "service": "tranc3-ai-worker",
        "version": "2.0.0",
        "backend": mode,
        "backend_url": BACKEND_URL or None,
        "nano_url": NANO_URL or None,
        "backend_healthy": backend_ok,
        "nano_healthy": nano_ok,
        "hosting": "self-hosted (replaces Cloudflare Worker)",
        "note": (
            "No backend connected. Set TRANC3_BACKEND_URL to enable full inference."
            if mode == "stub"
            else "Self-owned inference active."
        ),
        "timestamp": int(__import__("time").time()),
    }


@app.get("/api/v1/ai/models")
async def models():
    has_backend = bool(BACKEND_URL or NANO_URL)
    return {
        "object": "list",
        "backend_connected": has_backend,
        "data": [
            {
                "id": id_,
                "object": "model",
                "name": info["name"],
                "available": True,
                "backend": info["backend"] if has_backend else "tranc3-stub",
                "trained": has_backend,
                "capabilities": info["capabilities"],
            }
            for id_, info in TRANC3_MODELS.items()
        ],
    }


@app.post("/api/v1/ai/chat")
async def chat(request: Request, authorization: str | None = Header(None)):
    user = await verify_auth(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Valid Bearer token required")

    body = await request.json()
    messages = body.get("messages", [])
    model = body.get("model", "tranc3-base")

    if not messages:
        raise HTTPException(status_code=400, detail="messages array is required")

    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    system_msg = next((m["content"] for m in messages if m.get("role") == "system"), None)

    nano = await call_nano(
        "generate",
        {
            "prompt": last_user,
            "personality": body.get("personality", model),
            "system_prompt": system_msg,
            "max_tokens": body.get("max_tokens", 256),
            "temperature": body.get("temperature", 0.8),
            "top_p": body.get("top_p", 0.9),
        },
    )

    if nano and nano.get("response"):
        return {
            "id": str(uuid.uuid4()),
            "object": "chat.completion",
            "model": model,
            "backend": "tranc3-own",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": nano["response"]},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": nano.get("tokens", 0),
                "total_tokens": nano.get("tokens", 0),
            },
            "personality": nano.get("personality"),
        }

    # No backend — honest stub
    return stub_chat(messages, model)


@app.post("/api/v1/ai/embeddings")
async def embeddings(request: Request, authorization: str | None = Header(None)):
    user = await verify_auth(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Valid Bearer token required")

    body = await request.json()
    input_text = body.get("input")
    if not input_text:
        raise HTTPException(status_code=400, detail="input is required")

    texts = [input_text] if isinstance(input_text, str) else input_text
    nano = await call_nano("embed", {"text": texts[0], "pooling": body.get("pooling", "mean")})

    if nano and nano.get("embedding"):
        return {
            "object": "list",
            "model": "tranc3-embeddings",
            "backend": "tranc3-own",
            "data": [
                {"object": "embedding", "index": i, "embedding": nano["embedding"]}
                for i in range(len(texts))
            ],
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        }

    return stub_embedding(input_text)


@app.post("/api/v1/ai/analyze-emotion")
async def analyze_emotion(request: Request, authorization: str | None = Header(None)):
    user = await verify_auth(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Valid Bearer token required")

    body = await request.json()
    text = body.get("text") or body.get("input", "")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    nano = await call_nano("emotion", {"text": text})
    if nano and nano.get("dominant"):
        return nano

    return stub_emotion(text)


@app.post("/api/v1/ai/consciousness")
async def consciousness(request: Request, authorization: str | None = Header(None)):
    user = await verify_auth(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Valid Bearer token required")

    body = await request.json()
    text = body.get("text") or body.get("input", "")
    if not text:
        raise HTTPException(status_code=400, detail="text or input is required")

    nano = await call_nano("consciousness", {"text": text})
    if nano and isinstance(nano.get("phi"), (int, float)):
        return nano

    # Heuristic phi estimate
    words = text.split()
    vocab = len(set(words))
    phi = min(1.0, (vocab / max(len(words), 1)) * 2.0)
    return {
        "phi": round(phi, 4),
        "awareness": "high" if phi > 0.7 else "medium" if phi > 0.4 else "low",
        "model": "tranc3-heuristic",
        "backend": "tranc3-stub",
    }


@app.post("/api/v1/ai/tokenize")
async def tokenize(request: Request, authorization: str | None = Header(None)):
    user = await verify_auth(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Valid Bearer token required")

    body = await request.json()
    nano = await call_nano(
        "tokenize",
        {
            "action": body.get("action", "encode"),
            "text": body.get("text", ""),
            "ids": body.get("ids", []),
            "skip_special": body.get("skip_special", True),
        },
    )
    if nano:
        return nano

    # Whitespace fallback
    if body.get("action", "encode") == "encode":
        tokens = body.get("text", "").split()
        return {"tokens": tokens, "ids": list(range(len(tokens))), "model": "fallback"}
    return {"text": f"[{len(body.get('ids', []))} tokens decoded]", "model": "fallback"}


@app.post("/api/v1/ai/predict")
async def predict(request: Request, authorization: str | None = Header(None)):
    user = await verify_auth(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Valid Bearer token required")

    body = await request.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    nano = await call_nano(
        "predict",
        {
            "text": text,
            "top_k": body.get("top_k", 5),
            "predict_type": body.get("predict_type", "next_token"),
        },
    )
    if nano:
        return nano

    return {
        "prediction": "the",
        "confidence": 0.1,
        "top_k": [{"token": "the", "prob": 0.1}],
        "model": "tranc3-stub",
        "backend": "tranc3-stub",
    }


# ── Run ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)  # nosec B104 — containerised service
