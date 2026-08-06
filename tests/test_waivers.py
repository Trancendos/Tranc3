"""
Tests for governance waivers/exceptions (src/compliance/waivers.py) and its
FastAPI routes (src/compliance/waivers_routes.py).
"""

from __future__ import annotations

import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.compliance.waivers as waivers_module
import src.compliance.waivers_routes as waivers_routes_module
from src.compliance.waivers import (
    WaiverNotFoundError,
    WaiverValidationError,
    emit_expiry_events,
    get_waiver,
    list_waivers,
    register_waiver,
    revoke_waiver,
)
from src.compliance.waivers_routes import router


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(waivers_module, "_DB_PATH", tmp_path / "waivers.db")
    with waivers_module._get_conn() as conn:
        waivers_module._init_db(conn)


# ── register_waiver ─────────────────────────────────────────────────────────


def test_register_waiver_defaults_effective_from_to_now():
    before = time.time()
    waiver = register_waiver(
        subject="Matrix Suite SUITE-FIN review cadence",
        justification="Dependent system migration in progress",
        requestor="agent-1",
        approver="human-1",
        expires_on=time.time() + 3600,
    )
    assert waiver.effective_from >= before
    assert waiver.status == "active"
    assert waiver.compensating_controls == []


def test_register_waiver_with_compensating_controls():
    waiver = register_waiver(
        subject="test",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        expires_on=time.time() + 3600,
        compensating_controls=["manual review weekly", "alerting enabled"],
    )
    assert waiver.compensating_controls == ["manual review weekly", "alerting enabled"]


@pytest.mark.parametrize("field", ["subject", "justification", "requestor", "approver"])
def test_register_waiver_rejects_blank_fields(field):
    kwargs = {
        "subject": "test",
        "justification": "test",
        "requestor": "agent-1",
        "approver": "human-1",
        "expires_on": time.time() + 3600,
    }
    kwargs[field] = "   "
    with pytest.raises(WaiverValidationError):
        register_waiver(**kwargs)


def test_register_waiver_rejects_expires_on_before_effective_from():
    now = time.time()
    with pytest.raises(WaiverValidationError):
        register_waiver(
            subject="test",
            justification="test",
            requestor="agent-1",
            approver="human-1",
            effective_from=now,
            expires_on=now - 1,
        )


def test_register_waiver_rejects_non_string_compensating_controls():
    with pytest.raises(WaiverValidationError):
        register_waiver(
            subject="test",
            justification="test",
            requestor="agent-1",
            approver="human-1",
            expires_on=time.time() + 3600,
            compensating_controls=[123],
        )


def test_register_waiver_future_effective_from_is_pending():
    now = time.time()
    waiver = register_waiver(
        subject="test",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        effective_from=now + 3600,
        expires_on=now + 7200,
    )
    assert waiver.status == "pending"


def test_register_waiver_emits_observatory_event():
    from src.observability.observatory import get_observatory

    obs = get_observatory()
    before = len(obs._buffer)
    waiver = register_waiver(
        subject="test",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        expires_on=time.time() + 3600,
    )
    assert len(obs._buffer) == before + 1
    event = obs._buffer[-1]
    assert event.event_type == "governance.waiver.granted"
    assert event.target == waiver.waiver_id
    assert event.service == "trancendos-waivers"


# ── get_waiver / list_waivers ──────────────────────────────────────────────


def test_get_waiver_not_found_raises():
    with pytest.raises(WaiverNotFoundError):
        get_waiver("WVR-DOESNOTEXIST")


def test_list_waivers_filters_by_status():
    active = register_waiver(
        subject="active-one",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        expires_on=time.time() + 3600,
    )
    expired = register_waiver(
        subject="expired-one",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        effective_from=time.time() - 7200,
        expires_on=time.time() - 3600,
    )
    all_ids = {w.waiver_id for w in list_waivers()}
    assert {active.waiver_id, expired.waiver_id} <= all_ids

    active_only = {w.waiver_id for w in list_waivers(status="active")}
    assert active.waiver_id in active_only
    assert expired.waiver_id not in active_only

    expired_only = {w.waiver_id for w in list_waivers(status="expired")}
    assert expired.waiver_id in expired_only
    assert active.waiver_id not in expired_only


# ── revoke_waiver ───────────────────────────────────────────────────────────


def test_revoke_waiver_sets_status_revoked():
    waiver = register_waiver(
        subject="test",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        expires_on=time.time() + 3600,
    )
    revoked = revoke_waiver(waiver.waiver_id, revoked_by="human-2", reason="no longer needed")
    assert revoked.status == "revoked"
    assert revoked.revoked_by == "human-2"

    fetched = get_waiver(waiver.waiver_id)
    assert fetched.status == "revoked"


def test_revoke_waiver_not_found_raises():
    with pytest.raises(WaiverNotFoundError):
        revoke_waiver("WVR-DOESNOTEXIST", revoked_by="human-1", reason="test")


