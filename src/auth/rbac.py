"""Canonical RBAC helpers for FastAPI route dependencies.

This module keeps the permission strings used by ``api.py`` available on the
main branch without depending on the larger Infinity RBAC package layout.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from fastapi import HTTPException, Request, status

_ALL_PERMISSIONS = frozenset({"*"})
_ADMIN_TIERS = frozenset({"business", "enterprise", "admin"})
_EVAL_PERMISSION = "eval:score"

_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": _ALL_PERMISSIONS,
    "operator": frozenset({"admin:audit", "admin:config", _EVAL_PERMISSION}),
    "prime": frozenset({"admin:audit", "admin:config", _EVAL_PERMISSION}),
    "devops": frozenset({"admin:audit", "admin:config", _EVAL_PERMISSION}),
    "developer": frozenset({_EVAL_PERMISSION}),
    "ai": frozenset({_EVAL_PERMISSION}),
    "agent": frozenset({_EVAL_PERMISSION}),
    "service": frozenset({_EVAL_PERMISSION}),
    "user": frozenset({_EVAL_PERMISSION}),
    "bot": frozenset(),
}


def _normalise_values(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        return {values.strip().lower()} if values.strip() else set()
    if isinstance(values, Iterable):
        normalised: set[str] = set()
        for value in values:
            if isinstance(value, str) and value.strip():
                normalised.add(value.strip().lower())
        return normalised
    return set()


def _user_roles(user: Mapping[str, Any]) -> set[str]:
    roles = _normalise_values(user.get("roles"))
    roles |= _normalise_values(user.get("role"))

    tier = str(user.get("tier", "")).strip().lower()
    if tier in _ADMIN_TIERS:
        roles.add("operator")
    elif tier:
        roles.add("user")

    return roles


def get_permissions_for_user(user: Mapping[str, Any]) -> set[str]:
    """Return the effective permission strings for a user mapping."""

    if not user or not user.get("is_active", True):
        return set()

    permissions: set[str] = set()
    for role in _user_roles(user):
        permissions.update(_ROLE_PERMISSIONS.get(role, frozenset()))
    return permissions


def user_has_permission(user: Mapping[str, Any], permission: str) -> bool:
    permissions = get_permissions_for_user(user)
    return "*" in permissions or permission in permissions


def require_permission(permission: str):
    """FastAPI dependency enforcing a named permission from request.state.user."""

    async def _dependency(request: Request) -> None:
        user = getattr(request.state, "user", None)
        if not isinstance(user, Mapping):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        if not user_has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission}",
            )

    return _dependency


__all__ = ["get_permissions_for_user", "require_permission", "user_has_permission"]
