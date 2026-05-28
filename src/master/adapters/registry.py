"""
src/master/adapters/registry.py — Unified adapter registry with priority routing.

Routes bot_type to the correct adapter using a priority chain:

  Priority 1: Exact bot_type match in adapter.handles
  Priority 2: "nanocode" → NanocodeAdapter
  Priority 3: "aeonmind" → AeonMindAdapter
  Priority 4: Core 12 types → Tranc3BotsAdapter (with SrcWorkersAdapter fallback)
  Priority 5: Everything else → stub response

Example dispatch:
    adapter = get_adapter("monitor")     # → Tranc3BotsAdapter
    adapter = get_adapter("nanocode")    # → NanocodeAdapter
    adapter = get_adapter("classify")    # → AeonMindAdapter (via aeonmind bot_type)
    adapter = get_adapter("aeonmind")    # → AeonMindAdapter
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .aeonmind_adapter import _AEONMIND_CAPABILITIES, AeonMindAdapter
from .base import BaseAdapter
from .nanocode_adapter import _NANOCODE_MODES, NanocodeAdapter
from .src_workers_adapter import SrcWorkersAdapter
from .tranc3_bots_adapter import _CORE_BOTS, Tranc3BotsAdapter

logger = logging.getLogger(__name__)


class _StubAdapter(BaseAdapter):
    """Fallback: returns a stub response for unknown bot types."""

    name = "stub"
    handles: frozenset = frozenset()

    async def dispatch(self, action: str, params: Dict[str, Any]) -> Any:
        return {"stub": True, "adapter": "stub", "action": action, "params": params}


class AdapterRegistry:
    """
    Singleton-style registry that selects the correct adapter for a given bot_type.

    The same instance is shared across the BotSwarm to avoid re-initialising
    adapters per-slot.
    """

    def __init__(self) -> None:
        self._tranc3 = Tranc3BotsAdapter()
        self._src = SrcWorkersAdapter()
        self._nano = NanocodeAdapter()
        self._aeon = AeonMindAdapter()
        self._stub = _StubAdapter()

        # Build a lookup map: bot_type → primary adapter
        self._map: Dict[str, BaseAdapter] = {}
        for bt in _CORE_BOTS:
            self._map[bt] = self._tranc3
        self._map["nanocode"] = self._nano
        self._map["aeonmind"] = self._aeon
        # AeonMind capabilities can also be addressed directly
        for cap in _AEONMIND_CAPABILITIES:
            if cap not in self._map:
                self._map[cap] = self._aeon
        # NanoCode failure modes can also be addressed directly
        for mode in _NANOCODE_MODES:
            if mode not in self._map:
                self._map[mode] = self._nano

    def resolve(self, bot_type: str) -> BaseAdapter:
        """Return the best adapter for bot_type, falling back through the chain."""
        adapter = self._map.get(bot_type)
        if adapter is None:
            logger.debug("No adapter for bot_type=%r — using stub", bot_type)
            return self._stub

        # Health-based fallback for inference types
        if adapter is self._tranc3 and not adapter.is_available():
            if bot_type in {"generate", "embed", "emotion", "tokenize",
                            "consciousness", "personality", "predict"}:
                if self._src.is_available():
                    logger.info("Tranc3BotsAdapter unavailable — falling back to SrcWorkersAdapter")
                    return self._src
            return self._stub

        return adapter

    def all_adapters(self) -> list[BaseAdapter]:
        return [self._tranc3, self._src, self._nano, self._aeon]

    def status(self) -> Dict[str, bool]:
        return {a.name: a.is_available() for a in self.all_adapters()}


# Module-level singleton
_registry: Optional[AdapterRegistry] = None


def get_adapter(bot_type: str) -> BaseAdapter:
    """Return the registered adapter for bot_type (creates registry on first call)."""
    global _registry
    if _registry is None:
        _registry = AdapterRegistry()
    return _registry.resolve(bot_type)
