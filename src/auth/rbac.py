"""
src/auth/rbac.py — RBAC permission guard for FastAPI dependency injection.

Usage:
    @app.get("/admin/audit")
    async def audit(
        current_user: dict = Depends(get_current_user),
        _perm: None = require_permission("admin:audit"),
    ):
        ...
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

try:
    from auth import get_current_user
except ImportError:
    from src.auth.dependencies import get_current_user  # type: ignore[no-redef]

# Permission → minimum role mapping
_PERMISSION_ROLES: dict[str, set[str]] = {
    "admin:audit": {"admin"},
    "admin:config": {"admin"},
    "admin:users": {"admin"},
    "admin:billing": {"admin"},
    "operator:read": {"admin", "operator"},
    "operator:write": {"admin", "operator"},
    "user:read": {"admin", "operator", "user"},
    "user:write": {"admin", "operator", "user"},
}


def _has_permission(user: dict, permission: str) -> bool:
    user_role = (user.get("role") or user.get("tier") or "user").lower()
    allowed_roles = _PERMISSION_ROLES.get(permission, {"admin"})
    return user_role in allowed_roles


def require_permission(permission: str):
    """
    FastAPI dependency factory that enforces an RBAC permission check.

    Returns a Depends-compatible callable that raises 403 if the current
    user does not hold the required permission.
    """

    async def _guard(current_user: dict = Depends(get_current_user)) -> None:
        if not _has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: '{permission}' required.",
            )

    return Depends(_guard)
