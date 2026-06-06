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
import re
from typing import Any, Callable, Optional

from fastapi import Request
from src.observability.observatory import EventCategory, EventSeverity


# ── Input validators ──────────────────────────────────────────────────────────

_DANGEROUS_PATTERNS = re.compile(
    r"(<script|javascript:|on\w+=|DROP\s+TABLE|SELECT\s+\*|INSERT\s+INTO"
    r"|DELETE\s+FROM|UNION\s+SELECT|eval\(|exec\(|__import__"
    r"|ignore\s+previous\s+instructions|disregard\s+previous)",
    re.IGNORECASE,
)


def validate_non_empty(value: str, field_name: str = "field") -> str:
    """Raise ValueError if value is blank after stripping."""
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    return stripped


def validate_safe_string(value: str, field_name: str = "field", max_length: int = 10_000) -> str:
    """Raise ValueError if value contains injection patterns or exceeds max_length."""
    if len(value) > max_length:
        raise ValueError(f"{field_name} exceeds maximum length of {max_length} characters")
    if _DANGEROUS_PATTERNS.search(value):
        raise ValueError(f"{field_name} contains disallowed content")
    return value


def validate_username(username: str) -> str:
    """Alphanumeric + underscore/hyphen, 3–64 chars."""
    username = validate_non_empty(username, "username")
    if not re.fullmatch(r"[a-zA-Z0-9_\-]{3,64}", username):
        raise ValueError("username must be 3–64 alphanumeric characters (underscores and hyphens allowed)")
    return username


def validate_email(email: str) -> str:
    """Basic RFC-5322-ish email check."""
    email = validate_non_empty(email, "email")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("email address is not valid")
    return email.lower()


def validate_port(port: int) -> int:
    """1–65535 range check."""
    if not (1 <= port <= 65535):
        raise ValueError(f"port {port} is out of valid range (1–65535)")
    return port


# ── @audit_action decorator ───────────────────────────────────────────────────

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
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
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
