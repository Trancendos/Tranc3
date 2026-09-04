from __future__ import annotations

import json

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from src.auth.rbac import get_permissions_for_user, require_permission, user_has_permission
from tests.support.routes import mounted_routes


def _make_client() -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def inject_user(request: Request, call_next):
        raw_user = request.headers.get("x-test-user")
        if raw_user:
            request.state.user = json.loads(raw_user)
        return await call_next(request)

    @app.get("/admin/audit")
    async def admin_audit(_perm: None = Depends(require_permission("admin:audit"))):
        return {"ok": True}

    @app.get("/eval")
    async def eval_score(_perm: None = Depends(require_permission("eval:score"))):
        return {"ok": True}

    return TestClient(app)


class TestPermissionHelpers:
    def test_business_tier_gets_admin_permissions(self):
        permissions = get_permissions_for_user({"tier": "business", "is_active": True})
        assert "admin:audit" in permissions
        assert "admin:config" in permissions
        assert "eval:score" in permissions

    def test_free_tier_does_not_get_admin_permissions(self):
        permissions = get_permissions_for_user({"tier": "free", "is_active": True})
        assert "admin:audit" not in permissions
        assert "admin:config" not in permissions
        assert "eval:score" in permissions

    def test_admin_role_gets_wildcard_permissions(self):
        assert user_has_permission({"role": "admin", "is_active": True}, "admin:config")
        assert user_has_permission({"role": "admin", "is_active": True}, "totally:new:permission")


class TestRequirePermissionDependency:
    def test_missing_user_requires_authentication(self):
        client = _make_client()
        response = client.get("/admin/audit")
        assert response.status_code == 401
        assert response.json() == {"detail": "Authentication required"}

    def test_free_tier_cannot_access_admin_permission(self):
        client = _make_client()
        response = client.get(
            "/admin/audit",
            headers={"x-test-user": json.dumps({"tier": "free", "is_active": True})},
        )
        assert response.status_code == 403
        assert response.json() == {"detail": "Missing permission: admin:audit"}

    def test_business_tier_can_access_admin_permission(self):
        client = _make_client()
        response = client.get(
            "/admin/audit",
            headers={"x-test-user": json.dumps({"tier": "business", "is_active": True})},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_authenticated_user_can_access_eval_permission(self):
        client = _make_client()
        response = client.get(
            "/eval",
            headers={"x-test-user": json.dumps({"tier": "free", "is_active": True})},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}


class TestNoRouteMisusesRequirePermission:
    """No route may pass the bare guard as a default value.

    ``require_permission()`` returns a guard that must be wrapped in
    ``Depends(...)``. Written bare -- ``_perm: None = require_permission(...)``
    -- FastAPI reads the ``None`` annotation and registers ``_perm`` as a *query
    parameter*, so every request 422s during validation and the guard never runs.
    The route then looks protected while actually being unreachable and
    unenforced. Seven routes in api.py shipped that way; this catches a
    recurrence by inspecting the real app's registered parameters.
    """

    def test_no_registered_route_takes_a_callable_as_a_query_parameter(self):
        """Detect the bug by its shape, not by the parameter's name.

        Matching only ``_perm`` would miss a route that called the parameter
        anything else and reintroduced the identical defect. The real signature
        is a *query parameter whose default is a callable* — no legitimate query
        parameter defaults to a function, so that catches the guard regardless of
        what it is named.
        """
        import os
        from unittest.mock import MagicMock, patch

        import pytest

        if not os.getenv("SECRET_KEY"):
            pytest.skip("SECRET_KEY env var not set")
        try:
            with patch("redis.from_url", return_value=MagicMock(ping=lambda: True)):
                from api import app
        except ModuleNotFoundError as e:
            pytest.skip(f"missing production dependency: {e}")

        offenders = []
        for route in mounted_routes(app):
            dependant = getattr(route, "dependant", None)
            if not dependant:
                continue
            for param in dependant.query_params:
                if callable(getattr(param.field_info, "default", None)):
                    offenders.append(f"{sorted(route.methods)} {route.path} ({param.name})")
        assert not offenders, (
            "these routes pass a dependency callable as a plain default, so FastAPI "
            "registers it as a query parameter and 422s every request before the "
            f"guard runs — wrap it in Depends(...): {offenders}"
        )
