# tests/test_dimensional_auth_middleware.py
# Regression tests for Dimensional/middleware/auth.py's AuthMiddleware.
#
# This middleware is not currently mounted anywhere live (only referenced from
# the already-archived archive/api_ecosystem.py), but a cubic-dev-ai review
# flagged two bugs in it after it was touched to fix the same dead
# token_manager/user_manager import pattern as src/security/middleware.py:
#   1. The JWT's "role" claim was dropped entirely when building request.state.user,
#      so require_permission() (src/auth/rbac.py) would deny admin-only permissions
#      for JWT-authenticated admins.
#   2. create_access_token() (src/auth/tokens.py) stores "tier" as an int (default
#      0), but the middleware did `payload.get("tier", "free")` and stored it
#      verbatim — src/auth/rbac.py's get_permissions_for_user() calls
#      `.lower()` on that value, which raises AttributeError on an int rather
#      than returning an authorization decision.

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import create_token
from Dimensional.middleware.auth import AuthMiddleware
from src.auth.rbac import get_permissions_for_user


@pytest.fixture
def app_with_state_route(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-for-unit-tests-00002")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-unit-tests-00002")

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/protected")
    async def protected(request: Request):
        user = getattr(request.state, "user", None)
        return {"user": user}

    with TestClient(app) as c:
        yield c


class TestAuthMiddlewarePreservesRoleAndTier:
    def test_admin_role_survives_into_request_state_user(self, app_with_state_route):
        token = create_token(user_id="u1", username="alice", role="admin")
        resp = app_with_state_route.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        user = resp.json()["user"]
        assert user["role"] == "admin"

    def test_admin_role_grants_wildcard_permission_through_rbac(self, app_with_state_route):
        token = create_token(user_id="u1", username="alice", role="admin")
        resp = app_with_state_route.get("/protected", headers={"Authorization": f"Bearer {token}"})
        user = resp.json()["user"]
        assert "*" in get_permissions_for_user(user)

    def test_default_role_is_user(self, app_with_state_route):
        token = create_token(user_id="u2", username="bob")
        resp = app_with_state_route.get("/protected", headers={"Authorization": f"Bearer {token}"})
        user = resp.json()["user"]
        assert user["role"] == "user"

    def test_numeric_tier_does_not_crash_permission_lookup(self, app_with_state_route):
        # create_access_token() always stores tier as an int — this must not
        # raise AttributeError when downstream RBAC code calls .lower() on it.
        token = create_token(user_id="u3", username="carol", tier=1)
        resp = app_with_state_route.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        user = resp.json()["user"]
        assert isinstance(user["tier"], str)
        # No established int->tier-name mapping exists anywhere in the
        # codebase, so an unrecoverable numeric tier fails closed to "free"
        # rather than guessing "pro"/"business".
        assert user["tier"] == "free"
        get_permissions_for_user(user)  # must not raise
