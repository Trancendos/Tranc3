"""
Tests for Matrix Suites Observatory event emission (src/compliance/matrix_suites.py)
and its FastAPI routes (src/compliance/matrix_suites_routes.py) — Magna Carta Stage 7.2.

Uses a small fixture registry rather than the real submodule file so overdue/cadence
behaviour is deterministic regardless of when the real matrix_suites.yaml's next_review
dates fall.
"""

from __future__ import annotations

import copy
import os
from datetime import date

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.compliance.matrix_suites as matrix_suites_module
import src.compliance.matrix_suites_routes as matrix_suites_routes_module
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


NO_PREFIX_FIXTURE = {
    "meta": {"observatory_event_prefix": "governance.suite"},
    "suites": [
        {
            "suite_id": "SUITE-NOPFX",
            "name": "No Prefix Suite",
            "pillar": "Knowledge",
            "steward_ai": "Solo Steward",
            "steward_location": "The Library",
            "presiding_prime": "Norman Hawkins",
            "escalation": ["Human owner"],
            "review_cadence": "quarterly",
            "next_review": "2099-01-01",
            # deliberately missing observatory_events, to exercise the
            # "refuse to emit a malformed event name" guard
            "kpi": "n/a",
            "matrices": [
                {
                    "id": "NOPFX-MATRIX",
                    "repo": "magna-carta",
                    "path": "docs/compliance/NOPFX-MATRIX.md",
                    "register": None,
                },
            ],
        },
    ],
}


@pytest.fixture()
def no_prefix_registry_path(tmp_path):
    p = tmp_path / "matrix_suites_no_prefix.yaml"
    p.write_text(yaml.safe_dump(NO_PREFIX_FIXTURE), encoding="utf-8")
    return str(p)


@pytest.fixture()
def observatory():
    return Observatory()


def test_load_suites_missing_file_returns_empty(tmp_path):
    assert load_suites(str(tmp_path / "nope.yaml")) == []


def test_load_suites_reads_fixture(registry_path):
    suites = load_suites(registry_path)
    assert {s["suite_id"] for s in suites} == {"SUITE-FIN", "SUITE-KNO"}


def test_load_suites_non_list_suites_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump({"suites": {"not": "a list"}}), encoding="utf-8")
    with pytest.raises(MatrixSuitesError):
        load_suites(str(p))


def test_load_suites_non_dict_root_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(["not", "a", "mapping"]), encoding="utf-8")
    with pytest.raises(MatrixSuitesError):
        load_suites(str(p))


