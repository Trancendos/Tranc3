"""
Tests for Matrix Suites Observatory event emission (src/compliance/matrix_suites.py)
and its FastAPI routes (src/compliance/matrix_suites_routes.py) — Magna Carta Stage 7.2.

Uses a small fixture registry rather than the real submodule file so overdue/cadence
behaviour is deterministic regardless of when the real matrix_suites.yaml's next_review
dates fall.
"""

from __future__ import annotations

from datetime import date

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.compliance.matrix_suites as matrix_suites_module
from src.compliance.matrix_suites import (
    MatrixSuitesError,
    emit_overdue_events,
    list_suite_health,
    load_suites,
    record_escalated,
    record_matrix_changed,
    record_review_completed,
)
from src.compliance.matrix_suites_routes import router
from src.observability.observatory import Observatory


@pytest.fixture(autouse=True)
def _reset_overdue_throttle():
    """emit_overdue_events throttles per suite per calendar day via a module-level
    dict; reset it between tests so one test's emission doesn't suppress another's."""
    matrix_suites_module._last_overdue_emit.clear()
    yield
    matrix_suites_module._last_overdue_emit.clear()

FIXTURE = {
    "meta": {"observatory_event_prefix": "governance.suite"},
    "suites": [
        {
            "suite_id": "SUITE-FIN",
            "name": "Financial Suite",
            "pillar": "Commercial / Financial",
            "steward_ai": "Dorris Fontaine",
            "steward_location": "Royal Bank of Arcadia",
            "presiding_prime": "Dorris Fontaine",
            "escalation": ["Dorris Fontaine (Prime)", "Cornelius MacIntyre", "Human owner"],
            "review_cadence": "monthly",
            "next_review": "2020-01-01",  # deliberately in the past -> overdue
            "observatory_events": "governance.suite.financial.*",
            "kpi": "0 overdue matrix reviews",
            "matrices": [
                {
                    "id": "FINANCIAL-MATRIX",
                    "repo": "magna-carta",
                    "path": "docs/compliance/FINANCIAL-MATRIX.md",
                    "register": "MC-017",
                },
            ],
        },
        {
            "suite_id": "SUITE-KNO",
            "name": "Knowledge Suite",
            "pillar": "Knowledge",
            "steward_ai": "Zimik",
            "steward_location": "The Library",
            "presiding_prime": "Norman Hawkins",
            "escalation": ["Norman Hawkins", "Cornelius MacIntyre", "Human owner"],
            "review_cadence": "quarterly",
            "next_review": "2099-01-01",  # far future -> not overdue
            "observatory_events": "governance.suite.knowledge.*",
            "kpi": "wiki mirrors canonical sources",
            "matrices": [
                {
                    "id": "KNOWLEDGE-MATRIX",
                    "repo": "magna-carta",
                    "path": "docs/compliance/KNOWLEDGE-MATRIX.md",
                    "register": "MC-018",
                },
            ],
        },
    ],
}


@pytest.fixture()
def registry_path(tmp_path):
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(FIXTURE), encoding="utf-8")
    return str(p)


@pytest.fixture()
def observatory():
    return Observatory()


def test_load_suites_missing_file_returns_empty(tmp_path):
    assert load_suites(str(tmp_path / "nope.yaml")) == []


def test_load_suites_reads_fixture(registry_path):
    suites = load_suites(registry_path)
    assert {s["suite_id"] for s in suites} == {"SUITE-FIN", "SUITE-KNO"}


def test_list_suite_health_flags_overdue(registry_path):
    health = {h.suite_id: h for h in list_suite_health(path=registry_path)}
    assert health["SUITE-FIN"].overdue is True
    assert health["SUITE-FIN"].days_overdue > 0
    assert health["SUITE-KNO"].overdue is False
    assert health["SUITE-KNO"].days_overdue == 0


def test_list_suite_health_event_prefix_strips_wildcard(registry_path):
    health = {h.suite_id: h for h in list_suite_health(path=registry_path)}
    assert health["SUITE-FIN"].event_prefix == "governance.suite.financial"


def test_emit_overdue_events_emits_only_for_overdue_suites(registry_path, observatory):
    events = emit_overdue_events(observatory=observatory, path=registry_path)
    assert len(events) == 1
    assert events[0].event_type == "governance.suite.financial.review.overdue"
    assert events[0].target == "SUITE-FIN"
    assert events[0].metadata["days_overdue"] > 0


def test_emit_overdue_events_throttled_same_day(registry_path, observatory):
    first = emit_overdue_events(observatory=observatory, path=registry_path, today=date(2026, 6, 1))
    second = emit_overdue_events(observatory=observatory, path=registry_path, today=date(2026, 6, 1))
    assert len(first) == 1
    assert len(second) == 0  # same day -> throttled


