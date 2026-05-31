# src/auth/rbac.py
# Role-Based Access Control (RBAC) guards for protected FastAPI routes.
#
# Provides a ``require_permission(permission)`` dependency factory used by the
# admin / evaluation endpoints in api.py, e.g.:
#
#     @app.get("/admin/audit")
#     async def admin_audit(_perm: None = require_permission("admin:audit")):
#         ...
#
# The check resolves the current user from (in priority order):
#   1. ``request.state.user`` populated by RBACMiddleware from a Bearer JWT
#   2. the standard ``get_current_user`` dependency (also honours test overrides
#      registered via ``app.dependency_overrides[get_current_user]``)
#
# A user whose role is contained in the permission's allowed-role set — or who
# holds the ``admin`` superuser role — is granted access; otherwise a 403 is
# raised.

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

# Imported at module load so FastAPI's dependency_overrides (which match on the
# exact callable object) correctly intercept this same ``get_current_user``.
# auth.py is a leaf module (it imports api lazily), so this is cycle-safe.
from auth import get_current_user

# Permission → set of roles allowed to exercise it.
# The ``admin`` role is an implicit superuser and is always allowed.
_PERMISSION_ROLES: dict[str, set[str]] = {
    "admin:audit": {"admin"},
    "admin:config": {"admin"},
    "admin:users": {"admin"},
    "eval:score": {"admin", "operator"},
}

# Roles that, by prefix, gain access when no explicit mapping exists.
# e.g. any "admin:*" permission requires the "admin" role.
_PREFIX_ROLES: dict[str, set[str]] = {
    "admin:": {"admin"},
    "eval:": {"admin", "operator"},
    "moderation:": {"admin", "moderator"},
}

# The implicit superuser role — always granted every permission.
_SUPERUSER_ROLE = "admin"


def _extract_role(user: Any) -> str:
    """Return the user's role, tolerating both dict and object shapes."""
    if user is None:
        return ""
    if isinstance(user, dict):
        return str(user.get("role") or user.get("tier") or "user")
    return str(getattr(user, "role", None) or getattr(user, "tier", None) or "user")


def _allowed_roles(permission: str) -> set[str]:
    """Resolve the set of roles allowed for a permission (explicit then prefix)."""
    if permission in _PERMISSION_ROLES:
        return _PERMISSION_ROLES[permission]
    for prefix, roles in _PREFIX_ROLES.items():
        if permission.startswith(prefix):
            return roles
    return set()


def _has_permission(user: Any, permission: str) -> bool:
    """True if ``user`` is allowed to exercise ``permission``."""
    role = _extract_role(user)
    if role == _SUPERUSER_ROLE:
        return True
    return role in _allowed_roles(permission)


def require_permission(permission: str):
    """FastAPI dependency factory enforcing that the caller holds ``permission``.

    Returns a ``Depends(...)`` suitable for use as a route parameter default.
    Raises HTTP 403 when the resolved user lacks the required role, or HTTP 401
    when no authenticated user can be resolved.
    """

    async def _checker(
        request: Request,
        current_user: dict = Depends(get_current_user),
    ) -> None:
        # Prefer the middleware-populated user, fall back to the dependency.
        user = getattr(request.state, "user", None) or current_user
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        if not _has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions for '{permission}'",
            )
        return None

    return Depends(_checker)
