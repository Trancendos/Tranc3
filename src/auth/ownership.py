# src/auth/ownership.py
"""Shared per-user-resource ownership check.

Mirrors api.py's gdpr_erase() ownership check: users may act on their own
data; admins may act on any user's data. Used by every router that scopes a
resource to a user_id (tranquility, taimra, resonate, vrar3d).
"""

from __future__ import annotations

from fastapi import HTTPException


def require_self_or_admin(user_id: str, current_user: dict) -> None:
    """Real JWT payloads (src/auth/tokens.py) carry the caller's identity
    under the standard "sub" claim, not "id" — accept either so this doesn't
    500 for genuine callers with real tokens. The "enterprise" override this
    originally mirrored from gdpr_erase() checked `tier == "enterprise"`, but
    real tokens carry `tier` as a numeric int (never that string) — checking
    `role == "admin"` instead uses a claim real tokens actually carry."""
    caller_id = current_user.get("id") or current_user.get("sub")
    if caller_id != user_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Can only access your own data")
