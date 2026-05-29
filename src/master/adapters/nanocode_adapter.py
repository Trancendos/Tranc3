"""
src/master/adapters/nanocode_adapter.py — Bridge to NanoCodeBotDispatcher.

Wraps src/healing/nanocode_bots.py which provides:
    NanoCodeBotDispatcher.dispatch(failure_mode: FailureMode) -> RepairResult

Bot type: "nanocode"

Action maps to FailureMode enum values:
    compliance_metadata_missing, stale_embedding, free_tier_approaching,
    rate_limit_hit, service_unreachable, config_drift,
    memory_leak, high_error_rate, dependency_failed

Usage in YAML:
    - bot: nanocode
      action: service_unreachable
      params:
        service: infinity-auth
        context: {"error": "connection refused"}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from .base import BaseAdapter

logger = logging.getLogger(__name__)

_NANOCODE_MODES = frozenset(
    {
        "compliance_metadata_missing",
        "stale_embedding",
        "free_tier_approaching",
        "rate_limit_hit",
        "service_unreachable",
        "config_drift",
        "memory_leak",
        "high_error_rate",
        "dependency_failed",
    }
)


class NanocodeAdapter(BaseAdapter):
    """Adapter routing to NanoCodeBotDispatcher autonomous repair bots."""

    name = "nanocode"
    handles = frozenset({"nanocode"})

    def __init__(self) -> None:
        self._dispatcher = None
        self._failure_mode_cls = None

    def _load(self):
        if self._dispatcher is not None:
            return
        try:
            from src.healing.nanocode_bots import (  # noqa: PLC0415
                FailureMode,
                NanoCodeBotDispatcher,
            )

            self._dispatcher = NanoCodeBotDispatcher()
            self._failure_mode_cls = FailureMode
        except ImportError as exc:
            logger.debug("nanocode_bots not importable: %s", exc)

    def is_available(self) -> bool:
        self._load()
        return self._dispatcher is not None

    async def dispatch(self, action: str, params: Dict[str, Any]) -> Any:
        self._load()
        if self._dispatcher is None:
            return {
                "stub": True,
                "adapter": self.name,
                "mode": action,
                "params": params,
            }

        mode_name = action.lower().replace("-", "_")
        if mode_name not in _NANOCODE_MODES:
            raise ValueError(
                f"Unknown nanocode failure mode '{mode_name}'. Valid: {sorted(_NANOCODE_MODES)}"
            )

        try:
            failure_mode = self._failure_mode_cls[mode_name.upper()]
        except KeyError:
            failure_mode = self._failure_mode_cls(mode_name)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._dispatcher.dispatch(failure_mode, context=params),
        )
        return result if isinstance(result, dict) else {"repaired": True, "mode": mode_name}
