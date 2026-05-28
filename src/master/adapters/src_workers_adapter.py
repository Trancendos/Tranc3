"""
src/master/adapters/src_workers_adapter.py — Bridge to src/workers/bot_registry.py.

Wraps the Redis-backed WorkerPool registry from src/workers/bot_registry.py which
provides:
    BotRegistry.run(bot_type, **kwargs) -> JobResult (via WorkerPool.submit_and_wait)

Only handles the 7 inference bot types that have WorkerPool backing:
    generate, embed, emotion, tokenize, consciousness, personality, predict

Falls back gracefully when Redis is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from .base import BaseAdapter

logger = logging.getLogger(__name__)

_INFERENCE_BOTS = frozenset({
    "generate", "embed", "emotion", "tokenize",
    "consciousness", "personality", "predict",
})


class SrcWorkersAdapter(BaseAdapter):
    """Adapter for the Redis-backed src/workers BotRegistry."""

    name = "src_workers"
    handles = _INFERENCE_BOTS

    def __init__(self) -> None:
        self._registry = None

    def _load_registry(self):
        if self._registry is not None:
            return self._registry
        try:
            from src.workers.bot_registry import BotRegistry  # noqa: PLC0415
            self._registry = BotRegistry
        except ImportError as exc:
            logger.debug("src.workers.bot_registry not importable: %s", exc)
            self._registry = None
        return self._registry

    def is_available(self) -> bool:
        return self._load_registry() is not None

    async def dispatch(self, action: str, params: Dict[str, Any]) -> Any:
        registry = self._load_registry()
        if registry is None:
            return {"stub": True, "adapter": self.name, "action": action, "params": params}

        bot_type = params.pop("_bot_type", "generate")
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: registry.run(bot_type, action=action, **params),
            )
            return result if isinstance(result, dict) else {"result": str(result)}
        except Exception as exc:
            logger.warning("SrcWorkersAdapter dispatch failed: %s", exc)
            raise
