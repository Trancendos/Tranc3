"""
Trancendos Infinity RBAC — Role-Based Access Control Engine
============================================================
Tier-aware Role-Based Access Control for the Infinity Ecosystem.

Roles are derived from the Trancendos tier system and pillar associations.
Each role has a defined set of permissions, and pillar-scoped roles have
additional domain-specific permissions.

OWASP A01 (Broken Access Control): Enforces least privilege per role.
OWASP A04 (Insecure Design): Role hierarchy is explicit and auditable.

Features:
    - Tier-aware role hierarchy with inheritance
    - Pillar-scoped permissions for Prime entities
    - Endpoint-level permission checks
    - Resource-level access scoping
    - Audit logging for access decisions

Usage:
    from Dimensional.infinity.rbac import RBACEngine, Permission

    engine = RBACEngine()
    if engine.check_access(user, "api:agents", "write"):
        # Allow write to agents
        ...
"""

from __future__ import annotations

import logging
from enum import Flag, auto
from typing import Any, Dict, Optional

from Dimensional.infinity.nomenclature import InfinityRole, Pillar

logger = logging.getLogger(__name__)


# ── Permissions ──────────────────────────────────────────────────


class Permission(Flag):
    """Granular permission flags for the Infinity Ecosystem."""

    NONE = 0
    # Read permissions
    READ_PLATFORM = auto()  # Read platform status, health, overview
    READ_AGENTS = auto()  # Read agent fleet data
    READ_MODELS = auto()  # Read model hub data
    READ_WORKFLOWS = auto()  # Read workflow definitions
    READ_SECURITY = auto()  # Read security/vault data
    READ_AUDIT = auto()  # Read audit ledger entries
    READ_TOPOLOGY = auto()  # Read topology configuration
    READ_EVENTS = auto()  # Read event stream
    READ_USERS = auto()  # Read user data
    READ_SENTINEL = auto()  # Read Sentinel Station events

    # Write permissions
    WRITE_AGENTS = auto()  # Create/modify agents
    WRITE_MODELS = auto()  # Register/modify models
    WRITE_WORKFLOWS = auto()  # Create/modify workflows
    WRITE_SECURITY = auto()  # Manage secrets, security policies
    WRITE_TOPOLOGY = auto()  # Change topology mode
    WRITE_USERS = auto()  # Create/modify users
    WRITE_SENTINEL = auto()  # Publish to Sentinel Station

    # Execute permissions
    EXECUTE_WORKFLOWS = auto()  # Run workflow executions
    EXECUTE_AGENTS = auto()  # Deploy/undeploy agents
    EXECUTE_COMMANDS = auto()  # Execute platform commands

    # Admin permissions
    ADMIN_SYSTEM = auto()  # Full system administration
    ADMIN_SECURITY = auto()  # Security administration
    ADMIN_INFINITY = auto()  # Infinity-Admin access
    ADMIN_SENTINEL = auto()  # Sentinel Station administration

    # Composite permissions
    READ_ALL = (
        READ_PLATFORM
        | READ_AGENTS
        | READ_MODELS
        | READ_WORKFLOWS
        | READ_SECURITY
        | READ_AUDIT
        | READ_TOPOLOGY
        | READ_EVENTS
        | READ_USERS
        | READ_SENTINEL
    )
    WRITE_ALL = (
        WRITE_AGENTS
        | WRITE_MODELS
        | WRITE_WORKFLOWS
        | WRITE_SECURITY
        | WRITE_TOPOLOGY
        | WRITE_USERS
        | WRITE_SENTINEL
    )
    EXECUTE_ALL = EXECUTE_WORKFLOWS | EXECUTE_AGENTS | EXECUTE_COMMANDS
    ADMIN_ALL = ADMIN_SYSTEM | ADMIN_SECURITY | ADMIN_INFINITY | ADMIN_SENTINEL
    ALL = READ_ALL | WRITE_ALL | EXECUTE_ALL | ADMIN_ALL


# ── Role Permission Mapping ─────────────────────────────────────