def test_revoke_waiver_rejects_blank_revoked_by():
    waiver = register_waiver(
        subject="test",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        expires_on=time.time() + 3600,
    )
    with pytest.raises(WaiverValidationError):
        revoke_waiver(waiver.waiver_id, revoked_by="  ", reason="test")


def test_revoke_already_revoked_waiver_raises():
    waiver = register_waiver(
        subject="test",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        expires_on=time.time() + 3600,
    )
    revoke_waiver(waiver.waiver_id, revoked_by="human-2", reason="first revoke")
    with pytest.raises(WaiverValidationError):
        revoke_waiver(waiver.waiver_id, revoked_by="human-3", reason="second revoke")


def test_revoke_expired_waiver_raises():
    """cubic-style: revoking an already-expired waiver would misrepresent why it
    ended — it should read 'expired', not 'revoked by human-3 for an unrelated
    reason after the fact'."""
    waiver = register_waiver(
        subject="test",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        effective_from=time.time() - 7200,
        expires_on=time.time() - 3600,
    )
    with pytest.raises(WaiverValidationError):
        revoke_waiver(waiver.waiver_id, revoked_by="human-2", reason="too late")


def test_revoke_waiver_race_expiry_between_check_and_update_raises(monkeypatch):
    """cubic P1: the status check in get_waiver() and the UPDATE in revoke_waiver()
    are two separate operations — a waiver can cross expires_on in between. Feeds
    revoke_waiver() a stale 'active' Waiver snapshot while the DB row has already
    genuinely expired, proving the UPDATE's own WHERE clause (not just the earlier
    Python-level status check) is what actually blocks this."""
    waiver = register_waiver(
        subject="test",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        expires_on=time.time() + 3600,
    )
    stale_snapshot = get_waiver(waiver.waiver_id)
    assert stale_snapshot.status == "active"

    with waivers_module._get_conn() as conn:
        conn.execute(
            "UPDATE waivers SET expires_on = ? WHERE waiver_id = ?",
            (time.time() - 1, waiver.waiver_id),
        )
        conn.commit()

    monkeypatch.setattr(waivers_module, "get_waiver", lambda _wid: stale_snapshot)
    with pytest.raises(WaiverValidationError):
        revoke_waiver(waiver.waiver_id, revoked_by="human-2", reason="race")


# ── emit_expiry_events ──────────────────────────────────────────────────────


def test_emit_expiry_events_only_fires_once_per_waiver():
    register_waiver(
        subject="test",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        effective_from=time.time() - 7200,
        expires_on=time.time() - 3600,
    )
    first = emit_expiry_events()
    assert len(first) == 1
    assert first[0].event_type == "governance.waiver.expired"

    second = emit_expiry_events()
    assert second == []


def test_emit_expiry_events_skips_active_and_revoked():
    register_waiver(
        subject="active",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        expires_on=time.time() + 3600,
    )
    revoked_but_expired = register_waiver(
        subject="revoked",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        effective_from=time.time() - 7200,
        expires_on=time.time() - 3600 + 0.001,
    )
    # Force it into 'revoked' before it would otherwise be picked up as expired —
    # revoke_waiver() itself refuses to revoke an already-expired waiver, so
    # simulate a revoke that landed just before expiry via direct DB write.
    with waivers_module._get_conn() as conn:
        conn.execute(
            "UPDATE waivers SET revoked_at = ?, revoked_by = 'human-2' WHERE waiver_id = ?",
            (time.time() - 3600, revoked_but_expired.waiver_id),
        )
        conn.commit()

    events = emit_expiry_events()
    assert events == []


def test_emit_expiry_events_rolls_back_claim_on_emit_failure(monkeypatch):
    """cubic P2: the original version committed expiry_notified=1 before calling
    _emit() — an Observatory failure mid-scan permanently lost that waiver's
    audit event with no way to retry. The claim must roll back on failure so a
    later scan picks it up again."""
    waiver = register_waiver(
        subject="test",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        effective_from=time.time() - 7200,
        expires_on=time.time() - 3600,
    )

    original_emit = waivers_module._emit

    def _failing_emit(*_args, **_kwargs):
        raise RuntimeError("observatory unavailable")

    monkeypatch.setattr(waivers_module, "_emit", _failing_emit)
    first = emit_expiry_events()
    assert first == []
    assert get_waiver(waiver.waiver_id).expiry_notified is False

    # cubic: undo() would also revert the autouse _isolated_db fixture's
    # _DB_PATH patch (same monkeypatch instance, function-scoped) — restore
    # only _emit specifically, not the whole monkeypatch session.
    monkeypatch.setattr(waivers_module, "_emit", original_emit)
    second = emit_expiry_events()
    assert len(second) == 1
    assert get_waiver(waiver.waiver_id).expiry_notified is True


