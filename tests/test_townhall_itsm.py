"""The Town Hall's ITSM records: durable, owned, and announced.

Before this, `src/townhall/itsm.py` held incidents in two in-memory dicts,
emitted nothing, referenced no other subsystem, and had no callers anywhere in
`src/`. These tests hold the three things that changed, and the ordering
between two of them.
"""

from __future__ import annotations

import pytest

from src.townhall import itsm as itsm_module
from src.townhall.itsm import (
    IncidentPriority,
    IncidentStatus,
    ItsmService,
    UnknownIncidentError,
    resolve_ownership,
)


@pytest.fixture
def service(tmp_path):
    svc = ItsmService(db_path=tmp_path / "itsm.db")
    yield svc
    svc.close()


@pytest.fixture
def emitted(monkeypatch):
    """Capture what the service announces, in order."""
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        itsm_module, "_emit", lambda event_type, data: events.append((event_type, data))
    )
    return events


class TestRecordsSurviveARestart:
    """A ticket that disappears when a worker recycles is not a record."""

    def test_incidents_persist_across_instances(self, tmp_path):
        first = ItsmService(db_path=tmp_path / "itsm.db")
        incident = first.create_incident("Disk pressure", "…", service="SRV-SPARK-001")
        first.close()

        second = ItsmService(db_path=tmp_path / "itsm.db")
        try:
            assert second.get_incident(incident.id).title == "Disk pressure"
        finally:
            second.close()

    def test_changes_persist_across_instances(self, tmp_path):
        first = ItsmService(db_path=tmp_path / "itsm.db")
        change = first.create_change("Bump the pool size", service="SRV-SPARK-001")
        first.close()

        second = ItsmService(db_path=tmp_path / "itsm.db")
        try:
            assert [c.id for c in second.list_changes()] == [change.id]
        finally:
            second.close()

    def test_resolved_state_persists(self, tmp_path):
        first = ItsmService(db_path=tmp_path / "itsm.db")
        incident = first.create_incident("Latency", "…")
        first.update_incident_status(incident.id, IncidentStatus.RESOLVED)
        first.close()

        second = ItsmService(db_path=tmp_path / "itsm.db")
        try:
            reloaded = second.get_incident(incident.id)
            assert reloaded.status is IncidentStatus.RESOLVED
            assert reloaded.resolved_at is not None
            assert second.list_incidents(open_only=True) == []
        finally:
            second.close()


class TestAnIncidentKnowsWhoAnswersForIt:
    """The question the architecture asks of every incident, which had no
    programmatic answer before the CMDB identity spine."""

    def test_a_real_service_id_yields_its_location_and_ais(self, service):
        incident = service.create_incident("MCP 500s", "…", service="SRV-SPARK-001")
        own = incident.ownership
        assert own.resolved
        assert own.location == "The Spark"
        assert own.tier3_ai == "Imfy"
        assert own.tier2_prime == "Cornelius MacIntyre"

    def test_a_location_name_resolves_too(self, service):
        incident = service.create_incident("Audit lag", "…", service="The Observatory")
        assert incident.ownership.location == "The Observatory"

    def test_an_unknown_service_is_recorded_not_guessed(self, service):
        # A plausible but wrong owner is worse than none: it routes the page to
        # somebody who is not on the hook.
        incident = service.create_incident("Odd behaviour", "…", service="not-a-service")
        own = incident.ownership
        assert not own.resolved
        assert own.location is None
        assert own.tier3_ai is None
        assert own.unresolved_reason

    def test_an_ambiguous_location_is_flagged(self, service):
        # The Observatory owns several services. The incident carries the flag
        # so a blast radius is not built from one of six without knowing.
        incident = service.create_incident("Audit lag", "…", service="The Observatory")
        assert incident.ownership.location_is_ambiguous

    def test_ownership_survives_a_restart(self, tmp_path):
        first = ItsmService(db_path=tmp_path / "itsm.db")
        incident = first.create_incident("MCP 500s", "…", service="SRV-SPARK-001")
        first.close()

        second = ItsmService(db_path=tmp_path / "itsm.db")
        try:
            own = second.get_incident(incident.id).ownership
            assert own.resolved
            assert own.location == "The Spark"
            assert own.tier3_ai == "Imfy"
        finally:
            second.close()

    def test_incidents_can_be_listed_by_location(self, service):
        service.create_incident("A", "…", service="SRV-SPARK-001")
        service.create_incident("B", "…", service="The Observatory")
        titles = {i.title for i in service.incidents_for_location("The Spark")}
        assert titles == {"A"}

    def test_resolve_ownership_is_usable_without_raising_an_incident(self):
        assert resolve_ownership("SRV-SPARK-001").location == "The Spark"
        assert not resolve_ownership("nonsense").resolved


