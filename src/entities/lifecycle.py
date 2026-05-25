"""
Trancendos Ecosystem — Lifecycle Hooks & EventEmitter

Provides lifecycle event emission for all tier classes:
  onInit → onStart → (onCycle)* → onStop
  onError can fire at any point in the lifecycle.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union


class LifecycleEvent(str, Enum):
    INIT = "init"
    START = "start"
    STOP = "stop"
    ERROR = "error"
    CYCLE = "cycle"
    TOOL_CALL = "toolCall"
    TOOL_RESULT = "toolResult"


@dataclass
class LifecycleContext:
    entity: str
    tier: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    details: Optional[Dict[str, Any]] = None


# Type alias for lifecycle listeners — can be sync or async
LifecycleListener = Callable[[LifecycleContext], None]


class LifecycleEmitter:
    """
    Typed event emitter for entity lifecycle hooks.

    Supports:
      - Specific event listeners: onLifecycle('start', handler)
      - One-time listeners: onceLifecycle('error', handler)
      - Catch-all listeners: onAny(handler) — receives (event, context)
    """

    def __init__(self, owner_name: str) -> None:
        self._owner_name = owner_name
        self._listeners: Dict[str, List[LifecycleListener]] = {}
        self._any_listeners: List[Callable[[str, LifecycleContext], None]] = []

    @property
    def owner_name(self) -> str:
        return self._owner_name

    def on_lifecycle(self, event: LifecycleEvent, listener: LifecycleListener) -> "LifecycleEmitter":
        """Register a listener for a specific lifecycle event."""
        key = event.value if isinstance(event, LifecycleEvent) else event
        if key not in self._listeners:
            self._listeners[key] = []
        self._listeners[key].append(listener)
        return self

    def once_lifecycle(self, event: LifecycleEvent, listener: LifecycleListener) -> "LifecycleEmitter":
        """Register a one-time listener for a specific lifecycle event."""
        key = event.value if isinstance(event, LifecycleEvent) else event

        def wrapper(ctx: LifecycleContext) -> None:
            self.remove_lifecycle_listener(event, wrapper)
            listener(ctx)

        self.on_lifecycle(event, wrapper)
        return self

    def on_any(self, listener: Callable[[str, LifecycleContext], None]) -> "LifecycleEmitter":
        """Register a catch-all listener that receives (event, context)."""
        self._any_listeners.append(listener)
        return self

    def remove_lifecycle_listener(self, event: LifecycleEvent, listener: LifecycleListener) -> "LifecycleEmitter":
        """Remove a specific listener."""
        key = event.value if isinstance(event, LifecycleEvent) else event
        if key in self._listeners:
            self._listeners[key] = [l for l in self._listeners[key] if l != listener]
        return self

    async def emit_lifecycle(self, event: LifecycleEvent, details: Optional[Dict[str, Any]] = None) -> None:
        """Emit a lifecycle event with standardised context."""
        ctx = LifecycleContext(
            entity=self._owner_name,
            tier=-1,  # overridden by each tier class
            timestamp=datetime.utcnow(),
            details=details,
        )

        # Fire specific listeners
        key = event.value if isinstance(event, LifecycleEvent) else event
        for listener in self._listeners.get(key, []):
            try:
                result = listener(ctx)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass  # listeners should not crash the emitter

        # Fire catch-all listeners
        for listener in self._any_listeners:
            try:
                result = listener(key, ctx)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    def emit_lifecycle_sync(self, event: LifecycleEvent, details: Optional[Dict[str, Any]] = None) -> None:
        """Synchronous emit — for use in constructors where async isn't possible."""
        ctx = LifecycleContext(
            entity=self._owner_name,
            tier=-1,
            timestamp=datetime.utcnow(),
            details=details,
        )

        key = event.value if isinstance(event, LifecycleEvent) else event
        for listener in self._listeners.get(key, []):
            try:
                listener(ctx)
            except Exception:
                pass

        for listener in self._any_listeners:
            try:
                listener(key, ctx)
            except Exception:
                pass
