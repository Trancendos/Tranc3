"""The Continual Improvement Register, and whether its gate actually gates.

A register that merely records alongside incident closure is the defect this
whole engagement keeps finding: present, correct, connected to nothing. The
property worth testing is therefore not "entries can be written" but "an
incident cannot be closed without one", and that the refusal happens before
the row is written rather than after.
"""

from __future__ import annotations

import pytest

from src.townhall import cir as cir_module
from src.townhall.cir import (
    CirService,
    ClosureBlocked,
    ImprovementKind,
    ImprovementStatus,
    UnknownImprovementError,
)
from src.townhall.itsm import IncidentStatus, ItsmService
from tests.support.routes import mounted_paths


@pytest.fixture
def cir(tmp_path):
    svc = CirService(db_path=tmp_path / "cir.db")
    yield svc
    svc.close()


@pytest.fixture
def itsm(tmp_path, cir):
    svc = ItsmService(db_path=tmp_path / "itsm.db", cir=cir)
    yield svc
    svc.close()


@pytest.fixture
def emitted(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        cir_module, "_emit", lambda event_type, data: events.append((event_type, data))
    )
    return events


class TestClosureIsGated:
    """The reason the register exists."""

    def test_an_incident_with_no_entry_cannot_be_closed(self, itsm):
        incident = itsm.create_incident("vault down", "…", service="SRV-VOID-001")
        with pytest.raises(ClosureBlocked):
            itsm.update_incident_status(incident.id, IncidentStatus.CLOSED)

    def test_the_refusal_happens_before_the_write(self, itsm):
        # A gate that fires after the UPDATE has already closed the incident
        # and is only complaining about it.
        incident = itsm.create_incident("vault down", "…")
        itsm.update_incident_status(incident.id, IncidentStatus.RESOLVED)
        with pytest.raises(ClosureBlocked):
            itsm.update_incident_status(incident.id, IncidentStatus.CLOSED)
        assert itsm.get_incident(incident.id).status is IncidentStatus.RESOLVED

    def test_resolution_is_never_gated(self, itsm):
        # Deliberate asymmetry. Blocking resolution would hold a customer's
        # outage open while paperwork is filed, which is how improvement
        # gates get switched off.
        incident = itsm.create_incident("vault down", "…")
        assert (
            itsm.update_incident_status(incident.id, IncidentStatus.RESOLVED).status
            is IncidentStatus.RESOLVED
        )

    def test_no_other_transition_is_gated(self, itsm):
        incident = itsm.create_incident("vault down", "…")
        for status in (
            IncidentStatus.INVESTIGATING,
            IncidentStatus.MITIGATED,
            IncidentStatus.RESOLVED,
        ):
            itsm.update_incident_status(incident.id, status)

    def test_a_raised_improvement_unblocks_closure(self, itsm, cir):
        incident = itsm.create_incident("vault down", "…")
        cir.raise_improvement("add a vault probe", raised_by="Prometheus", incident_id=incident.id)
        assert (
            itsm.update_incident_status(incident.id, IncidentStatus.CLOSED).status
            is IncidentStatus.CLOSED
        )

    def test_an_accepted_risk_unblocks_closure(self, itsm, cir):
        incident = itsm.create_incident("vault down", "…")
        cir.accept_as_risk(
            "",
            accepted_by="Tristuran",
            rationale="transient upstream blip",
            incident_id=incident.id,
        )
        assert (
            itsm.update_incident_status(incident.id, IncidentStatus.CLOSED).status
            is IncidentStatus.CLOSED
        )

    def test_an_entry_on_a_different_incident_does_not_unblock_this_one(self, itsm, cir):
        one = itsm.create_incident("vault down", "…")
        other = itsm.create_incident("grid stalled", "…")
        cir.raise_improvement("add a probe", raised_by="Prometheus", incident_id=other.id)
        with pytest.raises(ClosureBlocked):
            itsm.update_incident_status(one.id, IncidentStatus.CLOSED)

    def test_an_unknown_incident_is_a_missing_incident_not_a_missing_entry(self, itsm):
        from src.townhall.itsm import UnknownIncidentError

        with pytest.raises(UnknownIncidentError):
            itsm.update_incident_status("no-such-incident", IncidentStatus.CLOSED)

    def test_the_refusal_says_how_to_satisfy_it(self, cir):
        allowed, reason = cir.may_close("INC-1")
        assert allowed is False
        assert "accept-as-risk" in reason or "accept" in reason
        assert "named decider" in reason