class TestTransitionsAreAnnounced:
    """Problem Management and the CIR react to these. Before, they could not
    see anything this module did."""

    def test_raising_an_incident_announces_it(self, service, emitted):
        service.create_incident("Down", "…", service="SRV-SPARK-001")
        assert [e[0] for e in emitted] == ["incident.raised"]

    @pytest.mark.parametrize(
        ("status", "event"),
        [
            (IncidentStatus.INVESTIGATING, "incident.triaged"),
            (IncidentStatus.RESOLVED, "incident.resolved"),
            (IncidentStatus.CLOSED, "incident.closed"),
        ],
    )
    def test_each_lifecycle_status_announces_its_verb(self, service, emitted, status, event):
        incident = service.create_incident("Down", "…")
        emitted.clear()
        service.update_incident_status(incident.id, status)
        assert [e[0] for e in emitted] == [event]

    def test_mitigated_is_recorded_but_not_announced(self, service, emitted):
        # Service restored, incident not resolved. Inventing an
        # `incident.mitigated` verb would hand consumers a transition the
        # architecture does not define.
        incident = service.create_incident("Down", "…")
        emitted.clear()
        service.update_incident_status(incident.id, IncidentStatus.MITIGATED)
        assert emitted == []
        assert service.get_incident(incident.id).status is IncidentStatus.MITIGATED

    def test_escalation_announces_and_carries_its_reason(self, service, emitted):
        incident = service.create_incident("Down", "…")
        emitted.clear()
        service.escalate_incident(incident.id, reason="customer impact confirmed")
        assert len(emitted) == 1
        event, payload = emitted[0]
        assert event == "incident.escalated"
        assert payload["reason"] == "customer impact confirmed"
        assert service.get_incident(incident.id).priority is IncidentPriority.P1

    def test_a_change_announces_itself(self, service, emitted):
        service.create_change("Bump pool size", service="SRV-SPARK-001")
        assert [e[0] for e in emitted] == ["change.requested"]

    def test_the_payload_carries_the_owner(self, service, emitted):
        # So a consumer reading only the event stream still knows who is
        # accountable, without re-resolving the service itself.
        service.create_incident("Down", "…", service="SRV-SPARK-001")
        payload = emitted[0][1]
        assert payload["location"] == "The Spark"
        assert payload["tier3_ai"] == "Imfy"
        assert payload["ownership_resolved"] is True


