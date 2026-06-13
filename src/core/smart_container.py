"""
Smart DI container with lifetime management and auto-wiring.
"""
from __future__ import annotations

import inspect
import threading
from contextlib import contextmanager
from enum import Enum
from typing import Any, Callable, Dict, Generator, Optional, Type, TypeVar

T = TypeVar("T")


class Lifetime(Enum):
    SINGLETON = "singleton"
    TRANSIENT = "transient"
    REQUEST = "request"


class DIError(Exception):
    pass


_request_scope_local = threading.local()


class RequestScope:
    """Context manager that isolates request-scoped instances."""

    def __init__(self, container: "SmartContainer") -> None:
        self._container = container

    def __enter__(self) -> "RequestScope":
        if not hasattr(_request_scope_local, "stack"):
            _request_scope_local.stack = []
        _request_scope_local.stack.append({})
        return self

    def __exit__(self, *args: Any) -> None:
        if hasattr(_request_scope_local, "stack") and _request_scope_local.stack:
            _request_scope_local.stack.pop()


def _get_request_cache() -> Optional[Dict[type, Any]]:
    stack = getattr(_request_scope_local, "stack", None)
    if stack:
        return stack[-1]
    return None


class _Registration:
    def __init__(
        self,
        lifetime: Lifetime,
        factory: Callable[[], Any],
    ) -> None:
        self.lifetime = lifetime
        self.factory = factory
        self._singleton_instance: Any = None
        self._singleton_lock = threading.Lock()

    def get(self, type_: type) -> Any:
        if self.lifetime == Lifetime.SINGLETON:
            if self._singleton_instance is None:
                with self._singleton_lock:
                    if self._singleton_instance is None:
                        self._singleton_instance = self.factory()
            return self._singleton_instance

        if self.lifetime == Lifetime.REQUEST:
            cache = _get_request_cache()
            if cache is None:
                raise DIError(
                    f"Cannot resolve REQUEST-scoped {type_.__name__} outside a request scope. "
                    "Use container.request_scope() context manager."
                )
            if type_ not in cache:
                cache[type_] = self.factory()
            return cache[type_]

        # TRANSIENT
        return self.factory()


class SmartContainer:
    """
    Dependency injection container with SINGLETON, TRANSIENT, and REQUEST lifetimes.
    Supports auto-wiring via __init__ type annotations.
    """

    def __init__(self) -> None:
        self._registry: Dict[type, _Registration] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        type_: Type[T],
        implementation: Optional[Type[T]] = None,
        lifetime: Lifetime = Lifetime.TRANSIENT,
    ) -> None:
        """Register a class (optionally with a different implementation class)."""
        impl = implementation if implementation is not None else type_
        factory = self._build_autowire_factory(impl)
        with self._lock:
            self._registry[type_] = _Registration(lifetime, factory)

    def register_factory(
        self,
        type_: Type[T],
        factory: Callable[[], T],
        lifetime: Lifetime = Lifetime.TRANSIENT,
    ) -> None:
        """Register a callable factory."""
        with self._lock:
            self._registry[type_] = _Registration(lifetime, factory)

    def register_instance(self, type_: Type[T], instance: T) -> None:
        """Register a pre-built singleton instance."""
        with self._lock:
            self._registry[type_] = _Registration(
                Lifetime.SINGLETON, lambda: instance
            )
            # Force singleton to be the instance
            reg = self._registry[type_]
            reg._singleton_instance = instance

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, type_: Type[T]) -> T:
        """Resolve a type, raising DIError if not registered."""
        with self._lock:
            reg = self._registry.get(type_)
        if reg is None:
            raise DIError(
                f"Type '{type_.__name__}' is not registered in the container."
            )
        return reg.get(type_)  # type: ignore[return-value]

    def try_resolve(self, type_: Type[T]) -> Optional[T]:
        """Resolve a type, returning None if not registered."""
        try:
            return self.resolve(type_)
        except DIError:
            return None

    # ------------------------------------------------------------------
    # Request scope
    # ------------------------------------------------------------------

    @contextmanager
    def request_scope(self) -> Generator[RequestScope, None, None]:
        """Context manager for REQUEST-scoped lifetimes."""
        scope = RequestScope(self)
        with scope:
            yield scope

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def registered_types(self) -> list:
        with self._lock:
            return list(self._registry.keys())

    def is_registered(self, type_: type) -> bool:
        with self._lock:
            return type_ in self._registry

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_autowire_factory(self, cls: type) -> Callable[[], Any]:
        """Build a factory that auto-wires constructor dependencies."""
        try:
            sig = inspect.signature(cls.__init__)
        except (ValueError, TypeError):
            return cls  # type: ignore[return-value]

        params = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.annotation is inspect.Parameter.empty:
                continue
            if param.annotation is type(None):
                continue
            params.append(param.annotation)

        if not params:
            return cls  # type: ignore[return-value]

        container_ref = self

        def factory() -> Any:
            args = [container_ref.resolve(p) for p in params]
            return cls(*args)

        return factory