class TestAcceptanceIsAttributable:
    """The escape hatch is the point, but it is not free."""

    def test_an_anonymous_acceptance_is_refused(self, cir):
        with pytest.raises(ValueError):
            cir.accept_as_risk("", accepted_by="  ", rationale="nothing to do", incident_id="INC-1")

    def test_an_unreasoned_acceptance_is_refused(self, cir):
        with pytest.raises(ValueError):
            cir.accept_as_risk("", accepted_by="Tristuran", rationale="", incident_id="INC-1")

    def test_the_decider_is_recorded_on_the_entry(self, cir):
        entry = cir.accept_as_risk(
            "", accepted_by="Tristuran", rationale="one-off network blip", incident_id="INC-1"
        )
        assert entry.accepted_by == "Tristuran"
        assert entry.status is ImprovementStatus.ACCEPTED_AS_RISK
        assert entry.rationale == "one-off network blip"

    def test_an_improvement_needs_somebody_who_raised_it(self, cir):
        with pytest.raises(ValueError):
            cir.raise_improvement("do better", raised_by=" ")

    def test_an_improvement_needs_a_title(self, cir):
        with pytest.raises(ValueError):
            cir.raise_improvement("   ", raised_by="Tristuran")


class TestEntriesAreDurableAndAnnounced:
    def test_entries_survive_a_restart(self, tmp_path):
        first = CirService(db_path=tmp_path / "cir.db")
        entry = first.raise_improvement("add a probe", raised_by="Prometheus", incident_id="INC-1")
        first.close()

        second = CirService(db_path=tmp_path / "cir.db")
        try:
            assert [e.id for e in second.entries_for_incident("INC-1")] == [entry.id]
        finally:
            second.close()

    @pytest.mark.parametrize(
        ("action", "event"),
        [
            ("raise", "improvement.raised"),
            ("accept", "improvement.accepted_as_risk"),
            ("realise", "improvement.realised"),
        ],
    )
    def test_every_state_announces_its_verb(self, cir, emitted, action, event):
        # Unlike the incident lifecycle, no CIR state is silent -- the whole
        # purpose is that the decision is visible.
        if action == "raise":
            cir.raise_improvement("x", raised_by="Tristuran")
        elif action == "accept":
            cir.accept_as_risk("x", accepted_by="Tristuran", rationale="y", incident_id="INC-1")
        else:
            entry = cir.raise_improvement("x", raised_by="Tristuran")
            emitted.clear()
            cir.realise(entry.id)
        assert [e[0] for e in emitted] == [event]

    def test_the_row_is_the_record_and_the_event_only_the_notification(self, cir, monkeypatch):
        # A broken bus must not lose the entry -- and must not leave an
        # incident un-closable because the notification failed.
        import src.event_bus as event_bus_pkg

        def explode():
            raise RuntimeError("bus down")

        monkeypatch.setattr(event_bus_pkg, "get_event_bus", explode)
        entry = cir.raise_improvement("add a probe", raised_by="Prometheus", incident_id="INC-1")
        assert cir.get(entry.id).id == entry.id
        assert cir.may_close("INC-1")[0] is True

    def test_the_emitter_really_is_reached_when_the_bus_works(self, cir, emitted):
        # Vacuity guard for the test above: if _emit were never called at all,
        # that test would pass for the wrong reason.
        cir.raise_improvement("x", raised_by="Tristuran")
        assert emitted

    def test_realising_an_unknown_improvement_raises(self, cir):
        with pytest.raises(UnknownImprovementError):
            cir.realise("CIR-nope")

    def test_open_only_excludes_settled_entries(self, cir):
        raised = cir.raise_improvement("still to do", raised_by="Tristuran")
        done = cir.raise_improvement("done", raised_by="Tristuran")
        cir.realise(done.id)
        cir.accept_as_risk("", accepted_by="Tristuran", rationale="n/a", incident_id="INC-1")
        assert [e.id for e in cir.list_entries(open_only=True)] == [raised.id]
        assert len(cir.list_entries()) == 3

    def test_kinds_round_trip_through_storage(self, cir):
        entry = cir.raise_improvement(
            "split the worker", kind=ImprovementKind.ARCHITECTURE, raised_by="Tristuran"
        )
        assert cir.get(entry.id).kind is ImprovementKind.ARCHITECTURE