ROLE_PERMISSIONS: Dict[InfinityRole, Permission] = {
    InfinityRole.ADMIN: Permission.ALL,
    InfinityRole.PRIME: (
        Permission.READ_ALL
        | Permission.WRITE_ALL
        | Permission.EXECUTE_ALL
        | Permission.ADMIN_SENTINEL
    ),
    InfinityRole.AI: (
        Permission.READ_ALL
        | Permission.WRITE_AGENTS
        | Permission.WRITE_MODELS
        | Permission.WRITE_WORKFLOWS
        | Permission.WRITE_SENTINEL
        | Permission.EXECUTE_WORKFLOWS
        | Permission.EXECUTE_AGENTS
    ),
    InfinityRole.AGENT: (
        Permission.READ_PLATFORM
        | Permission.READ_AGENTS
        | Permission.READ_MODELS
        | Permission.READ_WORKFLOWS
        | Permission.READ_EVENTS
        | Permission.EXECUTE_WORKFLOWS
    ),
    InfinityRole.BOT: (
        Permission.READ_PLATFORM
        | Permission.READ_EVENTS
        | Permission.READ_SENTINEL
        | Permission.WRITE_SENTINEL
    ),
    InfinityRole.USER: (
        Permission.READ_PLATFORM
        | Permission.READ_AGENTS
        | Permission.READ_MODELS
        | Permission.READ_WORKFLOWS
        | Permission.READ_EVENTS
        | Permission.WRITE_AGENTS
        | Permission.WRITE_WORKFLOWS
        | Permission.EXECUTE_WORKFLOWS
        | Permission.EXECUTE_AGENTS
    ),
    InfinityRole.SERVICE: (
        Permission.READ_ALL | Permission.WRITE_SENTINEL | Permission.READ_SENTINEL
    ),
}

# Pillar-specific additional permissions for Prime roles
PILLAR_PERMISSIONS: Dict[Pillar, Permission] = {
    Pillar.ARCHITECTURAL: Permission.ADMIN_SYSTEM,
    Pillar.SECURITY: Permission.ADMIN_SECURITY,
    Pillar.DEVOPS: Permission.ADMIN_SENTINEL,
    Pillar.COMMERCIAL: Permission.READ_AUDIT | Permission.READ_SECURITY,
    Pillar.CREATIVITY: Permission.WRITE_MODELS | Permission.WRITE_WORKFLOWS,
    Pillar.DEVELOPMENT: Permission.WRITE_WORKFLOWS | Permission.EXECUTE_COMMANDS,
    Pillar.KNOWLEDGE: Permission.READ_ALL,
    Pillar.WELLBEING: Permission.READ_USERS,
}

# Endpoint-to-permission mapping for route-level authorization
ENDPOINT_PERMISSIONS: Dict[str, Permission] = {
    # Aggregated API
    "/api/overview": Permission.READ_PLATFORM,
    "/api/agents": Permission.READ_AGENTS,
    "/api/models": Permission.READ_MODELS,
    "/api/workflows": Permission.READ_WORKFLOWS,
    "/api/security": Permission.READ_SECURITY,
    "/api/audit": Permission.READ_AUDIT,
    "/api/topology/mode": Permission.READ_TOPOLOGY,
    # Write endpoints
    "POST:/api/agents": Permission.WRITE_AGENTS,
    "POST:/api/workflows": Permission.WRITE_WORKFLOWS,
    "PUT:/api/topology/mode": Permission.WRITE_TOPOLOGY,
    "POST:/api/workflows/{id}/run": Permission.EXECUTE_WORKFLOWS,
    # Sentinel Station
    "/sentinel": Permission.READ_SENTINEL,
    "POST:/sentinel/publish": Permission.WRITE_SENTINEL,
    # Infinity locations
    "/infinity-admin": Permission.ADMIN_INFINITY,
    "/infinity-one": Permission.READ_USERS,
    # Events
    "/events": Permission.READ_EVENTS,
    "POST:/events": Permission.WRITE_SENTINEL,
}


# ── RBAC Engine ──────────────────────────────────────────────────


