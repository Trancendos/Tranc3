"""
src/master/adapters/base.py — Base adapter contract.

Every adapter must implement `dispatch(action, params)` and
`is_available()` so the registry can fall through to the next
adapter when one is unavailable.
"""

from __future__ import annotations

import abc
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class BaseAdapter(abc.ABC):
    """Abstract base for all bot/worker adapters."""

    #: Unique name identifying this adapter in the registry
    name: str = ""

    #: Bot types this adapter can handle (used for routing)
    handles: frozenset[str] = frozenset()

    @abc.abstractmethod
    async def dispatch(self, action: str, params: Dict[str, Any]) -> Any:
        """Execute action with params, return raw result."""

    def is_available(self) -> bool:
        """Return True if underlying system is reachable/importable."""
        return True

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} name={self.name!r}>"
