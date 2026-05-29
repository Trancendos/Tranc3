# FID: TRANC3-TEST-017 | Version: 1.0.0 | Module: auth
"""
tests/test_rbac.py — Tests for the Role-Based Access Control system.

Covers Permission enum, RBACManager (built-in roles, hierarchy, custom roles,
grant/revoke), and the require_permission FastAPI dependency factory.

No external dependencies required — pure Python, no CUDA, no torch.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Permission enum
# ---------------------------------------------------------------------------


class TestPermissionEnum:
    def test_permission_values_are_strings(self):
        from src.auth.rbac import Permission

        for p in Permission:
            assert isinstance(p.value, str)

    def test_permission_colon_format(self):
        from src.auth.rbac import Permission

        for p in Permission:
            assert ":" in p.value, f"{p.name} must follow <resource>:<action> format"

    def test_mcp_permissions_exist(self):
        from src.auth.rbac import Permission

        assert Permission.MCP_CALL == "mcp:call"
        assert Permission.MCP_ADMIN == "mcp:admin"

    def test_eval_permissions_exist(self):
        from src.auth.rbac import Permission

        assert Permission.EVAL_SCORE == "eval:score"
        assert Permission.EVAL_ADMIN == "eval:admin"

    def test_knowledge_permissions_exist(self):
        from src.auth.rbac import Permission

        assert Permission.KNOWLEDGE_READ == "knowledge:read"
        assert Permission.KNOWLEDGE_WRITE == "knowledge:write"
        assert Permission.KNOWLEDGE_ADMIN == "knowledge:admin"

    def test_chat_permissions_exist(self):
        from src.auth.rbac import Permission

        assert Permission.CHAT_BASIC == "chat:basic"
        assert Permission.CHAT_ADVANCED == "chat:advanced"
        assert Permission.CHAT_UNLIMITED == "chat:unlimited"

    def test_admin_permissions_exist(self):
        from src.auth.rbac import Permission

        assert Permission.ADMIN_USERS == "admin:users"
        assert Permission.ADMIN_BILLING == "admin:billing"
        assert Permission.ADMIN_CONFIG == "admin:config"
        assert Permission.ADMIN_AUDIT == "admin:audit"

    def test_platform_permissions_exist(self):
        from src.auth.rbac import Permission

        assert Permission.PLATFORM_METRICS == "platform:metrics"
        assert Permission.PLATFORM_SHUTDOWN == "platform:shutdown"
        assert Permission.PLATFORM_SUPERADMIN == "platform:superadmin"

    def test_at_least_17_permissions(self):
        from src.auth.rbac import Permission

        assert len(list(Permission)) >= 17

    def test_permission_usable_as_dict_key(self):
        from src.auth.rbac import Permission

        d = {Permission.MCP_CALL: True}
        assert d[Permission.MCP_CALL] is True

    def test_permission_comparable_to_string(self):
        from src.auth.rbac import Permission

        assert Permission.CHAT_BASIC == "chat:basic"
        assert "admin:users" == Permission.ADMIN_USERS


# ---------------------------------------------------------------------------
# Built-in roles exist
# ---------------------------------------------------------------------------


class TestBuiltInRoles:
    def test_guest_role_exists(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        assert "guest" in mgr.list_roles()

    def test_user_role_exists(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        assert "user" in mgr.list_roles()

    def test_operator_role_exists(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        assert "operator" in mgr.list_roles()

    def test_admin_role_exists(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        assert "admin" in mgr.list_roles()

    def test_superadmin_role_exists(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        assert "superadmin" in mgr.list_roles()

    def test_five_builtin_roles(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        builtin = {"guest", "user", "operator", "admin", "superadmin"}
        assert builtin.issubset(set(mgr.list_roles()))


# ---------------------------------------------------------------------------
# Permission inheritance (hierarchy)
# ---------------------------------------------------------------------------


class TestRoleHierarchy:
    def test_guest_has_chat_basic(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert mgr.has_permission("guest", Permission.CHAT_BASIC)

    def test_user_has_all_guest_permissions(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        guest_perms = mgr.effective_permissions("guest")
        user_perms = mgr.effective_permissions("user")
        for p in guest_perms:
            assert p in user_perms, f"user missing guest permission: {p}"

    def test_operator_has_all_user_permissions(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        user_perms = mgr.effective_permissions("user")
        op_perms = mgr.effective_permissions("operator")
        for p in user_perms:
            assert p in op_perms, f"operator missing user permission: {p}"

    def test_admin_has_all_operator_permissions(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        op_perms = mgr.effective_permissions("operator")
        admin_perms = mgr.effective_permissions("admin")
        for p in op_perms:
            assert p in admin_perms, f"admin missing operator permission: {p}"

    def test_superadmin_has_all_permissions(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        sa_perms = mgr.effective_permissions("superadmin")
        for p in Permission:
            assert p.value in sa_perms, f"superadmin missing permission: {p.value}"

    def test_guest_does_not_have_admin_users(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert not mgr.has_permission("guest", Permission.ADMIN_USERS)

    def test_user_does_not_have_knowledge_write(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert not mgr.has_permission("user", Permission.KNOWLEDGE_WRITE)

    def test_operator_does_not_have_admin_users(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert not mgr.has_permission("operator", Permission.ADMIN_USERS)

    def test_admin_has_knowledge_admin(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert mgr.has_permission("admin", Permission.KNOWLEDGE_ADMIN)

    def test_operator_has_platform_metrics(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert mgr.has_permission("operator", Permission.PLATFORM_METRICS)

    def test_admin_does_not_have_platform_shutdown(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert not mgr.has_permission("admin", Permission.PLATFORM_SHUTDOWN)

    def test_superadmin_has_platform_shutdown(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert mgr.has_permission("superadmin", Permission.PLATFORM_SHUTDOWN)


# ---------------------------------------------------------------------------
# has_permission and check
# ---------------------------------------------------------------------------


class TestHasPermissionAndCheck:
    def test_has_permission_unknown_role_returns_false(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert not mgr.has_permission("nonexistent_role", Permission.CHAT_BASIC)

    def test_check_any_role_grants_permission(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert mgr.check(["guest", "admin"], Permission.ADMIN_USERS)

    def test_check_no_roles_returns_false(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert not mgr.check([], Permission.CHAT_BASIC)

    def test_check_single_role_without_permission(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert not mgr.check(["guest"], Permission.KNOWLEDGE_WRITE)

    def test_check_multiple_roles_first_grants(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        assert mgr.check(["operator", "guest"], Permission.MCP_ADMIN)

    def test_check_string_permission_accepted(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        assert mgr.check(["user"], "mcp:call")

    def test_has_permission_string_permission_accepted(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        assert mgr.has_permission("user", "mcp:call")


# ---------------------------------------------------------------------------
# effective_permissions
# ---------------------------------------------------------------------------


class TestEffectivePermissions:
    def test_returns_frozenset(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        result = mgr.effective_permissions("user")
        assert isinstance(result, frozenset)

    def test_guest_permissions_non_empty(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        assert len(mgr.effective_permissions("guest")) > 0

    def test_superadmin_has_more_permissions_than_admin(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        sa = mgr.effective_permissions("superadmin")
        admin = mgr.effective_permissions("admin")
        assert len(sa) > len(admin)

    def test_unknown_role_raises_value_error(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        with pytest.raises(ValueError, match="Unknown role"):
            mgr.effective_permissions("totally_fake_role")


# ---------------------------------------------------------------------------
# Custom role management
# ---------------------------------------------------------------------------


class TestCustomRoles:
    def test_define_custom_role(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        mgr.define_role("analyst", {Permission.EVAL_SCORE, Permission.KNOWLEDGE_READ})
        assert "analyst" in mgr.list_roles()

    def test_custom_role_has_defined_permissions(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        mgr.define_role("analyst", {Permission.EVAL_SCORE})
        assert mgr.has_permission("analyst", Permission.EVAL_SCORE)

    def test_custom_role_lacks_undefined_permissions(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        mgr.define_role("analyst", {Permission.EVAL_SCORE})
        assert not mgr.has_permission("analyst", Permission.ADMIN_USERS)

    def test_custom_role_with_parent_inherits(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        mgr.define_role("power_user", {Permission.EVAL_ADMIN}, parent_role="user")
        # Should inherit user's permissions too
        assert mgr.has_permission("power_user", Permission.CHAT_BASIC)
        assert mgr.has_permission("power_user", Permission.EVAL_ADMIN)

    def test_override_builtin_role_raises(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        with pytest.raises(ValueError, match="Cannot override built-in role"):
            mgr.define_role("admin", {"some:permission"})

    def test_define_multiple_custom_roles(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        mgr.define_role("roleA", {Permission.CHAT_BASIC})
        mgr.define_role("roleB", {Permission.EVAL_SCORE})
        assert "roleA" in mgr.list_roles()
        assert "roleB" in mgr.list_roles()


# ---------------------------------------------------------------------------
# Grant and revoke
# ---------------------------------------------------------------------------


class TestGrantRevoke:
    def test_grant_permission_to_custom_role(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        mgr.define_role("limited", set())
        mgr.grant_permission("limited", Permission.CHAT_BASIC)
        assert mgr.has_permission("limited", Permission.CHAT_BASIC)

    def test_revoke_permission_from_custom_role(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        mgr.define_role("limited", {Permission.CHAT_BASIC, Permission.MCP_CALL})
        mgr.revoke_permission("limited", Permission.MCP_CALL)
        assert not mgr.has_permission("limited", Permission.MCP_CALL)
        assert mgr.has_permission("limited", Permission.CHAT_BASIC)

    def test_grant_to_unknown_role_raises(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        with pytest.raises(ValueError, match="Unknown role"):
            mgr.grant_permission("ghost_role", Permission.CHAT_BASIC)

    def test_revoke_nonexistent_permission_is_silent(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        mgr.define_role("empty", set())
        # Should not raise
        mgr.revoke_permission("empty", Permission.PLATFORM_SHUTDOWN)

    def test_grant_string_permission(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        mgr.define_role("custom", set())
        mgr.grant_permission("custom", "custom:action")
        assert mgr.has_permission("custom", "custom:action")


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------


class TestIntrospection:
    def test_role_info_returns_dict(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        info = mgr.role_info("user")
        assert isinstance(info, dict)

    def test_role_info_has_required_keys(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        info = mgr.role_info("admin")
        assert "name" in info
        assert "parent_role" in info
        assert "direct_permissions" in info
        assert "effective_permissions" in info

    def test_role_info_name_matches(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        assert mgr.role_info("operator")["name"] == "operator"

    def test_role_info_parent_of_user_is_guest(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        assert mgr.role_info("user")["parent_role"] == "guest"

    def test_role_info_guest_has_no_parent(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        assert mgr.role_info("guest")["parent_role"] is None

    def test_list_roles_returns_list(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        roles = mgr.list_roles()
        assert isinstance(roles, list)

    def test_list_roles_sorted(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        roles = mgr.list_roles()
        assert roles == sorted(roles)

    def test_compare_roles_structure(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        result = mgr.compare_roles("guest", "admin")
        assert "only_in_a" in result
        assert "only_in_b" in result
        assert "shared" in result

    def test_compare_roles_guest_vs_admin_shared(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        result = mgr.compare_roles("guest", "admin")
        # chat:basic is in both
        assert Permission.CHAT_BASIC.value in result["shared"]

    def test_compare_roles_admin_has_admin_users_only(self):
        from src.auth.rbac import Permission, RBACManager

        mgr = RBACManager()
        result = mgr.compare_roles("guest", "admin")
        assert Permission.ADMIN_USERS.value in result["only_in_b"]

    def test_compare_same_role_has_no_diff(self):
        from src.auth.rbac import RBACManager

        mgr = RBACManager()
        result = mgr.compare_roles("user", "user")
        assert result["only_in_a"] == []
        assert result["only_in_b"] == []


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------


class TestGlobalSingleton:
    def test_rbac_manager_singleton_exists(self):
        from src.auth.rbac import RBACManager, rbac_manager

        assert isinstance(rbac_manager, RBACManager)

    def test_singleton_has_builtin_roles(self):
        from src.auth.rbac import rbac_manager

        assert "superadmin" in rbac_manager.list_roles()


# ---------------------------------------------------------------------------
# require_permission FastAPI dependency
# ---------------------------------------------------------------------------


class TestRequirePermission:
    def test_require_permission_returns_depends(self):
        """require_permission() should return a FastAPI Depends object."""
        from fastapi.params import Depends

        from src.auth.rbac import require_permission

        dep = require_permission("admin:users")
        assert isinstance(dep, Depends)

    def _make_request(self, user: dict | None):
        """Build a minimal mock request with request.state.user."""
        req = MagicMock()
        req.state.user = user
        return req

    def test_dependency_passes_for_authorized_user(self):
        import asyncio

        from src.auth.rbac import require_permission

        dep = require_permission("chat:basic")
        # Extract the inner async function from Depends
        inner = dep.dependency
        user = {"user_id": "u1", "roles": ["user"]}
        req = self._make_request(user)
        # Should not raise
        asyncio.run(inner(request=req))

    def test_dependency_raises_403_for_unauthorized(self):
        import asyncio

        from fastapi import HTTPException

        from src.auth.rbac import require_permission

        dep = require_permission("admin:users")
        inner = dep.dependency
        user = {"user_id": "u1", "roles": ["guest"]}
        req = self._make_request(user)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(inner(request=req))
        assert exc_info.value.status_code == 403

    def test_dependency_raises_401_for_no_user(self):
        import asyncio

        from fastapi import HTTPException

        from src.auth.rbac import require_permission

        dep = require_permission("chat:basic")
        inner = dep.dependency
        # Simulate missing user in request state
        req = MagicMock()
        req.state.user = None
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(inner(request=req))
        assert exc_info.value.status_code == 401

    def test_dependency_superadmin_passes_any_permission(self):
        import asyncio

        from src.auth.rbac import require_permission

        dep = require_permission("platform:shutdown")
        inner = dep.dependency
        user = {"user_id": "sa", "roles": ["superadmin"]}
        req = self._make_request(user)
        asyncio.run(inner(request=req))  # should not raise

    def test_dependency_403_detail_mentions_permission(self):
        import asyncio

        from fastapi import HTTPException

        from src.auth.rbac import require_permission

        perm = "knowledge:admin"
        dep = require_permission(perm)
        inner = dep.dependency
        user = {"user_id": "u1", "roles": ["user"]}
        req = self._make_request(user)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(inner(request=req))
        assert perm in exc_info.value.detail

    def test_dependency_falls_back_to_single_role_key(self):
        """Legacy 'role' key (singular) should also work."""
        import asyncio

        from src.auth.rbac import require_permission

        dep = require_permission("mcp:call")
        inner = dep.dependency
        user = {"user_id": "u2", "role": "user"}  # singular 'role' not 'roles'
        req = self._make_request(user)
        asyncio.run(inner(request=req))  # should not raise
