"""The Lab — ACO pheromone router across 6 free code AI backends (Lead AI: The Dr. & Slime)"""

from __future__ import annotations

import collections
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from models import (
    BackendStatus,
    CodeBackend,
    CodeRequest,
    CodeResponse,
    LabStatus,
    TaskType,
)

import config

logger = logging.getLogger(config.WORKER_NAME)


# ── ThresholdGuard ─────────────────────────────────────────────────────────────


class ThresholdGuard:
    def __init__(self, name: str, quota: int, window: int):
        self.name = name
        self.quota = quota
        self.window = window
        self.pheromone: float = 1.0
        self._ts: collections.deque = collections.deque()

    def can_allow(self) -> bool:
        self._evict()
        return len(self._ts) < self.quota

    def record(self) -> None:
        self._ts.append(time.monotonic())

    def allow(self) -> bool:
        if not self.can_allow():
            return False
        self.record()
        return True

    def reinforce(self) -> None:
        self.pheromone = min(1.0, self.pheromone + 0.1)

    def decay(self) -> None:
        self.pheromone = max(0.0, self.pheromone - config.PHEROMONE_DECAY)

    def calls_in_window(self) -> int:
        self._evict()
        return len(self._ts)

    def _evict(self) -> None:
        cutoff = time.monotonic() - self.window
        while self._ts and self._ts[0] < cutoff:
            self._ts.popleft()


# ── Backend registry ───────────────────────────────────────────────────────────