class TestTheDatabaseIsTheGuaranteeNotTheEvent:
    """`emit_async` warns and drops when no event loop is running, so emission
    is not delivery. The write must land first, or the platform announces
    transitions that never happened."""

    def test_the_record_is_committed_before_the_event_is_announced(self, tmp_path, monkeypatch):
        svc = ItsmService(db_path=tmp_path / "itsm.db")
        seen: list[bool] = []

        def _capture(event_type, data):
            # Read the row through a *separate* connection at emit time. If the
            # write had not committed, this would find nothing.
            import sqlite3

            conn = sqlite3.connect(str(tmp_path / "itsm.db"))
            try:
                row = conn.execute(
                    "SELECT 1 FROM incidents WHERE id = ?", (data["incident_id"],)
                ).fetchone()
            finally:
                conn.close()
            seen.append(row is not None)

        monkeypatch.setattr(itsm_module, "_emit", _capture)
        try:
            svc.create_incident("Down", "…")
            assert seen == [True]
        finally:
            svc.close()

    def test_a_failing_emitter_does_not_lose_the_record(self, tmp_path, monkeypatch):
        """The notification is allowed to fail. The record is not."""
        import src.event_bus as event_bus_pkg

        def _explode(*_a, **_k):
            raise RuntimeError("bus unavailable")

        monkeypatch.setattr(event_bus_pkg, "get_event_bus", _explode)

        svc = ItsmService(db_path=tmp_path / "itsm.db")
        try:
            incident = svc.create_incident("Down", "…", service="SRV-SPARK-001")
            stored = svc.get_incident(incident.id)
            assert stored.title == "Down"
            assert stored.ownership.location == "The Spark"
        finally:
            svc.close()

    def test_the_emitter_really_is_reached_when_the_bus_works(self, service, emitted):
        """Guards the test above from passing vacuously.

        If _emit were never called at all, `a failing emitter` would prove
        nothing — the record would survive because nothing had tried to emit.
        """
        service.create_incident("Down", "…")
        assert emitted, "create_incident emitted nothing; the failure test is vacuous"


class TestUnknownRecordsRaise:
    """A silent None turns a dropped status update into one nobody notices."""

    def test_getting_an_unknown_incident_raises(self, service):
        with pytest.raises(UnknownIncidentError):
            service.get_incident("nope")

    def test_updating_an_unknown_incident_raises(self, service):
        with pytest.raises(UnknownIncidentError):
            service.update_incident_status("nope", IncidentStatus.CLOSED)

    def test_escalating_an_unknown_incident_raises(self, service):
        with pytest.raises(UnknownIncidentError):
            service.escalate_incident("nope", reason="because")

    def test_an_escalation_needs_a_stated_reason(self, service):
        incident = service.create_incident("Down", "…")
        with pytest.raises(ValueError):
            service.escalate_incident(incident.id, reason="   ")
        assert service.get_incident(incident.id).priority is IncidentPriority.P3


