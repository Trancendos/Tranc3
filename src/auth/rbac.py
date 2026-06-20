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

from fastapi import HTTPException, Request, status

# Tier → permission sets (additive, business > pro > free)
_TIER_PERMISSIONS: dict[str, set[str]] = {
    "free": {
        "eval:score",
        "user:read",
        "user:write",
    },
    "pro": {
        "eval:score",
        "user:read",
        "user:write",
        "operator:read",
        "operator:write",
    },
    "business": {
        "eval:score",
        "user:read",
        "user:write",
        "operator:read",
        "operator:write",
        "admin:audit",
        "admin:config",
        "admin:users",
        "admin:billing",
    },
}

# Role → wildcards (admin gets everything)
_ROLE_WILDCARDS: set[str] = {"admin"}


def get_permissions_for_user(user: dict) -> set[str]:
    """Return the full set of permissions for a user dict."""
    role = (user.get("role") or "").lower()
    if role in _ROLE_WILDCARDS:
        return set(_TIER_PERMISSIONS["business"]) | {"*"}
    tier = (user.get("tier") or "free").lower()
    return set(_TIER_PERMISSIONS.get(tier, _TIER_PERMISSIONS["free"]))


def user_has_permission(user: dict, permission: str) -> bool:
    """Return True if the user holds the given permission."""
    perms = get_permissions_for_user(user)
    return "*" in perms or permission in perms


def _has_permission(user: dict, permission: str) -> bool:
    return user_has_permission(user, permission)


def require_permission(permission: str):
    """
    FastAPI dependency factory that enforces an RBAC permission check.

    Reads user from request.state.user (set by auth middleware).
    Raises 401 if no user present, 403 if permission denied.
    """

    async def _guard(request: Request) -> None:
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        if not user_has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission}",
            )

    return _guard
