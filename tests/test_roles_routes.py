# tests/test_roles_routes.py
# HTTP-level tests for src/roles/routes.py (the /roles API).

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.entities.platform import PLATFORM_ENTITIES, PLATFORM_ROLES, all_seats
from src.roles import registry as registry_module
from src.roles.registry import RoleRegistry
from src.roles.routes import router as roles_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_registry = RoleRegistry(db_path=tmp_path / "routes_test.db")
    monkeypatch.setattr(registry_module, "_registry", test_registry)

    app = FastAPI()
    app.include_router(roles_router)
    with TestClient(app) as c:
        yield c
    test_registry.close()


def _override(user_id: str, role: str = "user"):
    def _dep():
        return {"sub": user_id, "role": role}

    return _dep


class TestReadRoutes:
    def test_list_roles_is_public(self, client):
        resp = client.get("/roles/")
        assert resp.status_code == 200
        body = resp.json()
        # Locations plus non-Location platform roles (the Shared Functional
        # Services Core). Derived from the registries rather than hardcoded:
        # this assertion was a literal 43 and broke the moment a role was added,
        # which tells you the count changed but not whether it changed
        # correctly. Comparing the actual key set does.
        assert {r["location"] for r in body} == set(PLATFORM_ENTITIES) | set(PLATFORM_ROLES)
        assert len(body) == len(all_seats())

    def test_get_known_role(self, client):
        resp = client.get("/roles/Royal Bank of Arcadia")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_description"] == "Chief Financial Officer"
        assert body["assigned_ai"] == "Dorris Fontaine"

    def test_get_role_with_slash_in_location_name(self, client):
        """ChronosSphere / ArcStream is the one canonical location whose name
        contains a literal '/' — the {location:path} route converter must
        resolve it instead of 404ing or matching the wrong route."""
        resp = client.get("/roles/ChronosSphere / ArcStream")
        assert resp.status_code == 200
        assert resp.json()["location"] == "ChronosSphere / ArcStream"

    def test_history_for_slash_location_does_not_shadow_get(self, client):
        resp = client.get("/roles/ChronosSphere / ArcStream/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_unknown_role_404s(self, client):
        resp = client.get("/roles/Nonexistent Place")
        assert resp.status_code == 404

    def test_history_empty_for_untouched_role(self, client):
        resp = client.get("/roles/Luminous/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_unknown_location_404s(self, client):
        resp = client.get("/roles/Nonexistent Place/history")
        assert resp.status_code == 404


class TestAssignRoute:
    def test_requires_auth(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        resp = client.post("/roles/The Nexus/assign", json={"ai_name": "New AI"})
        assert resp.status_code in (401, 403)

    def test_non_admin_forbidden(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.post("/roles/The Nexus/assign", json={"ai_name": "New AI"})
            assert resp.status_code == 403
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_can_assign(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/roles/The Nexus/assign",
                json={"ai_name": "New AI", "reason": "rotation"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["assigned_ai"] == "New AI"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_assign_unknown_location_404s(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post("/roles/Nonexistent Place/assign", json={"ai_name": "X"})
            assert resp.status_code == 404
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_assign_unsafe_ai_name_rejected(self, client):
        before_role = client.get("/roles/The Nexus").json()
        before_history = client.get("/roles/The Nexus/history").json()
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/roles/The Nexus/assign",
                json={"ai_name": "<script>alert(1)</script>"},
            )
            assert resp.status_code == 400
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)
        assert client.get("/roles/The Nexus").json() == before_role
        assert client.get("/roles/The Nexus/history").json() == before_history

    def test_assign_blank_ai_name_rejected(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post("/roles/The Nexus/assign", json={"ai_name": "   "})
            assert resp.status_code == 400
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_assign_records_history(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            client.post("/roles/The HIVE/assign", json={"ai_name": "Swarm AI 2"})
            history = client.get("/roles/The HIVE/history").json()
            assert len(history) == 1
            assert history[0]["new_ai"] == "Swarm AI 2"
            assert history[0]["previous_ai"] == "The Queen"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)


class TestUnassignRoute:
    def test_requires_auth(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        resp = client.request("DELETE", "/roles/The Nexus/assign")
        assert resp.status_code in (401, 403)

    def test_non_admin_forbidden(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.request("DELETE", "/roles/The Nexus/assign")
            assert resp.status_code == 403
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_can_unassign(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.request("DELETE", "/roles/The Nexus/assign")
            assert resp.status_code == 200
            assert resp.json()["assigned_ai"] is None
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_unassign_unknown_location_404s(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.request("DELETE", "/roles/Nonexistent Place/assign")
            assert resp.status_code == 404
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)


class TestSuiteStewardshipRoutes:
    """Matrix Suites Stage 7.5 — /roles/suites cross-references Magna Carta's
    real matrix_suites.yaml (via the compliance/magna-carta submodule checked
    out in this repo) against the RoleRegistry fixture the `client` fixture
    already seeds with the real 43 canonical Locations."""

    def test_list_suites_is_public(self, client):
        resp = client.get("/roles/suites")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 8
        suite_ids = {s["suite_id"] for s in body}
        assert {"SUITE-FIN", "SUITE-SEC", "SUITE-LEG"} <= suite_ids

    def test_get_known_suite_matches_baseline(self, client):
        resp = client.get("/roles/suites/SUITE-SEC")
        assert resp.status_code == 200
        body = resp.json()
        assert body["steward_location"] == "Cryptex"
        assert body["designed_steward_ai"] == "Renik"
        assert body["current_steward_ai"] == "Renik"
        assert body["drifted"] is False

    def test_get_unknown_suite_404s(self, client):
        resp = client.get("/roles/suites/SUITE-NOPE")
        assert resp.status_code == 404

    def test_suites_route_not_swallowed_by_location_catchall(self, client):
        """Registration order matters: {location:path} must not intercept
        '/roles/suites' as if 'suites' were a location name."""
        resp = client.get("/roles/suites")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_malformed_registry_404s_not_500s(self, client, tmp_path, monkeypatch):
        """Regression: a non-mapping suite entry used to reach suite.get(...)
        unguarded and raise an unhandled AttributeError (500) instead of the
        routes' intended 404 invalid_registry — see
        src/roles/suite_stewardship.py's isinstance(suite, dict) guard."""
        bad = tmp_path / "bad_matrix_suites.yaml"
        bad.write_text("meta: {}\nsuites: [null]\n", encoding="utf-8")
        monkeypatch.setenv("MATRIX_SUITES_PATH", str(bad))
        resp = client.get("/roles/suites")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "invalid_registry"

    def test_reassigning_steward_location_shows_drift(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post("/roles/Cryptex/assign", json={"ai_name": "Temp Steward"})
            assert resp.status_code == 200
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)
        resp = client.get("/roles/suites/SUITE-SEC")
        body = resp.json()
        assert body["current_steward_ai"] == "Temp Steward"
        assert body["designed_steward_ai"] == "Renik"
        assert body["drifted"] is True


class TestSeatsRoute:
    """`GET /roles/{location}/seats` — every Job Description at one Location.

    The question the single-row model could not answer. Without this route an
    operator can see that The Chaos Party has a role, but not that it has two
    with different holders and different work.
    """

    def test_a_multi_ai_location_returns_every_seat(self, client):
        resp = client.get("/roles/The Chaos Party/seats")
        assert resp.status_code == 200
        body = resp.json()
        assert [s["seat_id"] for s in body] == ["primary", "alice-dream"]
        assert {s["assigned_ai"] for s in body} == {"The Mad Hatter", "Alice Dream"}

    def test_each_seat_carries_its_own_job_and_functions(self, client):
        """Two seats sharing a title or a function list would mean the seat
        model had been added without the roles actually being distinguished."""
        body = client.get("/roles/The Chaos Party/seats").json()
        assert len({s["job_description"] for s in body}) == 2
        assert body[0]["functions"] and body[1]["functions"]
        assert body[0]["functions"] != body[1]["functions"]

    def test_designed_for_is_reported_alongside_the_current_holder(self, client):
        """`designed_for` is who the seat was written for; `assigned_ai` is who
        holds it now. They start equal and are allowed to diverge."""
        body = client.get("/roles/Infinity/seats").json()
        orb = next(s for s in body if s["seat_id"] == "the-orb-of-orisis")
        assert orb["designed_for"] == "The Orb of Orisis"
        assert orb["job_description"] == "Head of Architectural Foresight"

    def test_a_single_ai_location_returns_exactly_one_seat(self, client):
        body = client.get("/roles/The Spark/seats").json()
        assert len(body) == 1 and body[0]["seat_id"] == "primary"

    def test_an_unknown_location_is_404_not_an_empty_list(self, client):
        """An empty list would read as "this Location has no roles", which is a
        different and wrong answer to "there is no such Location"."""
        assert client.get("/roles/Nowhere/seats").status_code == 404

    def test_the_route_is_public_like_the_other_reads(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        assert client.get("/roles/TateKing/seats").status_code == 200


class TestSeatScopedMutation:
    def test_assigning_names_the_seat(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", "admin")
        resp = client.post(
            "/roles/TateKing/assign",
            json={"ai_name": "Stand-In", "reason": "cover", "seat_id": "sam-king"},
        )
        assert resp.status_code == 200
        assert resp.json()["seat_id"] == "sam-king"

        seats = {s["seat_id"]: s["assigned_ai"] for s in client.get("/roles/TateKing/seats").json()}
        assert seats["sam-king"] == "Stand-In"
        assert seats["primary"] == "Benji Tate", "the sibling seat must not move"

    def test_assign_defaults_to_the_primary_seat(self, client):
        """A caller that predates seats keeps working unchanged."""
        client.app.dependency_overrides[get_current_user] = _override("admin1", "admin")
        resp = client.post("/roles/TateKing/assign", json={"ai_name": "Stand-In"})
        assert resp.status_code == 200 and resp.json()["seat_id"] == "primary"

    def test_unassigning_names_the_seat(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", "admin")
        resp = client.request(
            "DELETE", "/roles/Infinity/assign", json={"seat_id": "the-orb-of-orisis"}
        )
        assert resp.status_code == 200
        seats = {s["seat_id"]: s["assigned_ai"] for s in client.get("/roles/Infinity/seats").json()}
        assert seats["the-orb-of-orisis"] is None
        assert seats["primary"] == "The Guardian (Marcus Magnolia)"

    def test_an_unknown_seat_is_404(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", "admin")
        resp = client.post("/roles/TateKing/assign", json={"ai_name": "X", "seat_id": "not-a-seat"})
        assert resp.status_code == 404


class TestSlashContainingLocationNames:
    """`ChronosSphere / ArcStream` is a real Location whose name contains a
    slash, and every /roles route uses the `{location:path}` converter. The
    literal `/seats` and `/history` suffixes are matched by ordering, so a
    name containing a slash is where that ordering either holds or breaks.
    """

    NAME = "ChronosSphere / ArcStream"

    def test_seats_resolves_for_a_slash_containing_name(self, client):
        resp = client.get(f"/roles/{self.NAME}/seats")
        assert resp.status_code == 200
        assert resp.json()[0]["location"] == self.NAME

    def test_the_bare_location_route_still_resolves(self, client):
        resp = client.get(f"/roles/{self.NAME}")
        assert resp.status_code == 200
        assert resp.json()["location"] == self.NAME

    def test_history_resolves_for_a_slash_containing_name(self, client):
        assert client.get(f"/roles/{self.NAME}/history").status_code == 200


class TestHistoryIsSeatAware:
    def test_history_reports_which_seat_moved(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", "admin")
        client.post("/roles/TateKing/assign", json={"ai_name": "A", "seat_id": "sam-king"})
        entries = client.get("/roles/TateKing/history").json()
        assert entries and entries[0]["seat_id"] == "sam-king"

    def test_history_can_be_filtered_to_one_seat(self, client):
        """Without the filter a reader sees two interleaved seat moves with no
        way to separate them."""
        client.app.dependency_overrides[get_current_user] = _override("admin1", "admin")
        client.post("/roles/TateKing/assign", json={"ai_name": "A", "seat_id": "primary"})
        client.post("/roles/TateKing/assign", json={"ai_name": "B", "seat_id": "sam-king"})

        assert len(client.get("/roles/TateKing/history").json()) == 2
        only = client.get("/roles/TateKing/history", params={"seat_id": "sam-king"}).json()
        assert len(only) == 1 and only[0]["new_ai"] == "B"