class TestTheRoutesAreReachableAndWritesAreGated:
    """The module had no callers at all. Reads follow the platform's registry
    convention (open); writes change what the platform believes is broken and
    feed the event stream, so they require an admin."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        import api
        import tests.conftest  # noqa: F401  — applies env defaults

        return TestClient(api.app)

    def test_the_itsm_routes_are_mounted(self, client):
        import api

        paths = {r.path for r in api.app.routes if "/townhall/itsm" in getattr(r, "path", "")}
        assert "/townhall/itsm/incidents" in paths
        assert "/townhall/itsm/ownership/{service}" in paths

    def test_reads_are_open(self, client):
        assert client.get("/townhall/itsm/incidents").status_code == 200
        assert client.get("/townhall/itsm/changes").status_code == 200

    def test_impact_can_be_asked_before_anything_breaks(self, client):
        # The point of exposing it: assess a change, not only explain an
        # incident after the fact.
        body = client.get("/townhall/itsm/impact/SRV-VOID-001").json()
        assert body["resolved"] is True
        assert body["has_dependency_data"] is True
        assert body["known"]
        assert body["coverage"]["services"] > 0

    def test_impact_for_an_unknown_identifier_is_not_a_silent_zero(self, client):
        # 200 with resolved:false, never a 404 that a caller might read as
        # "assessed, nothing affected".
        response = client.get("/townhall/itsm/impact/SRV-NOPE-999")
        assert response.status_code == 200
        body = response.json()
        assert body["resolved"] is False
        assert "not a finding" in body["caveat"]
        assert "affected_count" not in body

    def test_impact_distinguishes_no_data_from_no_dependants(self, client):
        from src.cmdb.blast_radius import services_without_dependency_data

        absent = services_without_dependency_data()[0]
        body = client.get(f"/townhall/itsm/impact/{absent}").json()
        assert body["resolved"] is True
        assert body["affected_count"] == 0
        # Resolved, walked, and still unknown -- a different answer from the
        # unresolved case above, and the one that downgrades real P1s if it
        # is read as a zero.
        assert body["unknown_rather_than_empty"] is True

    def test_an_incident_carries_the_blast_radius_of_its_own_service(self, client):
        from auth import get_current_user

        client.app.dependency_overrides[get_current_user] = lambda: {
            "sub": "admin",
            "role": "admin",
        }
        try:
            created = client.post(
                "/townhall/itsm/incidents",
                json={"title": "vault unreachable", "service": "SRV-VOID-001"},
            ).json()
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

        body = client.get(f"/townhall/itsm/incidents/{created['id']}/impact").json()
        assert body["incident_id"] == created["id"]
        assert body["resolved"] is True
        assert body["known"]

    def test_impact_for_an_unknown_incident_is_404(self, client):
        assert client.get("/townhall/itsm/incidents/no-such/impact").status_code == 404

    def test_the_default_incident_service_does_not_resolve(self, client):
        """The root FastAPI app has no row in 02_service_inventory.csv.

        So an incident raised with the default `service` cannot be impact
        assessed. Recorded as a test rather than a comment: it fails the day
        the row is added, which is the day this expectation should change.
        """
        body = client.get("/townhall/itsm/impact/tranc3-backend").json()
        assert body["resolved"] is False

    def test_ownership_can_be_asked_without_raising_an_incident(self, client):
        body = client.get("/townhall/itsm/ownership/SRV-SPARK-001").json()
        assert body["location"] == "The Spark"
        assert body["tier3_ai"] == "Imfy"

    def test_an_unknown_service_reports_unresolved_rather_than_guessing(self, client):
        body = client.get("/townhall/itsm/ownership/not-a-service").json()
        assert body["resolved"] is False
        assert body["location"] is None
        assert body["unresolved_reason"]

    WRITE_ROUTES = [
        ("post", "/townhall/itsm/incidents", {"title": "x"}),
        ("post", "/townhall/itsm/incidents/abc/status", {"status": "closed"}),
        ("post", "/townhall/itsm/incidents/abc/escalate", {"reason": "x"}),
        ("post", "/townhall/itsm/changes", {"title": "x"}),
    ]

    @pytest.mark.parametrize(("method", "path", "payload"), WRITE_ROUTES)
    def test_writes_reject_an_unauthenticated_caller(self, client, method, path, payload):
        from auth import get_current_user

        client.app.dependency_overrides.pop(get_current_user, None)
        response = getattr(client, method)(path, json=payload)
        assert response.status_code in (401, 403), response.status_code

    @pytest.mark.parametrize(("method", "path", "payload"), WRITE_ROUTES)
    def test_writes_reject_an_authenticated_non_admin(self, client, method, path, payload):
        """Authorisation, not authentication.

        Calibration caught this gap: deleting `_require_admin` from every write
        handler broke no test, because an unauthenticated request fails at
        `Depends(get_current_user)` before reaching the gate. Nothing asserted
        that a *logged-in ordinary user* is refused, so the admin control could
        have been removed silently.
        """
        from auth import get_current_user

        client.app.dependency_overrides[get_current_user] = lambda: {
            "sub": "u1",
            "role": "user",
        }
        try:
            response = getattr(client, method)(path, json=payload)
            assert response.status_code == 403, response.status_code
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_an_admin_can_raise_an_incident(self, client):
        """Guards the two tests above from passing because the route is broken.

        If every write 500'd or 404'd, the refusal tests would still pass.
        """
        from auth import get_current_user

        client.app.dependency_overrides[get_current_user] = lambda: {
            "sub": "root",
            "role": "admin",
        }
        try:
            response = client.post(
                "/townhall/itsm/incidents",
                json={"title": "Raised by an admin", "service": "SRV-SPARK-001"},
            )
            assert response.status_code == 201, response.text
            assert response.json()["ownership"]["location"] == "The Spark"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)
