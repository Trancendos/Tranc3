# src/fluidic/reactive_state.py
# Reactive state container — observable state that notifies subscribers on change
# Enables fluidic, event-driven architecture without polling

import asyncio
import logging
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ReactiveState(Generic[T]):
    """
    Observable state container. When the state changes, all subscribers
    are notified asynchronously. Enables reactive, event-driven patterns.

    Usage:
        health_state = ReactiveState[Dict[str, bool]]({})
        health_state.subscribe(on_health_change)
        health_state.set({"redis": True, "db": False})  # Triggers on_health_change
    """

    def __init__(self, initial: Optional[T] = None, name: str = "unnamed"):
        self._value: Optional[T] = initial
        self._subscribers: List[Callable] = []
        self._history: List[T] = []
        self._max_history: int = 100
        self._name = name
        self._lock = asyncio.Lock()

    @property
    def value(self) -> Optional[T]:
        """Current state value"""
        return self._value

    async def set(self, new_value: T) -> None:
        """Set a new state value and notify subscribers"""
        old_value = self._value
        async with self._lock:
            self._value = new_value
            self._history.append(new_value)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

        if old_value != new_value:
            await self._notify(new_value, old_value)

    async def update(self, **kwargs: Any) -> None:
        """Update dict-like state with partial changes"""
        if isinstance(self._value, dict):
            new_state = {**self._value, **kwargs}
            await self.set(new_state)  # type: ignore[arg-type]

    def subscribe(self, callback: Callable) -> None:
        """Subscribe to state changes"""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable) -> None:
        """Unsubscribe from state changes"""
        self._subscribers = [cb for cb in self._subscribers if cb != callback]

    async def _notify(self, new_value: T, old_value: Optional[T]) -> None:
        """Notify all subscribers of a state change"""
        for callback in self._subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(new_value, old_value)
                else:
                    callback(new_value, old_value)
            except Exception as e:
                logger.error(
                    "Reactive state subscriber error (%s): %s",
                    sanitize_for_log(self._name),
                    sanitize_for_log(e),
                    extra={"callback": callback.__name__},
                )

    @property
    def history(self) -> List[T]:
        """State change history"""
        return self._history.copy()

    def __repr__(self) -> str:
        return f"ReactiveState({self._name}, value={self._value})"


class StateStore:
    """
    Central store for multiple reactive states.
    Provides a unified interface for managing application state.
    """

    def __init__(self):
        self._states: Dict[str, ReactiveState] = {}

    def create(self, name: str, initial: Any = None) -> ReactiveState:
        """Create a new reactive state"""
        state = ReactiveState(initial, name=name)
        self._states[name] = state
        return state

    def get(self, name: str) -> Optional[ReactiveState]:
        """Get a reactive state by name"""
        return self._states.get(name)

    async def set(self, name: str, value: Any) -> None:
        """Set a state value"""
        state = self._states.get(name)
        if state:
            await state.set(value)

    def snapshot(self) -> Dict[str, Any]:
        """Get a snapshot of all current state values"""
        return {name: state.value for name, state in self._states.items()}


# Singleton
state_store = StateStore()