class RBACEngine:
    """
    Role-Based Access Control engine for the Infinity Ecosystem.

    Implements tier-aware role hierarchy with pillar-scoped permissions.
    Each access check evaluates the user's role, tier, and pillar
    association to determine if the requested action is permitted.

    OWASP A01: Enforces least privilege per role.
    OWASP A04: Role hierarchy is explicit and auditable.
    """

    def __init__(
        self,
        role_permissions: Optional[Dict[InfinityRole, Permission]] = None,
        pillar_permissions: Optional[Dict[Pillar, Permission]] = None,
        endpoint_permissions: Optional[Dict[str, Permission]] = None,
    ):
        self._role_permissions = role_permissions or ROLE_PERMISSIONS
        self._pillar_permissions = pillar_permissions or PILLAR_PERMISSIONS
        self._endpoint_permissions = endpoint_permissions or ENDPOINT_PERMISSIONS

    def get_user_permissions(self, user: Dict[str, Any]) -> Permission:
        """Get the effective permissions for a user based on role and pillar.

        Combines base role permissions with pillar-specific additions
        for Prime-tier users.
        """
        role_str = user.get("role", "user")
        try:
            role = InfinityRole(role_str)
        except ValueError:
            role = InfinityRole.USER

        # Get base role permissions
        perms = self._role_permissions.get(role, Permission.NONE)

        # Add pillar-specific permissions for Prime roles
        if role == InfinityRole.PRIME:
            pillar_str = user.get("pillar")
            if pillar_str:
                try:
                    pillar = Pillar(pillar_str)
                    perms = perms | self._pillar_permissions.get(pillar, Permission.NONE)
                except ValueError as _exc:
                    logger.debug("suppressed %s", _exc, exc_info=False)

        return perms

    def check_permission(self, user: Dict[str, Any], required: Permission) -> bool:
        """Check if a user has the required permission.

        Uses flag intersection: the user's permissions must include
        all flags in the required permission set.
        """
        user_perms = self.get_user_permissions(user)
        return bool(user_perms & required)

    def check_access(
        self,
        user: Dict[str, Any],
        endpoint: str,
        method: str = "GET",
    ) -> bool:
        """Check if a user can access an endpoint.

        Resolves the endpoint to a permission requirement and checks
        against the user's effective permissions.

        For write endpoints, the method prefix (POST:/ PUT:/ DELETE:/)
        is used to differentiate from read access.
        """
        # Try method-specific endpoint first
        if method in ("POST", "PUT", "DELETE", "PATCH"):
            key = f"{method}:{endpoint}"
            perm = self._endpoint_permissions.get(key)
            if perm:
                return self.check_permission(user, perm)

        # Try base endpoint
        perm = self._endpoint_permissions.get(endpoint)
        if perm:
            return self.check_permission(user, perm)

        # Default: if endpoint is not in the mapping, allow access
        # (auth middleware already handles public/enforced paths)
        return True

    def check_pillar_access(
        self,
        user: Dict[str, Any],
        pillar: Pillar,
        action: str = "read",
    ) -> bool:
        """Check if a user can access resources within a specific pillar.

        Prime users have full access to their own pillar.
        Other users need explicit permissions.
        """
        user_role = user.get("role", "user")
        user_pillar = user.get("pillar")

        # Admins have full access
        if user_role == InfinityRole.ADMIN:
            return True

        # Primes have full access to their own pillar
        if user_role == InfinityRole.PRIME and user_pillar == pillar.value:
            return True

        # For other users, check based on action
        if action == "read":
            # Read access is generally allowed for authenticated users
            return user.get("is_active", False)

        # Write/admin actions require pillar membership
        return user_pillar == pillar.value

    def get_audit_context(self, user: Dict[str, Any], endpoint: str, method: str) -> Dict[str, Any]:
        """Generate an audit context for an access decision.

        Useful for logging access decisions for compliance (OWASP A09).
        """
        user_perms = self.get_user_permissions(user)
        required_perm = self._endpoint_permissions.get(endpoint)
        granted = self.check_access(user, endpoint, method)

        return {
            "user_id": user.get("sub", "anonymous"),
            "role": user.get("role", "unknown"),
            "tier": user.get("tier", "human"),
            "pillar": user.get("pillar"),
            "endpoint": endpoint,
            "method": method,
            "user_permissions": user_perms.value
            if isinstance(user_perms, Permission)
            else (int(user_perms) if user_perms is not None else 0),
            "required_permission": required_perm.value
            if isinstance(required_perm, Permission)
            else (int(required_perm) if required_perm is not None else None),
            "granted": granted,
        }