class TestTheRoutesEnforceTheSameGate:
    """A route that is softer than the service is the gate with a hole in it."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        import api
        import src.townhall.itsm as itsm_mod
        import tests.conftest  # noqa: F401  — applies env defaults

        # Replace the process-wide singletons rather than the names bound into
        # the routes module, so the gate inside ItsmService and the routes both
        # see the same temporary register.
        cir_svc = CirService(db_path=tmp_path / "cir.db")
        itsm_svc = ItsmService(db_path=tmp_path / "itsm.db", cir=cir_svc)
        monkeypatch.setattr(cir_module, "_cir", cir_svc)
        monkeypatch.setattr(itsm_mod, "_itsm", itsm_svc)
        try:
            yield TestClient(api.app)
        finally:
            itsm_svc.close()
            cir_svc.close()

    @staticmethod
    def _as_admin(client):
        from auth import get_current_user

        client.app.dependency_overrides[get_current_user] = lambda: {
            "sub": "admin",
            "role": "admin",
        }

    @staticmethod
    def _clear_auth(client):
        from auth import get_current_user

        client.app.dependency_overrides.pop(get_current_user, None)

    def _incident(self, client) -> str:
        self._as_admin(client)
        try:
            return client.post("/townhall/itsm/incidents", json={"title": "vault down"}).json()[
                "id"
            ]
        finally:
            self._clear_auth(client)

    def test_the_cir_routes_are_mounted(self, client):
        import api

        paths = mounted_paths(api.app)
        assert "/townhall/itsm/improvements" in paths
        assert "/townhall/itsm/incidents/{incident_id}/accept-as-risk" in paths

    def test_closing_without_an_entry_is_409_not_success(self, client):
        incident_id = self._incident(client)
        self._as_admin(client)
        try:
            response = client.post(
                f"/townhall/itsm/incidents/{incident_id}/status", json={"status": "closed"}
            )
        finally:
            self._clear_auth(client)
        assert response.status_code == 409
        assert "Continual Improvement Register" in response.json()["detail"]

    def test_the_closable_read_explains_before_the_refusal(self, client):
        incident_id = self._incident(client)
        body = client.get(f"/townhall/itsm/incidents/{incident_id}/closable").json()
        assert body["closable"] is False
        assert body["reason"]

    def test_accepting_a_risk_then_closing_succeeds(self, client):
        incident_id = self._incident(client)
        self._as_admin(client)
        try:
            accepted = client.post(
                f"/townhall/itsm/incidents/{incident_id}/accept-as-risk",
                json={"accepted_by": "Tristuran", "rationale": "one-off blip"},
            )
            assert accepted.status_code == 201
            assert client.get(f"/townhall/itsm/incidents/{incident_id}/closable").json()["closable"]
            closed = client.post(
                f"/townhall/itsm/incidents/{incident_id}/status", json={"status": "closed"}
            )
        finally:
            self._clear_auth(client)
        assert closed.status_code == 200
        assert closed.json()["status"] == "closed"

    def test_an_anonymous_acceptance_is_refused_at_the_route_too(self, client):
        incident_id = self._incident(client)
        self._as_admin(client)
        try:
            response = client.post(
                f"/townhall/itsm/incidents/{incident_id}/accept-as-risk",
                json={"accepted_by": "", "rationale": "one-off blip"},
            )
        finally:
            self._clear_auth(client)
        assert response.status_code == 422

    def test_accepting_a_risk_on_an_unknown_incident_is_404(self, client):
        self._as_admin(client)
        try:
            response = client.post(
                "/townhall/itsm/incidents/no-such/accept-as-risk",
                json={"accepted_by": "Tristuran", "rationale": "x"},
            )
        finally:
            self._clear_auth(client)
        assert response.status_code == 404

    def test_reads_are_open(self, client):
        assert client.get("/townhall/itsm/improvements").status_code == 200

    def test_writes_reject_an_authenticated_non_admin(self, client):
        from auth import get_current_user

        client.app.dependency_overrides[get_current_user] = lambda: {
            "sub": "u1",
            "role": "user",
        }
        try:
            # 403 specifically: 401 would only prove authentication runs, not
            # that the admin gate does.
            assert (
                client.post(
                    "/townhall/itsm/improvements",
                    json={"title": "x", "raised_by": "u1"},
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/townhall/itsm/incidents/any/accept-as-risk",
                    json={"accepted_by": "u1", "rationale": "x"},
                ).status_code
                == 403
            )
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_an_admin_can_do_what_the_non_admin_could_not(self, client):
        # So the refusals above cannot pass because the routes are broken.
        self._as_admin(client)
        try:
            response = client.post(
                "/townhall/itsm/improvements",
                json={"title": "add a probe", "raised_by": "Prometheus"},
            )
        finally:
            self._clear_auth(client)
        assert response.status_code == 201
