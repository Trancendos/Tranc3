"""Waiver expiry, revocation and durable history must fail closed."""

from __future__ import annotations

import pytest

from src.townhall.plm import DeliverableKind, GateBlocked, PlmService


@pytest.fixture
def service(tmp_path, monkeypatch):
    import src.townhall.plm as mod

    monkeypatch.setattr(mod.time, "time", lambda: 1000000.0)
    plm = PlmService(db_path=tmp_path / "plm.sqlite")
    yield plm, mod
    plm.close()


def _item(plm):
    return plm.create("A document", DeliverableKind.DOCUMENT, "The Library")


def test_waiver_is_time_boxed_by_default(service):
    plm, _ = service
    item = _item(plm)
    waiver = plm.waive(item.id, "concept.business-case", "short exception", "admin")
    assert waiver.expires_at == 1000000.0 + 86400.0
    assert plm.gate_status(item.id).can_advance


def test_expired_waiver_never_satisfies_gate(service, monkeypatch):
    plm, mod = service
    item = _item(plm)
    plm.waive(item.id, "concept.business-case", "temporary", "admin", ttl_seconds=60)
    monkeypatch.setattr(mod.time, "time", lambda: 1000060.0)
    assert not plm.gate_status(item.id).can_advance
    with pytest.raises(GateBlocked):
        plm.advance(item.id, approver="admin")
    assert plm.get(item.id).stage.value == "concept"


@pytest.mark.parametrize("ttl", [0, -1, 86400 * 31, True, "3600", float("inf"), float("nan")])
def test_invalid_or_unbounded_ttl_is_rejected(service, ttl):
    plm, _ = service
    item = _item(plm)
    with pytest.raises(ValueError, match="waiver duration"):
        plm.waive(item.id, "concept.business-case", "exception", "admin", ttl_seconds=ttl)


def test_revocation_blocks_gate_and_keeps_history(service):
    plm, _ = service
    item = _item(plm)
    plm.waive(item.id, "concept.business-case", "exception", "approver")
    assert plm.gate_status(item.id).can_advance
    plm.revoke_waiver(item.id, "concept.business-case", "withdrawn", "security")
    assert not plm.gate_status(item.id).can_advance
    with pytest.raises(GateBlocked):
        plm.advance(item.id, approver="security")
    events = plm.waiver_history(item.id)
    assert [event["event"] for event in events] == ["granted", "revoked"]
    assert events[1]["actor"] == "security"
    assert events[1]["reason"] == "withdrawn"


def test_expired_waiver_cannot_be_revoked_as_active(service, monkeypatch):
    plm, mod = service
    item = _item(plm)
    plm.waive(item.id, "concept.business-case", "exception", "approver", ttl_seconds=60)
    monkeypatch.setattr(mod.time, "time", lambda: 1000061.0)
    with pytest.raises(ValueError, match="active waiver"):
        plm.revoke_waiver(item.id, "concept.business-case", "expired", "security")


def test_revoke_requires_named_actor_and_reason(service):
    plm, _ = service
    item = _item(plm)
    plm.waive(item.id, "concept.business-case", "exception", "approver")
    with pytest.raises(ValueError):
        plm.revoke_waiver(item.id, "concept.business-case", "", "admin")
    with pytest.raises(ValueError):
        plm.revoke_waiver(item.id, "concept.business-case", "withdrawn", " ")


def test_legacy_indefinite_waivers_do_not_open_gate(service):
    plm, _ = service
    item = _item(plm)
    with plm._lock:
        plm._conn.execute(
            "INSERT INTO waivers (deliverable_id,criterion_id,reason,approver,waived_at) "
            "VALUES (?,?,?,?,?)",
            (item.id, "concept.business-case", "old grant", "admin", 10.0),
        )
        plm._conn.commit()
    assert not plm.gate_status(item.id).can_advance