def test_emit_expiry_events_claim_prevents_concurrent_duplicate(monkeypatch):
    """cubic P1: simulates a second concurrent caller claiming the row first —
    a waiver whose expiry_notified is already 1 by the time this call's UPDATE
    runs must be skipped, not double-emitted."""
    waiver = register_waiver(
        subject="test",
        justification="test",
        requestor="agent-1",
        approver="human-1",
        effective_from=time.time() - 7200,
        expires_on=time.time() - 3600,
    )

    real_get_conn = waivers_module._get_conn
    call_count = {"n": 0}

    def _racing_get_conn():
        call_count["n"] += 1
        # 1st call = the initial SELECT of candidates; 2nd call = this waiver's
        # own per-row claim UPDATE — inject the "other worker" race right before
        # that claim executes, so this call's UPDATE genuinely loses the race.
        if call_count["n"] == 2:
            other = real_get_conn()
            other.execute(
                "UPDATE waivers SET expiry_notified = 1 WHERE waiver_id = ?",
                (waiver.waiver_id,),
            )
            other.commit()
        return real_get_conn()

    monkeypatch.setattr(waivers_module, "_get_conn", _racing_get_conn)
    events = emit_expiry_events()
    assert events == []


# ── Routes ────────────────────────────────────────────────────────────────────

_TEST_INTERNAL_SECRET = os.environ["INTERNAL_SECRET"]


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, headers={"X-Internal-Secret": _TEST_INTERNAL_SECRET})


@pytest.fixture()
def unauthenticated_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_route_create_waiver(client):
    resp = client.post(
        "/compliance/waivers",
        json={
            "subject": "test",
            "justification": "test",
            "requestor": "agent-1",
            "approver": "human-1",
            "expires_on": time.time() + 3600,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"
    assert body["subject"] == "test"


def test_route_create_waiver_unauthenticated_rejected(unauthenticated_client):
    resp = unauthenticated_client.post(
        "/compliance/waivers",
        json={
            "subject": "test",
            "justification": "test",
            "requestor": "agent-1",
            "approver": "human-1",
            "expires_on": time.time() + 3600,
        },
    )
    assert resp.status_code == 403


def test_route_create_waiver_invalid_request_returns_400(client):
    resp = client.post(
        "/compliance/waivers",
        json={
            "subject": "test",
            "justification": "test",
            "requestor": "agent-1",
            "approver": "human-1",
            "expires_on": time.time() - 3600,  # in the past relative to default effective_from
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_waiver_request"


def test_route_get_waiver_unknown_returns_404(client):
    resp = client.get("/compliance/waivers/WVR-DOESNOTEXIST")
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_waiver"


def test_route_list_waivers(client):
    client.post(
        "/compliance/waivers",
        json={
            "subject": "test",
            "justification": "test",
            "requestor": "agent-1",
            "approver": "human-1",
            "expires_on": time.time() + 3600,
        },
    )
    resp = client.get("/compliance/waivers")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_route_revoke_waiver(client):
    created = client.post(
        "/compliance/waivers",
        json={
            "subject": "test",
            "justification": "test",
            "requestor": "agent-1",
            "approver": "human-1",
            "expires_on": time.time() + 3600,
        },
    ).json()
    resp = client.post(
        f"/compliance/waivers/{created['waiver_id']}/revoke",
        json={"revoked_by": "human-2", "reason": "no longer needed"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"


def test_route_revoke_unknown_waiver_returns_404(client):
    resp = client.post(
        "/compliance/waivers/WVR-DOESNOTEXIST/revoke",
        json={"revoked_by": "human-2", "reason": "test"},
    )
    assert resp.status_code == 404


def test_route_check_expired_unauthenticated_rejected(unauthenticated_client):
    resp = unauthenticated_client.post("/compliance/waivers/check-expired")
    assert resp.status_code == 403


def test_route_check_expired_emits_and_reports_count(client):
    created = client.post(
        "/compliance/waivers",
        json={
            "subject": "test",
            "justification": "test",
            "requestor": "agent-1",
            "approver": "human-1",
            "effective_from": time.time() - 7200,
            "expires_on": time.time() - 3600,
        },
    ).json()
    resp = client.post("/compliance/waivers/check-expired")
    assert resp.status_code == 200
    body = resp.json()
    assert body["emitted"] == 1
    assert body["waiver_ids"] == [created["waiver_id"]]


def test_route_open_when_internal_secret_unset(monkeypatch):
    monkeypatch.setattr(waivers_routes_module, "_INTERNAL_SECRET", "")
    app = FastAPI()
    app.include_router(router)
    open_client = TestClient(app)
    resp = open_client.post(
        "/compliance/waivers",
        json={
            "subject": "test",
            "justification": "test",
            "requestor": "agent-1",
            "approver": "human-1",
            "expires_on": time.time() + 3600,
        },
    )
    assert resp.status_code == 200
