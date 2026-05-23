# bots/handlers.py — Handler logic for each bot type.
#
# Inference bots (generate, embed, emotion, etc.) proxy to TRANC3_ENGINE_URL.
# Utility bots (code, memory, monitor, search, summarise) run standalone.
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

_ENGINE_URL = os.getenv("TRANC3_ENGINE_URL", "")


# ── Shared HTTP helper ─────────────────────────────────────────────────────────

async def _engine_post(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST to the Tranc3 engine nanoservice. Raises on failure."""
    try:
        import httpx
        url = _ENGINE_URL.rstrip("/") + endpoint
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        raise RuntimeError(f"Engine call to {endpoint} failed: {exc}") from exc


def _engine_available() -> bool:
    return bool(_ENGINE_URL)


# ── Inference bots ─────────────────────────────────────────────────────────────

async def handle_generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _engine_available():
        return await _engine_post("/generate", payload)
    prompt = payload.get("prompt", "")
    return {
        "text": f"[offline stub] Echo: {prompt[:120]}",
        "tokens": len(prompt.split()),
        "model": "tranc3-stub",
    }


async def handle_embed(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _engine_available():
        return await _engine_post("/embed", payload)
    text = str(payload.get("text", ""))
    h = int(hashlib.sha256(text.encode()).hexdigest(), 16)
    dim = int(payload.get("dim", 128))
    vec = [((h >> (i * 4)) & 0xF) / 15.0 - 0.5 for i in range(dim)]
    return {"embedding": vec, "dim": dim, "model": "tranc3-stub"}


async def handle_emotion(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _engine_available():
        return await _engine_post("/emotion", payload)
    text = str(payload.get("text", "")).lower()
    scores = {
        "joy":     sum(1 for w in ("happy", "great", "love", "wonderful") if w in text),
        "sadness": sum(1 for w in ("sad", "cry", "miss", "hurt") if w in text),
        "anger":   sum(1 for w in ("angry", "hate", "furious", "mad") if w in text),
        "fear":    sum(1 for w in ("scared", "fear", "afraid", "terrified") if w in text),
        "surprise":sum(1 for w in ("wow", "amazing", "unbelievable", "shocked") if w in text),
        "neutral": 1,
    }
    dominant = max(scores, key=lambda k: scores[k])
    total = max(sum(scores.values()), 1)
    return {
        "dominant": dominant,
        "scores": {k: round(v / total, 3) for k, v in scores.items()},
        "model": "tranc3-stub",
    }


async def handle_tokenize(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _engine_available():
        return await _engine_post("/tokenize", payload)
    text = str(payload.get("text", ""))
    tokens = re.findall(r"\w+|[^\w\s]", text)
    return {"tokens": tokens, "count": len(tokens), "model": "tranc3-stub"}


async def handle_consciousness(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _engine_available():
        return await _engine_post("/consciousness", payload)
    text = str(payload.get("text", ""))
    h = int(hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest(), 16)
    return {
        "state": "aware",
        "coherence": round(0.5 + (h % 50) / 100, 3),
        "depth": round(0.3 + (h % 70) / 100, 3),
        "model": "tranc3-stub",
    }


async def handle_personality(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _engine_available():
        return await _engine_post("/personality", payload)
    text = str(payload.get("text", ""))
    h = int(hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest(), 16)
    dims = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]
    return {
        "profile": {d: round(0.2 + ((h >> (i * 8)) & 0xFF) / 255.0 * 0.8, 3) for i, d in enumerate(dims)},
        "model": "tranc3-stub",
    }


async def handle_predict(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _engine_available():
        return await _engine_post("/predict", payload)
    context = str(payload.get("context", ""))
    words = context.split()
    next_word = words[-1][::-1] if words else "..."
    return {"prediction": next_word, "confidence": 0.5, "model": "tranc3-stub"}


# ── Utility bots (standalone — no ML) ─────────────────────────────────────────

async def handle_code(payload: Dict[str, Any]) -> Dict[str, Any]:
    task = payload.get("task", "")
    lang = payload.get("language", "python")
    templates = {
        "python": f'def solution():\n    """Auto-generated stub for: {task[:60]}\"\"\"\n    pass\n',
        "javascript": f'function solution() {{\n  // Auto-generated stub for: {task[:60]}\n}}\n',
        "typescript": f'function solution(): void {{\n  // Auto-generated stub for: {task[:60]}\n}}\n',
    }
    return {
        "code": templates.get(lang, templates["python"]),
        "language": lang,
        "task": task,
        "note": "Stub generated; connect TRANC3_ENGINE_URL for full code synthesis.",
    }


async def handle_memory(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = payload.get("action", "store")
    key    = payload.get("key", "")
    value  = payload.get("value", "")
    # Simple in-process dict — connect a VectorStore/Redis for persistent memory
    _STORE: Dict[str, Any] = {}
    if action == "store":
        _STORE[key] = {"value": value, "ts": time.time()}
        return {"status": "stored", "key": key}
    if action == "retrieve":
        entry = _STORE.get(key)
        return {"value": entry["value"] if entry else None, "key": key}
    if action == "list":
        return {"keys": list(_STORE.keys()), "count": len(_STORE)}
    return {"error": f"Unknown action: {action}"}


async def handle_monitor(payload: Dict[str, Any]) -> Dict[str, Any]:
    import platform

    import psutil  # type: ignore
    try:
        cpu    = psutil.cpu_percent(interval=0.1)
        mem    = psutil.virtual_memory()
        disk   = psutil.disk_usage("/")
        return {
            "cpu_pct":     cpu,
            "mem_pct":     mem.percent,
            "mem_used_mb": round(mem.used / 1_048_576, 1),
            "disk_pct":    disk.percent,
            "platform":    platform.system(),
            "uptime_s":    round(time.time() - psutil.boot_time(), 1),
        }
    except ImportError:
        return {"cpu_pct": 0, "mem_pct": 0, "disk_pct": 0, "note": "psutil not installed"}


async def handle_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    query   = str(payload.get("query", ""))
    limit   = int(payload.get("limit", 5))
    source  = payload.get("source", "local")
    if source == "web":
        return {
            "results": [],
            "note": "Web search requires external integration; set source=local or provide a search provider.",
            "query": query,
        }
    h = int(hashlib.sha256(query.encode()).hexdigest(), 16)
    results = [{"id": i, "score": round(1.0 - i * 0.1, 2), "text": f"[stub result {i}] {query}"} for i in range(min(limit, 5))]
    return {"results": results, "total": h % 1000, "query": query, "source": "stub"}


async def handle_summarise(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _engine_available():
        return await _engine_post("/generate", {
            "prompt": f"Summarise the following in 3 sentences:\n\n{payload.get('text', '')}",
            "max_tokens": 150,
        })
    text  = str(payload.get("text", ""))
    words = text.split()
    ratio = float(payload.get("ratio", 0.3))
    keep  = max(1, int(len(words) * ratio))
    summary = " ".join(words[:keep]) + ("..." if len(words) > keep else "")
    return {"summary": summary, "original_words": len(words), "summary_words": keep}


# ── Dispatch table ─────────────────────────────────────────────────────────────

HANDLERS = {
    "generate":     handle_generate,
    "embed":        handle_embed,
    "emotion":      handle_emotion,
    "tokenize":     handle_tokenize,
    "consciousness":handle_consciousness,
    "personality":  handle_personality,
    "predict":      handle_predict,
    "code":         handle_code,
    "memory":       handle_memory,
    "monitor":      handle_monitor,
    "search":       handle_search,
    "summarise":    handle_summarise,
}
