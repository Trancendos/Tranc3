"""Smart DI container with auto-wiring, lifetimes, and thread-safe singletons."""
from __future__ import annotations

import inspect
import threading
from enum import Enum, auto
from typing import Any, Callable, Optional, Type, TypeVar

T = TypeVar("T")

_local = threading.local()


class Lifetime(Enum):
    SINGLETON = auto()
    TRANSIENT = auto()
    REQUEST = auto()


class DIError(Exception):
    """Raised when dependency injection fails."""


class RequestScope:
    """Context manager that establishes a per-request scope cache."""

    def __init__(self, container: "SmartContainer") -> None:
        self._container = container
        self._cache: dict[type, Any] = {}

    def __enter__(self) -> "RequestScope":
        if not hasattr(_local, "scopes"):
            _local.scopes = []
        _local.scopes.append(self._cache)
        return self

    def __exit__(self, *_: Any) -> None:
        if hasattr(_local, "scopes") and _local.scopes:
            _local.scopes.pop()

    @staticmethod
    def current() -> Optional[dict[type, Any]]:
        scopes: list[dict[type, Any]] = getattr(_local, "scopes", [])
        return scopes[-1] if scopes else None


class _Registration:
    __slots__ = ("factory", "lifetime", "instance", "lock")

    def __init__(self, factory: Callable[[], Any], lifetime: Lifetime) -> None:
        self.factory = factory
        self.lifetime = lifetime
        self.instance: Any = None
        self.lock = threading.Lock()


class SmartContainer:
    """DI container with auto-wiring, lifetimes, and thread-safe singleton creation."""

    def __init__(self) -> None:
        self._registrations: dict[type, _Registration] = {}
        self._global_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    #  Registration                                                         #
    # ------------------------------------------------------------------ #

    def register(
        self,
        abstract: Type[T],
        concrete: Optional[Type[T]] = None,
        lifetime: Lifetime = Lifetime.TRANSIENT,
    ) -> "SmartContainer":
        """Register a type, optionally mapping abstract → concrete."""
        impl = concrete if concrete is not None else abstract
        self._registrations[abstract] = _Registration(
            factory=lambda: self._build(impl),
            lifetime=lifetime,
        )
        return self

    def register_factory(
        self,
        abstract: Type[T],
        factory: Callable[[], T],
        lifetime: Lifetime = Lifetime.TRANSIENT,
    ) -> "SmartContainer":
        """Register a callable factory for a type."""
        self._registrations[abstract] = _Registration(
            factory=factory,
            lifetime=lifetime,
        )
        return self

    def register_instance(self, abstract: Type[T], instance: T) -> "SmartContainer":
        """Register a pre-built singleton instance."""
        reg = _Registration(factory=lambda: instance, lifetime=Lifetime.SINGLETON)
        reg.instance = instance
        self._registrations[abstract] = reg
        return self

    # ------------------------------------------------------------------ #
    #  Resolution                                                           #
    # ------------------------------------------------------------------ #

    def resolve(self, abstract: Type[T]) -> T:
        """Resolve a type, raising DIError if not registered."""
        if abstract not in self._registrations:
            raise DIError(f"Type {abstract!r} is not registered in the container.")
        reg = self._registrations[abstract]
        return self._resolve_reg(abstract, reg)  # type: ignore[return-value]

    def try_resolve(self, abstract: Type[T]) -> Optional[T]:
        """Resolve a type, returning None if not registered."""
        try:
            return self.resolve(abstract)
        except DIError:
            return None

    def _resolve_reg(self, abstract: type, reg: _Registration) -> Any:
        if reg.lifetime is Lifetime.SINGLETON:
            if reg.instance is None:
                with reg.lock:
                    if reg.instance is None:  # double-checked locking
                        reg.instance = reg.factory()
            return reg.instance

        if reg.lifetime is Lifetime.REQUEST:
            scope = RequestScope.current()
            if scope is None:
                raise DIError(
                    f"Cannot resolve REQUEST-scoped {abstract!r} outside a request scope."
                )
            if abstract not in scope:
                scope[abstract] = reg.factory()
            return scope[abstract]

        # TRANSIENT
        return reg.factory()

    # ------------------------------------------------------------------ #
    #  Auto-wiring                                                          #
    # ------------------------------------------------------------------ #

    def _build(self, cls: type) -> Any:
        """Instantiate *cls* by auto-wiring typed __init__ parameters."""
        try:
            sig = inspect.signature(cls.__init__)
        except (ValueError, TypeError):
            return cls()

        kwargs: dict[str, Any] = {}
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            ann = param.annotation
            if ann is inspect.Parameter.empty:
                if param.default is inspect.Parameter.empty:
                    raise DIError(
                        f"Cannot auto-wire {cls!r}: parameter {name!r} has no type annotation and no default."
                    )
                continue  # use default
            resolved = self.try_resolve(ann)
            if resolved is None:
                if param.default is inspect.Parameter.empty:
                    raise DIError(
                        f"Cannot auto-wire {cls!r}: dependency {ann!r} for parameter {name!r} is not registered."
                    )
                # fall back to default
            else:
                kwargs[name] = resolved
        return cls(**kwargs)

    # ------------------------------------------------------------------ #
    #  Introspection                                                        #
    # ------------------------------------------------------------------ #

    def request_scope(self) -> RequestScope:
        return RequestScope(self)

    def registered_types(self) -> list[type]:
        return list(self._registrations.keys())

    def is_registered(self, abstract: type) -> bool:
        return abstract in self._registrations
