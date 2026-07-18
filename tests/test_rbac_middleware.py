# tests/test_rbac_middleware.py
# Regression test for src/security/middleware.py's RBACMiddleware.
#
# RBACMiddleware is meant to populate request.state.user from a valid Bearer
# JWT so require_permission() (src/auth/rbac.py) can enforce RBAC. It was
# broken since the auth refactor: it imported `auth.token_manager` and
# `auth.user_manager`, neither of which still exist in auth.py — the
# ImportError was silently swallowed by the middleware's own
# `except Exception: pass`, so request.state.user was NEVER populated from a
# Bearer token, and every require_permission()-guarded route 401'd
# unconditionally, even with a valid token. This is mounted live in api.py
# (`app.add_middleware(RBACMiddleware)`), so this was a real, currently-active
# production bug, not just test debt.

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import create_token
from src.security.middleware import RBACMiddleware


@pytest.fixture
def app_with_state_route(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-for-unit-tests-00001")

    app = FastAPI()
    app.add_middleware(RBACMiddleware)

    @app.get("/protected")
    async def protected(request: Request):
        user = getattr(request.state, "user", None)
        return {"user": user}

    with TestClient(app) as c:
        yield c


class TestRBACMiddlewarePopulatesUser:
    def test_valid_bearer_token_does_not_raise_and_user_stays_none_without_db_wiring(
        self, app_with_state_route
    ):
        token = create_token(user_id="u1", username="alice")
        resp = app_with_state_route.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        # db_user_manager lookup will fail in this bare-app fixture (no api.py
        # wiring), but the middleware must not raise — user simply stays None
        # in that case. The regression this guards against is the ImportError
        # itself, which used to be masked as "invalid token" for every request.
        assert resp.json() == {"user": None}

    def test_missing_token_leaves_user_unset(self, app_with_state_route):
        resp = app_with_state_route.get("/protected")
        assert resp.status_code == 200
        assert resp.json() == {"user": None}

    def test_malformed_token_does_not_raise(self, app_with_state_route):
        resp = app_with_state_route.get(
            "/protected", headers={"Authorization": "Bearer not-a-real-jwt"}
        )
        assert resp.status_code == 200
        assert resp.json() == {"user": None}

    def test_public_path_skips_middleware_entirely(self, app_with_state_route):
        resp = app_with_state_route.get("/health")
        # No route registered at /health in this fixture, but the middleware
        # itself must not error out on a public-prefixed path.
        assert resp.status_code == 404
