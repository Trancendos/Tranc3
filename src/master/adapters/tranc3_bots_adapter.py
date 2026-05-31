"""
src/master/adapters/tranc3_bots_adapter.py — Bridge to tranc3-bots registry.

Wraps tranc3-bots/bots/registry.py which exposes:
    BotRegistry.run(bot_type, timeout=30, **kwargs) -> dict

Handles all 12 core bot types:
    generate, embed, emotion, tokenize, consciousness, personality,
    predict, code, memory, monitor, search, summarise
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict

from .base import BaseAdapter

logger = logging.getLogger(__name__)

_BOTS_PATH = str(Path(__file__).resolve().parent.parent.parent.parent / "tranc3-bots")

_CORE_BOTS = frozenset(
    {
        "generate",
        "embed",
        "emotion",
        "tokenize",
        "consciousness",
        "personality",
        "predict",
        "code",
        "memory",
        "monitor",
        "search",
        "summarise",
    }
)


class Tranc3BotsAdapter(BaseAdapter):
    """Adapter for the tranc3-bots async HANDLERS registry."""

    name = "tranc3_bots"
    handles = _CORE_BOTS

    def __init__(self) -> None:
        self._registry = None

    def _load_registry(self):
        if self._registry is not None:
            return self._registry
        if _BOTS_PATH not in sys.path:
            sys.path.insert(0, _BOTS_PATH)
        try:
            from bots.registry import BotRegistry  # noqa: PLC0415

            self._registry = BotRegistry
        except ImportError as exc:
            logger.debug("tranc3-bots not importable: %s", exc)
            self._registry = None
        return self._registry

    def is_available(self) -> bool:
        return self._load_registry() is not None

    async def dispatch(self, action: str, params: Dict[str, Any]) -> Any:
        registry = self._load_registry()
        if registry is None:
            return {"stub": True, "adapter": self.name, "action": action, "params": params}

        bot_type = params.pop("_bot_type", action)
        timeout = params.pop("_timeout", 30)

        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: registry.run(bot_type, timeout=timeout, action=action, **params),
                ),
                timeout=float(timeout),
            )
            return result
        except Exception as exc:
            logger.warning("Tranc3BotsAdapter dispatch failed: %s", exc)
            raise