def test_load_suites_malformed_yaml_raises_matrix_suites_error(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("suites: [\n  - this is not: valid: yaml: at all", encoding="utf-8")
    with pytest.raises(MatrixSuitesError):
        load_suites(str(p))


def test_list_suite_health_flags_overdue(registry_path):
    health = {h.suite_id: h for h in list_suite_health(path=registry_path)}
    assert health["SUITE-FIN"].overdue is True
    assert health["SUITE-FIN"].days_overdue > 0
    assert health["SUITE-FIN"].next_review_valid is True
    assert health["SUITE-KNO"].overdue is False
    assert health["SUITE-KNO"].days_overdue == 0
    assert health["SUITE-KNO"].next_review_valid is True


def test_list_suite_health_missing_next_review_is_failsafe_overdue(tmp_path):
    fixture = copy.deepcopy(FIXTURE)
    del fixture["suites"][1]["next_review"]  # SUITE-KNO
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    health = {h.suite_id: h for h in list_suite_health(path=str(p))}
    assert health["SUITE-KNO"].overdue is True
    assert health["SUITE-KNO"].next_review_valid is False


def test_list_suite_health_date_object_next_review_is_parsed_not_failsafe(tmp_path):
    """A real matrix_suites.yaml quotes next_review as a string, but an
    unquoted YAML date (e.g. `next_review: 2026-08-31`) is auto-parsed by
    PyYAML into a datetime.date object. That's a genuine, valid future date
    and must be read as such (not overdue) rather than lumped into the
    fail-safe "corrupt value" bucket, which would falsely report a healthy
    suite as overdue and spam a daily review.overdue event."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][1]["next_review"] = date(2099, 1, 1)  # SUITE-KNO
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    health = {h.suite_id: h for h in list_suite_health(path=str(p))}
    assert health["SUITE-KNO"].overdue is False
    assert health["SUITE-KNO"].next_review_valid is True
    assert health["SUITE-KNO"].next_review == "2099-01-01"


def test_list_suite_health_past_date_object_next_review_is_overdue(tmp_path):
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][1]["next_review"] = date(2020, 1, 1)  # SUITE-KNO
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    health = {h.suite_id: h for h in list_suite_health(path=str(p))}
    assert health["SUITE-KNO"].overdue is True
    assert health["SUITE-KNO"].next_review_valid is True
    assert health["SUITE-KNO"].days_overdue > 0


def test_list_suite_health_garbage_next_review_is_failsafe_overdue(tmp_path):
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][1]["next_review"] = "not-a-date"  # SUITE-KNO
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    health = {h.suite_id: h for h in list_suite_health(path=str(p))}
    assert health["SUITE-KNO"].overdue is True
    assert health["SUITE-KNO"].next_review_valid is False


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
    second = emit_overdue_events(
        observatory=observatory, path=registry_path, today=date(2026, 6, 1)
    )
    assert len(first) == 1
    assert len(second) == 0  # same day -> throttled


def test_emit_overdue_events_fires_again_next_day(registry_path, observatory):
    emit_overdue_events(observatory=observatory, path=registry_path, today=date(2026, 6, 1))
    next_day = emit_overdue_events(
        observatory=observatory, path=registry_path, today=date(2026, 6, 2)
    )
    assert len(next_day) == 1


def test_emit_overdue_events_logs_warning_when_overdue_suite_has_no_prefix(
    tmp_path, observatory, caplog
):
    fixture = copy.deepcopy(NO_PREFIX_FIXTURE)
    fixture["suites"][0]["next_review"] = "2020-01-01"  # SUITE-NOPFX, overdue
    p = tmp_path / "matrix_suites_no_prefix.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    with caplog.at_level("WARNING"):
        events = emit_overdue_events(observatory=observatory, path=str(p))

    assert events == []
    assert any("SUITE-NOPFX" in record.message for record in caplog.records)


def test_record_review_completed_emits_event(registry_path, observatory):
    event = record_review_completed(
        "SUITE-KNO", "Zimik", "monthly check complete", observatory=observatory, path=registry_path
    )
    assert event.event_type == "governance.suite.knowledge.review.completed"
    assert event.actor == "Zimik"
    assert event.metadata["notes"] == "monthly check complete"


def test_record_review_completed_unknown_suite_raises(registry_path, observatory):
    with pytest.raises(MatrixSuitesError):
        record_review_completed(
            "SUITE-NOPE", "Someone", observatory=observatory, path=registry_path
        )


def test_record_review_completed_missing_prefix_raises(no_prefix_registry_path, observatory):
    with pytest.raises(MatrixSuitesError):
        record_review_completed(
            "SUITE-NOPFX", "Someone", observatory=observatory, path=no_prefix_registry_path
        )


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


def test_record_matrix_changed_tolerates_malformed_matrix_entry(tmp_path, observatory):
    """A non-dict entry in a suite's `matrices` list (registry drift/corruption)
    must not crash the comprehension with AttributeError — it should just be
    excluded from matrix_ids, so a genuinely non-member matrix_id still raises
    the normal MatrixSuitesValidationError instead of an unhandled 500."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][0]["matrices"].append("not-a-mapping")  # SUITE-FIN
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    event = record_matrix_changed(
        "SUITE-FIN", "FINANCIAL-MATRIX", observatory=observatory, path=str(p)
    )
    assert event.event_type == "governance.suite.financial.matrix.changed"

    with pytest.raises(MatrixSuitesError):
        record_matrix_changed("SUITE-FIN", "NOT-A-MEMBER", observatory=observatory, path=str(p))


def test_record_matrix_changed_missing_prefix_raises(no_prefix_registry_path, observatory):
    with pytest.raises(MatrixSuitesError):
        record_matrix_changed(
            "SUITE-NOPFX", "NOPFX-MATRIX", observatory=observatory, path=no_prefix_registry_path
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


def test_record_escalated_missing_prefix_raises(no_prefix_registry_path, observatory):
    with pytest.raises(MatrixSuitesError):
        record_escalated(
            "SUITE-NOPFX",
            "Solo Steward",
            "Human owner",
            "reason",
            observatory=observatory,
            path=no_prefix_registry_path,
        )


# ── Routes ────────────────────────────────────────────────────────────────────
#
# tests/conftest.py always sets INTERNAL_SECRET (falling back to a fixed test
# value if the env doesn't already have one), so matrix_suites_routes'
# _INTERNAL_SECRET is never "" in this suite — every POST call below needs
# the matching X-Internal-Secret header, same as it would against a real
# deployment with INTERNAL_SECRET configured.
_TEST_INTERNAL_SECRET = os.environ["INTERNAL_SECRET"]


@pytest.fixture()
def client(registry_path, monkeypatch):
    monkeypatch.setenv("MATRIX_SUITES_PATH", registry_path)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, headers={"X-Internal-Secret": _TEST_INTERNAL_SECRET})


@pytest.fixture()
def unauthenticated_client(registry_path, monkeypatch):
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


def test_route_complete_review_unknown_suite_does_not_leak_exception_text(client):
    resp = client.post(
        "/compliance/suites/SUITE-NOPE/review",
        json={"reviewer": "Zimik"},
    )
    assert resp.json() == {"error": "unknown_suite"}
    assert "SUITE-NOPE" not in resp.text


def test_route_post_rejects_missing_internal_secret(unauthenticated_client):
    resp = unauthenticated_client.post(
        "/compliance/suites/SUITE-KNO/review",
        json={"reviewer": "Zimik"},
    )
    assert resp.status_code == 403


def test_route_post_rejects_wrong_internal_secret(unauthenticated_client):
    resp = unauthenticated_client.post(
        "/compliance/suites/SUITE-KNO/review",
        json={"reviewer": "Zimik"},
        headers={"X-Internal-Secret": "wrong-secret"},
    )
    assert resp.status_code == 403


def test_route_post_accepts_no_secret_when_none_configured(registry_path, monkeypatch):
    monkeypatch.setenv("MATRIX_SUITES_PATH", registry_path)
    monkeypatch.setattr(matrix_suites_routes_module, "_INTERNAL_SECRET", "")
    app = FastAPI()
    app.include_router(router)
    open_client = TestClient(app)
    resp = open_client.post(
        "/compliance/suites/SUITE-KNO/review",
        json={"reviewer": "Zimik"},
    )
    assert resp.status_code == 200


def test_route_matrix_changed(client):
    resp = client.post(
        "/compliance/suites/SUITE-FIN/matrix-changed",
        json={"matrix_id": "FINANCIAL-MATRIX"},
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "governance.suite.financial.matrix.changed"


def test_route_matrix_changed_non_member_returns_400_not_404(client):
    """The suite_id is real — only the matrix_id is invalid — so this is a
    client validation error (400), not a missing resource (404)."""
    resp = client.post(
        "/compliance/suites/SUITE-FIN/matrix-changed",
        json={"matrix_id": "KNOWLEDGE-MATRIX"},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid_suite_request"}


def test_route_matrix_changed_unknown_suite_returns_404(client):
    resp = client.post(
        "/compliance/suites/SUITE-NOPE/matrix-changed",
        json={"matrix_id": "FINANCIAL-MATRIX"},
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "unknown_suite"}


def test_route_escalate(client):
    resp = client.post(
        "/compliance/suites/SUITE-KNO/escalate",
        json={"from_role": "Zimik", "to_role": "Norman Hawkins", "reason": "overdue"},
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "governance.suite.knowledge.escalated"


def test_route_escalate_invalid_role_returns_400_not_404(client):
    resp = client.post(
        "/compliance/suites/SUITE-KNO/escalate",
        json={"from_role": "Zimik", "to_role": "Someone Else", "reason": "overdue"},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid_suite_request"}


def test_route_escalate_unknown_suite_returns_404(client):
    resp = client.post(
        "/compliance/suites/SUITE-NOPE/escalate",
        json={"from_role": "Zimik", "to_role": "Norman Hawkins", "reason": "overdue"},
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "unknown_suite"}
