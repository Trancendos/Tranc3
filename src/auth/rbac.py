# FID: TRANC3-AUTH-004 | Version: 1.0.0 | Module: auth
"""
rbac.py — Role-Based Access Control for the Tranc3 / Trancendos platform.

Implements a hierarchical RBAC model with five built-in roles:
  guest → user → operator → admin → superadmin

Each role inherits all permissions of roles below it.  Custom roles can be
created at runtime and granted specific permissions without inheritance.

Permissions follow the format ``<resource>:<action>`` e.g.:
  ``mcp:call``, ``eval:score``, ``admin:users``, ``platform:shutdown``

Usage
-----
    from src.auth.rbac import RBACManager, Permission, require_permission

    rbac = RBACManager()

    # FastAPI dependency injection
    @app.post("/admin/users")
    async def create_user(
        current_user: dict = Depends(get_current_user),
        _: None = Depends(require_permission("admin:users")),
    ):
        ...

Zero-cost: pure Python, no external dependencies.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Dict, FrozenSet, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Permission enum
# ---------------------------------------------------------------------------


class Permission(str, Enum):
    """Canonical platform permissions."""

    # MCP / The Spark
    MCP_CALL = "mcp:call"
    MCP_ADMIN = "mcp:admin"

    # Evaluation
    EVAL_SCORE = "eval:score"
    EVAL_ADMIN = "eval:admin"

    # Knowledge / The Library
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"
    KNOWLEDGE_ADMIN = "knowledge:admin"

    # Chat / inference
    CHAT_BASIC = "chat:basic"
    CHAT_ADVANCED = "chat:advanced"
    CHAT_UNLIMITED = "chat:unlimited"

    # Platform admin
    ADMIN_USERS = "admin:users"
    ADMIN_BILLING = "admin:billing"
    ADMIN_CONFIG = "admin:config"
    ADMIN_AUDIT = "admin:audit"

    # System-level
    PLATFORM_METRICS = "platform:metrics"
    PLATFORM_SHUTDOWN = "platform:shutdown"
    PLATFORM_SUPERADMIN = "platform:superadmin"


# ---------------------------------------------------------------------------
# Built-in role hierarchy
# ---------------------------------------------------------------------------

_ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    "guest": frozenset({
        Permission.CHAT_BASIC,
    }),
    "user": frozenset({
        Permission.CHAT_BASIC,
        Permission.CHAT_ADVANCED,
        Permission.EVAL_SCORE,
        Permission.MCP_CALL,
        Permission.KNOWLEDGE_READ,
    }),
    "operator": frozenset({
        Permission.CHAT_BASIC,
        Permission.CHAT_ADVANCED,
        Permission.CHAT_UNLIMITED,
        Permission.EVAL_SCORE,
        Permission.EVAL_ADMIN,
        Permission.MCP_CALL,
        Permission.MCP_ADMIN,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.PLATFORM_METRICS,
    }),
    "admin": frozenset({
        Permission.CHAT_BASIC,
        Permission.CHAT_ADVANCED,
        Permission.CHAT_UNLIMITED,
        Permission.EVAL_SCORE,
        Permission.EVAL_ADMIN,
        Permission.MCP_CALL,
        Permission.MCP_ADMIN,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.KNOWLEDGE_ADMIN,
        Permission.ADMIN_USERS,
        Permission.ADMIN_BILLING,
        Permission.ADMIN_CONFIG,
        Permission.ADMIN_AUDIT,
        Permission.PLATFORM_METRICS,
    }),
    "superadmin": frozenset({p for p in Permission}),
}

# Ordered role hierarchy (index = power level)
_ROLE_HIERARCHY = ["guest", "user", "operator", "admin", "superadmin"]


# ---------------------------------------------------------------------------
# RBAC manager
# ---------------------------------------------------------------------------


@dataclass
class RoleDefinition:
    name: str
    permissions: Set[str] = field(default_factory=set)
    parent_role: Optional[str] = None  # inherits all parent permissions


class RBACManager:
    """
    Manages roles and permission checks.

    Thread-safe for read operations; mutations should happen at startup
    before serving requests.
    """

    def __init__(self) -> None:
        # Seed with built-in roles
        self._roles: Dict[str, RoleDefinition] = {}
        for role_name, perms in _ROLE_PERMISSIONS.items():
            self._roles[role_name] = RoleDefinition(
                name=role_name,
                permissions=set(perms),
                parent_role=self._parent_of(role_name),
            )

    @staticmethod
    def _parent_of(role_name: str) -> Optional[str]:
        """Return the next lower role in the hierarchy, or None for guest."""
        idx = _ROLE_HIERARCHY.index(role_name) if role_name in _ROLE_HIERARCHY else -1
        return _ROLE_HIERARCHY[idx - 1] if idx > 0 else None

    # ── Custom role management ──────────────────────────────────────────────

    def define_role(
        self,
        name: str,
        permissions: Set[str],
        parent_role: Optional[str] = None,
    ) -> None:
        """Register a custom role.  Raises ValueError if name conflicts with built-ins."""
        if name in _ROLE_PERMISSIONS:
            raise ValueError(f"Cannot override built-in role '{name}'")
        self._roles[name] = RoleDefinition(
            name=name, permissions=set(permissions), parent_role=parent_role
        )
        logger.info("rbac: custom role '%s' defined with %d permissions", name, len(permissions))

    def grant_permission(self, role_name: str, permission: str) -> None:
        """Add a permission to an existing role."""
        role = self._get_role(role_name)
        role.permissions.add(permission)

    def revoke_permission(self, role_name: str, permission: str) -> None:
        """Remove a permission from a role (built-in roles included)."""
        role = self._get_role(role_name)
        role.permissions.discard(permission)

    # ── Permission resolution ───────────────────────────────────────────────

    def _get_role(self, role_name: str) -> RoleDefinition:
        if role_name not in self._roles:
            raise ValueError(f"Unknown role: '{role_name}'")
        return self._roles[role_name]

    def effective_permissions(self, role_name: str) -> FrozenSet[str]:
        """Return all permissions for a role, including inherited ones.

        Raises ValueError for an unknown role so callers can distinguish
        "role exists but has no permissions" from "role does not exist".
        """
        if role_name not in self._roles:
            raise ValueError(f"Unknown role: '{role_name}'")

        visited: Set[str] = set()
        perms: Set[str] = set()

        def _collect(r: str) -> None:
            if r in visited:
                return
            visited.add(r)
            role = self._roles.get(r)
            if role is None:
                return
            perms.update(role.permissions)
            if role.parent_role:
                _collect(role.parent_role)

        _collect(role_name)
        return frozenset(perms)

    def has_permission(self, role_name: str, permission: str) -> bool:
        """Return True if *role_name* (or any parent) grants *permission*."""
        try:
            return permission in self.effective_permissions(role_name)
        except ValueError:
            return False

    def check(self, user_roles: list[str], permission: str) -> bool:
        """Return True if any of the user's roles grant *permission*."""
        return any(self.has_permission(r, permission) for r in user_roles)

    # ── Introspection ───────────────────────────────────────────────────────

    def role_info(self, role_name: str) -> Dict:
        role = self._get_role(role_name)
        return {
            "name": role.name,
            "parent_role": role.parent_role,
            "direct_permissions": sorted(role.permissions),
            "effective_permissions": sorted(self.effective_permissions(role_name)),
        }

    def list_roles(self) -> list[str]:
        return sorted(self._roles.keys())

    def compare_roles(self, role_a: str, role_b: str) -> Dict:
        """Return permissions unique to A, unique to B, and shared."""
        a_perms = self.effective_permissions(role_a)
        b_perms = self.effective_permissions(role_b)
        return {
            "only_in_a": sorted(a_perms - b_perms),
            "only_in_b": sorted(b_perms - a_perms),
            "shared": sorted(a_perms & b_perms),
        }


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

rbac_manager = RBACManager()


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def require_permission(permission: str):
    """FastAPI dependency factory — raises 403 if user lacks the permission.

    Expects ``current_user`` dict in scope with a ``roles`` key (list[str]).
    Compatible with the existing ``get_current_user`` dependency.

    Usage::

        @app.get("/protected")
        async def view(
            current_user: dict = Depends(get_current_user),
            _perm: None = Depends(require_permission("admin:config")),
        ):
            ...
    """
    from fastapi import Depends, HTTPException, Request, status

    async def _dependency(request: Request) -> None:
        # Extract user from request state (set by auth middleware)
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        roles: list[str] = user.get("roles", [user.get("role", "guest")])
        if not rbac_manager.check(roles, permission):
            logger.warning(
                "rbac: access denied user=%s roles=%s permission=%s",
                user.get("user_id", "unknown"),
                roles,
                permission,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )

    return Depends(_dependency)
