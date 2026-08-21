"""HTTP-level tests for POST /basement/promote.

This route is the only entry point to `src/basement/promotion.py`, which
implements the Basement -> Library leg of the learning pipeline and, until it
was wired, was called by nothing at all. Adding an untested route to reach
previously unreachable code would only move the gap rather than close it, so
the guard and both promotion modes are exercised here.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.basement import routes as basement_routes


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(basement_routes.router)
    with TestClient(app) as c:
        yield c
    c.app.dependency_overrides.clear()


def _as(role: str):
    def _dep():
        return {"sub": "u1", "role": role}

    return _dep


class TestPromoteGuard:
    def test_unauthenticated_is_refused(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        assert client.post("/basement/promote").status_code in (401, 403)

    def test_ordinary_user_is_refused(self, client):
        """Reading the evidence store is open to any authenticated caller;
        authoring Library articles from it is not."""
        client.app.dependency_overrides[get_current_user] = _as("user")
        resp = client.post("/basement/promote")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin role required"

    def test_admin_is_allowed(self, client):
        client.app.dependency_overrides[get_current_user] = _as("admin")
        assert client.post("/basement/promote", params={"dry_run": True}).status_code == 200


class TestPromoteBehaviour:
    def test_dry_run_reports_without_writing(self, client, monkeypatch):
        seen: dict = {}

        def _fake(limit: int, dry_run: bool):
            seen.update(limit=limit, dry_run=dry_run)
            return {"scanned": 3, "patterns": 1, "promoted": 0, "skipped": 1, "details": []}

        monkeypatch.setattr(basement_routes, "promote_patterns", _fake)
        client.app.dependency_overrides[get_current_user] = _as("admin")

        resp = client.post("/basement/promote", params={"dry_run": True, "limit": 42})
        assert resp.status_code == 200
        assert seen == {"limit": 42, "dry_run": True}
        assert resp.json()["promoted"] == 0

    def test_defaults_are_passed_through(self, client, monkeypatch):
        seen: dict = {}
        monkeypatch.setattr(
            basement_routes,
            "promote_patterns",
            lambda limit, dry_run: seen.update(limit=limit, dry_run=dry_run) or {"promoted": 0},
        )
        client.app.dependency_overrides[get_current_user] = _as("admin")

        assert client.post("/basement/promote").status_code == 200
        assert seen == {"limit": 500, "dry_run": False}

    @pytest.mark.parametrize("limit", [0, 5001])
    def test_limit_is_bounded(self, client, limit):
        """An unbounded scan over the evidence store is a denial-of-service
        against the Library, so the bound is validated rather than advisory."""
        client.app.dependency_overrides[get_current_user] = _as("admin")
        assert client.post("/basement/promote", params={"limit": limit}).status_code == 422

    def test_real_promotion_path_runs_end_to_end(self, client):
        """No monkeypatching: proves the route reaches the actual module.

        A test that only ever sees a stub would pass just as happily if the
        import were wrong -- which is the failure being closed here."""
        client.app.dependency_overrides[get_current_user] = _as("admin")
        body = client.post("/basement/promote", params={"dry_run": True}).json()
        assert {"scanned", "failures", "patterns", "promoted", "skipped"} <= set(body)
