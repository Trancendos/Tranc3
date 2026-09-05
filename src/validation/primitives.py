"""Pure input validators — importable with nothing but the standard library.

Why this is a separate module
-----------------------------
These six functions are `re` and `str` and nothing else, and they are used
by CI scripts, by the Town Hall's registries, and by workers whose build
context excludes the web framework. They lived in `validators.py` beside
`audit_action`, which needs FastAPI and The Observatory — so importing
`validate_non_empty` pulled in a chain that ends at `aiohttp` and
`structlog`, and a GitHub runner installing only PyYAML and pydantic could
not import them at all.

`validators.py` re-exports everything here, so no caller has to change and
there is still exactly one implementation of each check.
"""

from __future__ import annotations

import re

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
        raise ValueError(
            "username must be 3–64 alphanumeric characters (underscores and hyphens allowed)"
        )
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