_BACKENDS: Dict[str, ThresholdGuard] = {
    CodeBackend.ollama_deepseek: ThresholdGuard(
        CodeBackend.ollama_deepseek, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    CodeBackend.ollama_codellama: ThresholdGuard(
        CodeBackend.ollama_codellama, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    CodeBackend.ollama_qwen: ThresholdGuard(
        CodeBackend.ollama_qwen, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    CodeBackend.tabby: ThresholdGuard(
        CodeBackend.tabby, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    # Cloud backends — hard stops at hourly limits
    CodeBackend.huggingface: ThresholdGuard(
        CodeBackend.huggingface, config.HF_HOURLY_LIMIT, config.QUOTA_WINDOW_SECONDS
    ),
    CodeBackend.openrouter: ThresholdGuard(
        CodeBackend.openrouter, config.OPENROUTER_HOURLY_LIMIT, config.QUOTA_WINDOW_SECONDS
    ),
}


def _choose_backend() -> Optional[str]:
    candidates = [
        (name, guard)
        for name, guard in _BACKENDS.items()
        if guard.can_allow() and guard.pheromone > 0.01
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[1].pheromone, reverse=True)
    return candidates[0][0]


# ── Backend prompt builder ─────────────────────────────────────────────────────


def _build_prompt(req: CodeRequest) -> str:
    parts: List[str] = []
    task_prefix = {
        TaskType.complete: "Complete the following code",
        TaskType.generate: "Generate code",
        TaskType.review: "Review the following code and provide feedback",
        TaskType.explain: "Explain the following code",
        TaskType.refactor: "Refactor the following code",
        TaskType.test: "Write tests for the following code",
        TaskType.fix: "Fix the bug in the following code",
    }.get(req.task_type, "Generate code")

    if req.language:
        parts.append(f"{task_prefix} in {req.language}:")
    else:
        parts.append(f"{task_prefix}:")

    if req.context:
        parts.append(f"\nContext:\n{req.context}")

    parts.append(f"\n{req.prompt}")
    return "\n".join(parts)


# ── Per-backend adapters ───────────────────────────────────────────────────────


async def _call_ollama(model: str, req: CodeRequest) -> Optional[Dict[str, Any]]:
    prompt = _build_prompt(req)
    try:
        async with httpx.AsyncClient(verify=config.TLS_VERIFY, timeout=60.0) as client:
            r = await client.post(
                f"{config.OLLAMA_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": req.max_tokens,
                        "temperature": req.temperature,
                    },
                },
            )
            r.raise_for_status()
            data = r.json()
            return {
                "result": data.get("response", ""),
                "tokens_used": data.get("eval_count"),
            }
    except Exception as exc:
        logger.debug("Ollama %s call failed: %s", model, exc)
        return None


async def _call_tabby(req: CodeRequest) -> Optional[Dict[str, Any]]:
    if not config.TABBY_URL:
        return None
    prompt = _build_prompt(req)
    try:
        async with httpx.AsyncClient(verify=config.TLS_VERIFY, timeout=30.0) as client:
            r = await client.post(
                f"{config.TABBY_URL}/v1/completions",
                json={
                    "prompt": prompt,
                    "max_new_tokens": req.max_tokens,
                    "temperature": req.temperature,
                },
            )
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices", [])
            text = choices[0].get("text", "") if choices else ""
            return {"result": text, "tokens_used": None}
    except Exception as exc:
        logger.debug("Tabby call failed: %s", exc)
        return None


async def _call_huggingface(req: CodeRequest) -> Optional[Dict[str, Any]]:
    if not config.HF_API_KEY:
        return None
    prompt = _build_prompt(req)
    try:
        async with httpx.AsyncClient(verify=config.TLS_VERIFY, timeout=30.0) as client:
            r = await client.post(
                f"https://api-inference.huggingface.co/models/{config.HF_CODE_MODEL}",
                headers={"Authorization": f"Bearer {config.HF_API_KEY}"},
                json={
                    "inputs": prompt,
                    "parameters": {
                        "max_new_tokens": min(req.max_tokens, 1024),
                        "temperature": req.temperature,
                        "return_full_text": False,
                    },
                },
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and data:
                text = data[0].get("generated_text", "")
            else:
                text = str(data)
            return {"result": text, "tokens_used": None}
    except Exception as exc:
        logger.debug("HuggingFace call failed: %s", exc)
        return None


async def _call_openrouter(req: CodeRequest) -> Optional[Dict[str, Any]]:
    if not config.OPENROUTER_API_KEY:
        return None
    prompt = _build_prompt(req)
    try:
        async with httpx.AsyncClient(verify=config.TLS_VERIFY, timeout=30.0) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://trancendos.com",
                    "X-Title": "Trancendos The Lab",
                },
                json={
                    "model": config.OPENROUTER_CODE_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": req.max_tokens,
                    "temperature": req.temperature,
                },
            )
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices", [])
            text = choices[0].get("message", {}).get("content", "") if choices else ""
            usage = data.get("usage", {})
            return {"result": text, "tokens_used": usage.get("total_tokens")}
    except Exception as exc:
        logger.debug("OpenRouter call failed: %s", exc)
        return None


async def _offline_generate(req: CodeRequest) -> Dict[str, Any]:
    return {
        "result": f"# Offline mode — all backends unavailable\n# Task: {req.task_type}\n# Prompt: {req.prompt[:200]}",
        "tokens_used": None,
    }


# ── LabRouter ──────────────────────────────────────────────────────────────────


class LabRouter:
    async def generate(self, req: CodeRequest) -> CodeResponse:
        t0 = time.monotonic()
        backend_name = _choose_backend()
        result_data: Optional[Dict[str, Any]] = None

        if backend_name is not None:
            guard = _BACKENDS[backend_name]
            guard.record()

            if backend_name == CodeBackend.ollama_deepseek:
                result_data = await _call_ollama(config.OLLAMA_CODE_MODEL, req)
            elif backend_name == CodeBackend.ollama_codellama:
                result_data = await _call_ollama(config.OLLAMA_FALLBACK_MODEL, req)
            elif backend_name == CodeBackend.ollama_qwen:
                result_data = await _call_ollama(config.OLLAMA_FALLBACK2_MODEL, req)
            elif backend_name == CodeBackend.tabby:
                result_data = await _call_tabby(req)
            elif backend_name == CodeBackend.huggingface:
                result_data = await _call_huggingface(req)
            elif backend_name == CodeBackend.openrouter:
                result_data = await _call_openrouter(req)

            if result_data is None:
                guard.decay()
            else:
                guard.reinforce()

        if result_data is None:
            backend_name = CodeBackend.offline
            result_data = await _offline_generate(req)

        latency_ms = (time.monotonic() - t0) * 1000
        return CodeResponse(
            request_id=str(uuid.uuid4()),
            result=result_data["result"],
            language=req.language,
            task_type=req.task_type,
            backend=CodeBackend(backend_name),
            tokens_used=result_data.get("tokens_used"),
            latency_ms=round(latency_ms, 2),
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def status(self) -> LabStatus:
        active = _choose_backend() or CodeBackend.offline
        backend_statuses = []
        model_map = {
            CodeBackend.ollama_deepseek: config.OLLAMA_CODE_MODEL,
            CodeBackend.ollama_codellama: config.OLLAMA_FALLBACK_MODEL,
            CodeBackend.ollama_qwen: config.OLLAMA_FALLBACK2_MODEL,
            CodeBackend.tabby: "tabby-self-hosted",
            CodeBackend.huggingface: config.HF_CODE_MODEL,
            CodeBackend.openrouter: config.OPENROUTER_CODE_MODEL,
        }
        for name, guard in _BACKENDS.items():
            calls = guard.calls_in_window()
            backend_statuses.append(
                BackendStatus(
                    name=CodeBackend(name),
                    healthy=guard.pheromone > 0.01,
                    pheromone=round(guard.pheromone, 3),
                    calls_in_window=calls,
                    quota_remaining=max(0, guard.quota - calls),
                    model=model_map.get(name),
                )
            )
        return LabStatus(
            active_backend=CodeBackend(active),
            backends=backend_statuses,
            openai_compat_url=config.OPENAI_COMPAT_URL,
        )
