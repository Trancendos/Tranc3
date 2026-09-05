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

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import Request

    from src.observability.observatory import EventCategory, EventSeverity

# Neither `fastapi` nor The Observatory is imported at module level. This
# module's validators are small pure functions used by CI scripts and by
# workers whose build context excludes the web framework, and a top-level
# `from fastapi import Request` made all of them unimportable without it —
# which is how the backlog generator came to fail on a GitHub runner that
# installs only PyYAML and pydantic.
#
# Moving the pure functions into `primitives.py` was only half the fix. The
# four modules that import them from *here* — `src/auth/db_user_manager.py`,
# `src/relations/registry.py`, `src/notebooks/registry.py` and
# `src/roles/registry.py` — still executed this module, and the
# `EventCategory`/`EventSeverity` import at the top of it still ended at
# `aiohttp` and `structlog`. So the re-export below did not make this module
# importable without the chain; it only meant no caller had to change its
# import line. The enum import is now deferred to `decorator()`, which runs
# when a route module applies `@audit_action` — and a route module has
# FastAPI and The Observatory by definition. `from __future__ import
# annotations` keeps every annotation a string, so nothing else needs them.

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
    category: Optional["EventCategory"] = None,
    severity: Optional["EventSeverity"] = None,
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
        category: Observatory EventCategory; None means EventCategory.DATA
        severity: Observatory EventSeverity; None means EventSeverity.INFO
        service: Trancendos service name
        target_fn: Optional callable(kwargs) → str to derive the target from route args
    """

    def decorator(fn: Callable) -> Callable:
        # Resolved here, not in the signature: a default of
        # `EventCategory.DATA` would need the enum at *this* module's import
        # time, which is exactly the dependency chain this module now avoids.
        # `decorator` runs when a route module applies the decorator, and a
        # route module already imports The Observatory.
        from src.observability.observatory import (  # noqa: PLC0415
            EventCategory as _EventCategory,
        )
        from src.observability.observatory import (  # noqa: PLC0415
            EventSeverity as _EventSeverity,
        )

        resolved_category = _EventCategory.DATA if category is None else category
        resolved_severity = _EventSeverity.INFO if severity is None else severity

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
                        category=resolved_category,
                        severity=resolved_severity,
                        service=service,
                        outcome=outcome,
                        session_id=session_id,
                    )
                except Exception:
                    pass  # Never let audit logging break route execution

        return wrapper

    return decorator