def test_emit_overdue_events_fires_again_next_day(registry_path, observatory):
    emit_overdue_events(observatory=observatory, path=registry_path, today=date(2026, 6, 1))
    next_day = emit_overdue_events(observatory=observatory, path=registry_path, today=date(2026, 6, 2))
    assert len(next_day) == 1


def test_record_review_completed_emits_event(registry_path, observatory):
    event = record_review_completed(
        "SUITE-KNO", "Zimik", "monthly check complete", observatory=observatory, path=registry_path
    )
    assert event.event_type == "governance.suite.knowledge.review.completed"
    assert event.actor == "Zimik"
    assert event.metadata["notes"] == "monthly check complete"


def test_record_review_completed_unknown_suite_raises(registry_path, observatory):
    with pytest.raises(MatrixSuitesError):
        record_review_completed("SUITE-NOPE", "Someone", observatory=observatory, path=registry_path)


def test_record_matrix_changed_emits_event(registry_path, observatory):
    event = record_matrix_changed(
        "SUITE-FIN", "FINANCIAL-MATRIX", observatory=observatory, path=registry_path
    )
    assert event.event_type == "governance.suite.financial.matrix.changed"
    assert event.target == "FINANCIAL-MATRIX"


def test_record_matrix_changed_rejects_non_member_matrix(registry_path, observatory):
    with pytest.raises(MatrixSuitesError):
        record_matrix_changed(
            "SUITE-FIN", "KNOWLEDGE-MATRIX", observatory=observatory, path=registry_path
        )


def test_record_escalated_emits_event(registry_path, observatory):
    event = record_escalated(
        "SUITE-KNO",
        "Zimik",
        "Norman Hawkins",
        "review overdue by 30 days",
        observatory=observatory,
        path=registry_path,
    )
    assert event.event_type == "governance.suite.knowledge.escalated"
    assert event.actor == "Zimik"
    assert event.target == "Norman Hawkins"


def test_record_escalated_rejects_role_not_in_chain(registry_path, observatory):
    with pytest.raises(MatrixSuitesError):
        record_escalated(
            "SUITE-KNO",
            "Zimik",
            "Someone Else",
            "reason",
            observatory=observatory,
            path=registry_path,
        )


def test_record_escalated_rejects_backwards_move(registry_path, observatory):
    with pytest.raises(MatrixSuitesError):
        record_escalated(
            "SUITE-KNO",
            "Cornelius MacIntyre",
            "Zimik",
            "reason",
            observatory=observatory,
            path=registry_path,
        )


# ── Routes ────────────────────────────────────────────────────────────────────


@pytest.fixture()
def client(registry_path, monkeypatch):
    monkeypatch.setenv("MATRIX_SUITES_PATH", registry_path)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_route_list_suites(client):
    resp = client.get("/compliance/suites")
    assert resp.status_code == 200
    body = resp.json()
    assert {s["suite_id"] for s in body} == {"SUITE-FIN", "SUITE-KNO"}


def test_route_suite_detail_found(client):
    resp = client.get("/compliance/suites/SUITE-FIN")
    assert resp.status_code == 200
    assert resp.json()["suite_id"] == "SUITE-FIN"


def test_route_suite_detail_not_found(client):
    resp = client.get("/compliance/suites/SUITE-NOPE")
    assert resp.status_code == 404


def test_route_check_overdue(client):
    resp = client.post("/compliance/suites/check-overdue")
    assert resp.status_code == 200
    assert resp.json()["emitted"] >= 1


def test_route_complete_review(client):
    resp = client.post(
        "/compliance/suites/SUITE-KNO/review",
        json={"reviewer": "Zimik", "notes": "done"},
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "governance.suite.knowledge.review.completed"


def test_route_complete_review_unknown_suite(client):
    resp = client.post(
        "/compliance/suites/SUITE-NOPE/review",
        json={"reviewer": "Zimik"},
    )
    assert resp.status_code == 404


def test_route_matrix_changed(client):
    resp = client.post(
        "/compliance/suites/SUITE-FIN/matrix-changed",
        json={"matrix_id": "FINANCIAL-MATRIX"},
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "governance.suite.financial.matrix.changed"


def test_route_escalate(client):
    resp = client.post(
        "/compliance/suites/SUITE-KNO/escalate",
        json={"from_role": "Zimik", "to_role": "Norman Hawkins", "reason": "overdue"},
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "governance.suite.knowledge.escalated"
