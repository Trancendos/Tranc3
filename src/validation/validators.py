"""
Platform-wide input validators and the @audit_action decorator.

@audit_action enforces that any route annotated with it emits an AuditEvent
to The Observatory automatically — even if the route handler itself doesn't
call observe() manually.

Usage:
    from src.validation.validators import audit_action, validate_non_empty

    @app.post("/secrets/retrieve")
    @audit_action("secret.retrieve", category=EventCategory.SECRETS, severity=EventSeverity.SECURITY)
    async def retrieve_secret(request: Request, payload: SecretRequest):
        ...
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Callable, Optional

from src.observability.observatory import EventCategory, EventSeverity

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import Request

# `fastapi` is NOT imported at module level. This module's validators are
# small pure functions used by CI scripts and by workers whose build context
# excludes the web framework, and a top-level `from fastapi import Request`
# made all of them unimportable without it — which is how the backlog
# generator came to fail on a GitHub runner that installs only PyYAML and
# pydantic. `audit_action` needs the real class at request time and imports
# it inside the wrapper; `from __future__ import annotations` keeps the
# annotation a string, so nothing else needs it.
#
# The Observatory import above IS at module level, and deliberately so.
# Moving the pure validators into `primitives.py` was only half that fix:
# the four modules importing them from *here* — `src/auth/db_user_manager.py`,
# `src/relations/registry.py`, `src/notebooks/registry.py` and
# `src/roles/registry.py` — still executed this module, and this import
# still ended at `aiohttp` and `structlog`. Deferring it into `decorator()`
# fixed that but broke the public signature: with the enums out of the
# module namespace, `typing.get_type_hints(audit_action)` raised NameError,
# because `EventCategory` in the annotation no longer resolved.
#
# Both are fixed at the actual source. `observatory.py` is standard library
# plus one in-repo helper; the weight was entirely in `src/observability/
# __init__.py`, which eagerly imported metrics, tracing and health to offer
# 25 convenience names that nothing in the repository imports. Those are now
# resolved on demand (PEP 562), so this import costs what it always looked
# like it cost, and the annotations resolve at runtime again.

# The pure validators live in `primitives.py` so they can be imported without
# this module's FastAPI and Observatory chain — which ends at aiohttp and
# structlog, and made them unusable from a CI script or a slim worker. They
# are re-exported here so no caller had to change.
from src.validation.primitives import (  # noqa: E402
    _DANGEROUS_PATTERNS,
    validate_email,
    validate_non_empty,
    validate_port,
    validate_safe_string,
    validate_username,
)

__all__ = [
    "_DANGEROUS_PATTERNS",
    "audit_action",
    "validate_email",
    "validate_non_empty",
    "validate_port",
    "validate_safe_string",
    "validate_username",
]


# ── Audit decorator ───────────────────────────────────────────────────────────


def audit_action(
    event_type: str,
    *,
    category: EventCategory = EventCategory.DATA,
    severity: EventSeverity = EventSeverity.INFO,
    service: str = "tranc3-backend",
    target_fn: Optional[Callable[..., str]] = None,
) -> Callable:
    """
    Decorator that automatically records an AuditEvent to The Observatory
    after the decorated async route handler completes.

    The decorated function MUST receive a FastAPI Request as its first
    positional argument (or as keyword argument named 'request').

    Args:
        event_type: dot-notation event identifier, e.g. "secret.retrieve"
        category: Observatory EventCategory
        severity: Observatory EventSeverity
        service: Trancendos service name
        target_fn: Optional callable(kwargs) → str to derive the target from route args

    Raises:
        TypeError: if `category` or `severity` is not the enum it claims to
            be — including `None`.
    """
    # Checked here, at decoration time, rather than coerced at record time.
    #
    # The defaults are real enums, so `None` only arrives when a caller
    # passes it explicitly — typically from a config lookup that came back
    # empty. Substituting the default would then write an audit record
    # categorised `DATA` for an event the caller meant to categorise
    # otherwise, and the record would look entirely valid. In an audit log
    # that is the worst outcome available: a wrong fact, indistinguishable
    # from a right one, written by the system whose job is to be the record
    # of what happened. Letting `None` through instead reaches
    # `Observatory.record`, where the `finally` block below swallows the
    # AttributeError — so the event is simply not recorded, silently.
    #
    # A decorator's arguments are a programming error, not a runtime input:
    # this runs when a route module is imported, so a bad one stops the
    # service at startup with the offending line in the traceback, and can
    # never affect a live request. A bare string is refused for the same
    # reason — `EventCategory` subclasses `str`, so `"data"` would pass an
    # `isinstance(..., str)` check and still not be a category.
    for name, value, enum in (
        ("category", category, EventCategory),
        ("severity", severity, EventSeverity),
    ):
        if not isinstance(value, enum):
            raise TypeError(
                f"audit_action({event_type!r}): {name} must be an "
                f"{enum.__name__}, got {value!r}. Pass the enum member "
                f"(e.g. {enum.__name__}.{next(iter(enum)).name}) or omit the "
                "argument to take the default."
            )

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            from fastapi import Request  # noqa: PLC0415 - see the note above

            # Extract FastAPI Request from positional or keyword args
            request: Optional[Request] = None
            for a in args:
                if isinstance(a, Request):
                    request = a
                    break
            if request is None:
                request = kwargs.get("request")

            actor = "system"
            actor_ip = None
            session_id = None
            if request is not None:
                from src.observability.audit_middleware import _extract_actor

                actor = _extract_actor(request)
                actor_ip = request.client.host if request.client else None
                session_id = getattr(request.state, "request_id", None)

            target = target_fn(**kwargs) if target_fn else None
            outcome = "success"

            try:
                result = await fn(*args, **kwargs)
                return result
            except Exception:
                outcome = "failure"
                raise
            finally:
                try:
                    from src.observability.observatory import get_observatory

                    get_observatory().record(
                        event_type,
                        actor=actor,
                        actor_ip=actor_ip,
                        target=target,
                        category=category,
                        severity=severity,
                        service=service,
                        outcome=outcome,
                        session_id=session_id,
                    )
                except Exception:
                    pass  # Never let audit logging break route execution

        return wrapper

    return decorator
