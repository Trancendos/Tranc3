"""
src/master/adapters/aeonmind_adapter.py — Bridge to AeonMind BotServiceWorker.

Wraps AeonMind's Tier 5 stateless BotServiceWorker from:
    aeonmind/python/aeonmind/services/bot_services.py

Exposes 15 BotCapability types beyond the core 12:
    translate, classify, extract, validate, transform,
    notify, log, cache, route, filter, enrich, generic,
    summarize (alias for summarise), monitor (alias), embed (alias)

Usage in YAML:
    - bot: aeonmind
      action: classify
      params:
        input: "some text to classify"
        schema: {categories: ["positive", "negative"]}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from .base import BaseAdapter

logger = logging.getLogger(__name__)

_AEONMIND_CAPABILITIES = frozenset(
    {
        "translate",
        "summarize",
        "classify",
        "extract",
        "validate",
        "transform",
        "monitor",
        "notify",
        "log",
        "cache",
        "route",
        "filter",
        "enrich",
        "embed",
        "generic",
    }
)


class AeonMindAdapter(BaseAdapter):
    """Adapter for AeonMind Tier 5 BotServiceWorker (15 capabilities)."""

    name = "aeonmind"
    handles = frozenset({"aeonmind"})

    def __init__(self) -> None:
        self._worker_cls = None
        self._capability_cls = None

    def _load(self):
        if self._worker_cls is not None:
            return
        try:
            import sys  # noqa: PLC0415
            from pathlib import Path  # noqa: PLC0415

            aeon_path = str(
                Path(__file__).resolve().parent.parent.parent.parent / "aeonmind" / "python"
            )
            if aeon_path not in sys.path:
                sys.path.insert(0, aeon_path)
            from aeonmind.services.bot_services import (  # noqa: PLC0415
                BotCapability,
                BotServiceWorker,
            )

            self._worker_cls = BotServiceWorker
            self._capability_cls = BotCapability
        except ImportError as exc:
            logger.debug("AeonMind not importable: %s", exc)

    def is_available(self) -> bool:
        self._load()
        return self._worker_cls is not None

    async def dispatch(self, action: str, params: Dict[str, Any]) -> Any:
        self._load()
        if self._worker_cls is None:
            return {
                "stub": True,
                "adapter": self.name,
                "capability": action,
                "params": params,
            }

        cap_name = action.lower().replace("-", "_")
        if cap_name not in _AEONMIND_CAPABILITIES:
            raise ValueError(
                f"Unknown AeonMind capability '{cap_name}'. Valid: {sorted(_AEONMIND_CAPABILITIES)}"
            )

        try:
            capability = self._capability_cls[cap_name.upper()]
        except (KeyError, ValueError):
            capability = self._capability_cls(cap_name)

        worker = self._worker_cls()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: worker.execute(capability=capability, **params),
        )
        return result if isinstance(result, dict) else {"output": str(result)}