def test_expiry_survives_restart(tmp_path, monkeypatch):
    import src.townhall.plm as mod

    monkeypatch.setattr(mod.time, "time", lambda: 1000000.0)
    path = tmp_path / "plm.sqlite"
    first = PlmService(db_path=path)
    item = _item(first)
    first.waive(item.id, "concept.business-case", "temporary", "admin", ttl_seconds=60)
    first.close()
    second = PlmService(db_path=path)
    try:
        assert second.gate_status(item.id).can_advance
        monkeypatch.setattr(mod.time, "time", lambda: 1000061.0)
        assert not second.gate_status(item.id).can_advance
        assert second.waiver_history(item.id)[0]["event"] == "granted"
    finally:
        second.close()


def test_migration_old_sqlite_schema_is_fail_closed(tmp_path, monkeypatch):
    import sqlite3

    import src.townhall.plm as mod

    monkeypatch.setattr(mod.time, "time", lambda: 1000000.0)
    path = tmp_path / "old-plm.sqlite"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE waivers (deliverable_id TEXT NOT NULL, criterion_id TEXT NOT NULL, "
        "reason TEXT NOT NULL, approver TEXT NOT NULL, waived_at REAL NOT NULL, "
        "PRIMARY KEY(deliverable_id, criterion_id))"
    )
    db.commit()
    db.close()
    plm = PlmService(db_path=path)
    try:
        item = _item(plm)
        with plm._lock:
            plm._conn.execute(
                "INSERT INTO waivers (deliverable_id,criterion_id,reason,approver,waived_at) "
                "VALUES (?,?,?,?,?)",
                (item.id, "concept.business-case", "legacy", "admin", 0),
            )
            plm._conn.commit()
        assert not plm.gate_status(item.id).can_advance
        waiver = plm.waive(item.id, "concept.business-case", "renewed", "admin")
        assert waiver.expires_at == 1086400.0
        assert plm.gate_status(item.id).can_advance
    finally:
        plm.close()


def test_revocation_persists_after_restart(tmp_path, monkeypatch):
    import src.townhall.plm as mod

    monkeypatch.setattr(mod.time, "time", lambda: 1000000.0)
    path = tmp_path / "plm.sqlite"
    first = PlmService(db_path=path)
    item = _item(first)
    first.waive(item.id, "concept.business-case", "exception", "admin")
    first.revoke_waiver(item.id, "concept.business-case", "withdrawn", "security")
    first.close()
    second = PlmService(db_path=path)
    try:
        assert not second.gate_status(item.id).can_advance
        assert [e["event"] for e in second.waiver_history(item.id)] == ["granted", "revoked"]
    finally:
        second.close()


@pytest.fixture
def http_client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth import get_current_user
    from src.townhall import plm_routes

    plm = PlmService(db_path=tmp_path / "api-plm.sqlite")
    monkeypatch.setattr(plm_routes, "get_plm", lambda: plm)
    app = FastAPI()
    app.include_router(plm_routes.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "admin",
        "username": "admin",
        "role": "admin",
    }
    yield TestClient(app), app, plm, get_current_user
    plm.close()


def test_revoke_route_uses_authenticated_actor(http_client):
    client, _, plm, _ = http_client
    item = _item(plm)
    r = client.post(
        f"/townhall/plm/deliverables/{item.id}/waivers",
        json={"criterion_id": "concept.business-case", "reason": "temporary", "ttl_seconds": 60},
    )
    assert r.status_code == 201
    r2 = client.post(
        f"/townhall/plm/deliverables/{item.id}/waivers/concept.business-case/revoke",
        json={"reason": "withdrawn", "actor": "spoofed"},
    )
    assert r2.status_code == 200
    assert plm.waiver_history(item.id)[-1]["actor"] == "admin"
    assert not plm.gate_status(item.id).can_advance


def test_waiver_history_requires_admin(http_client):
    client, app, plm, dependency = http_client
    item = _item(plm)
    app.dependency_overrides[dependency] = lambda: {"sub": "viewer", "role": "viewer"}
    r = client.get(f"/townhall/plm/deliverables/{item.id}/waivers/history")
    assert r.status_code == 403
