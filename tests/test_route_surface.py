"""The route surface, after FastAPI stopped flattening included routers.

FastAPI 0.141 changed `include_router`: it appends one lazy `_IncludedRouter`
marker instead of copying each sub-route into `app.routes`, resolving the real
routes at request time. Routing is unaffected — every endpoint answers as
before — but `app.routes` went from the whole surface to only what is declared
directly on the app: 83 objects out of 342.

Three mount assertions failed loudly on a working application. Two other scans
failed silently and kept passing while inspecting a quarter of what they
claimed to, which is the defect class this engagement keeps finding.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.support.routes import mounted_paths, mounted_routes

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def app():
    import api

    return api.app


class TestTheHelperSeesWhatTheAppServes:
    def test_it_finds_paths_app_routes_does_not(self, app):
        """Calibrated: reading app.routes fails this.

        `/exchange/inventory` answers 200 and is absent from `app.routes`.
        That gap is the whole reason this helper exists.
        """
        direct = {getattr(r, "path", "") for r in app.routes}
        assert "/exchange/inventory" not in direct
        assert "/exchange/inventory" in mounted_paths(app)

    def test_it_finds_far_more_route_objects_than_the_attribute(self, app):
        """The silent half: a scan over app.routes inspects a fraction."""
        assert len(mounted_routes(app)) > 3 * len(app.routes)

    def test_the_paths_it_reports_actually_answer(self, app):
        """Calibrated: returning invented paths fails this."""
        from fastapi.testclient import TestClient

        client = TestClient(app)
        for path in ("/exchange/inventory", "/health"):
            assert path in mounted_paths(app)
            assert client.get(path).status_code < 500

    def test_websocket_routes_survive_the_openapi_read(self, app):
        """OpenAPI omits WebSockets, so the route walk has to fill them in."""
        assert "/ws/chat" in mounted_paths(app)

    def test_route_objects_carry_their_dependants(self, app):
        """What the RBAC sweep needs: real APIRoutes, not markers."""
        routes = mounted_routes(app)
        assert any(getattr(r, "dependant", None) is not None for r in routes)
        assert not any(type(r).__name__ == "_IncludedRouter" for r in routes)


class TestTheGuard:
    @pytest.fixture(scope="class")
    def guard(self):
        path = REPO / "scripts" / "check_route_surface_reads.py"
        spec = importlib.util.spec_from_file_location("check_route_surface_reads", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_the_suite_reads_the_surface_through_the_helper(self, guard):
        assert guard.offenders() == []

    def test_it_reads_code_not_prose(self, guard, tmp_path, monkeypatch):
        """Calibrated: matching source lines fails this.

        The first version was a regex and flagged the comment inside its own
        explanation. A check that cannot tell code from prose is one people
        route around by rewording rather than fixing.
        """
        probe = tmp_path / "test_probe.py"
        probe.write_text("# app.routes is mentioned here\nX = 1\n", encoding="utf-8")
        monkeypatch.setattr(guard, "TESTS", tmp_path)
        monkeypatch.setattr(guard, "REPO", tmp_path)
        assert guard.offenders() == []

    def test_it_catches_a_real_read(self, guard, tmp_path, monkeypatch):
        probe = tmp_path / "test_probe.py"
        probe.write_text("def f(app):\n    return [r for r in app.routes]\n", encoding="utf-8")
        monkeypatch.setattr(guard, "TESTS", tmp_path)
        monkeypatch.setattr(guard, "REPO", tmp_path)
        assert len(guard.offenders()) == 1

    def test_it_catches_a_qualified_read(self, guard, tmp_path, monkeypatch):
        """`api.app.routes` is the same defect wearing a module prefix."""
        probe = tmp_path / "test_probe.py"
        probe.write_text("import api\nX = list(api.app.routes)\n", encoding="utf-8")
        monkeypatch.setattr(guard, "TESTS", tmp_path)
        monkeypatch.setattr(guard, "REPO", tmp_path)
        assert len(guard.offenders()) == 1

    def test_a_getattr_bypass_is_caught(self, guard, tmp_path, monkeypatch):
        """Calibrated: matching only attribute nodes fails this.

        `getattr(app, "routes")` reaches the same object and reads the same
        truncated surface. A guard with a documented spelling is a guard with
        a documented bypass.
        """
        probe = tmp_path / "test_probe.py"
        probe.write_text('X = getattr(app, "routes")\n', encoding="utf-8")
        monkeypatch.setattr(guard, "TESTS", tmp_path)
        monkeypatch.setattr(guard, "REPO", tmp_path)
        assert len(guard.offenders()) == 1

    def test_an_unrelated_getattr_is_not_caught(self, guard, tmp_path, monkeypatch):
        """Calibrated: flagging every getattr on `app` fails this."""
        probe = tmp_path / "test_probe.py"
        probe.write_text('X = getattr(app, "title")\n', encoding="utf-8")
        monkeypatch.setattr(guard, "TESTS", tmp_path)
        monkeypatch.setattr(guard, "REPO", tmp_path)
        assert guard.offenders() == []
