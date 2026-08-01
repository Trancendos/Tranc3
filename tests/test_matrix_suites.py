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
    MatrixSuitesRegistryError,
    MatrixSuitesValidationError,
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


def test_load_suites_non_utf8_file_raises_matrix_suites_error(tmp_path):
    """A registry file that isn't valid UTF-8 (encoding drift, a bad merge, a
    stray binary write) must classify as MatrixSuitesError, not surface an
    unhandled UnicodeDecodeError as a raw 500."""
    p = tmp_path / "bad_encoding.yaml"
    p.write_bytes(b"suites:\n  - suite_id: \xff\xfe not valid utf-8\n")
    with pytest.raises(MatrixSuitesError):
        load_suites(str(p))


def test_list_suite_health_non_string_suite_id_is_coerced(tmp_path, observatory):
    """A registry entry with a non-string suite_id (e.g. an unquoted YAML int)
    must not crash emit_overdue_events()'s throttle-map dict key lookup —
    str()-coercing suite_id up front keeps it hashable and comparable no
    matter what the raw registry value's type is."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][0]["suite_id"] = 12345  # SUITE-FIN, deliberately non-string
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    health = {h.suite_id: h for h in list_suite_health(path=str(p))}
    assert "12345" in health
    assert health["12345"].overdue is True

    events = emit_overdue_events(observatory=observatory, path=str(p))
    assert any(e.target == "12345" for e in events)


def test_list_suite_health_skips_entries_with_missing_or_blank_suite_id(tmp_path, observatory):
    """Two distinct suite entries that both lack a usable suite_id (one
    missing the key entirely, one blank) must not both coerce to "" and
    collapse into a single, shared throttle-map key — list_suite_health()
    excludes them instead of listing them under a collided "" identifier."""
    fixture = copy.deepcopy(FIXTURE)
    del fixture["suites"][0]["suite_id"]  # was SUITE-FIN
    fixture["suites"][1]["suite_id"] = "   "  # was SUITE-KNO, blank after strip
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    health = list_suite_health(path=str(p))
    assert health == []

    events = emit_overdue_events(observatory=observatory, path=str(p))
    assert events == []


def test_list_suite_health_skips_duplicate_suite_id(tmp_path, observatory):
    """Two distinct registry entries sharing one suite_id would collide on
    the same overdue throttle key, and _find_suite() would always resolve to
    whichever came first -- list_suite_health() excludes both duplicates
    entirely rather than silently picking a winner."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][1]["suite_id"] = "SUITE-FIN"  # collide with suites[0]
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    health = list_suite_health(path=str(p))
    assert health == []


def test_list_suite_health_skips_whitespace_padded_duplicate_suite_id(tmp_path, observatory):
    """Duplicate detection compares the coerced (stripped) id, so " SUITE-FIN "
    counts as the same identifier as "SUITE-FIN"."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][1]["suite_id"] = " SUITE-FIN "  # collide with suites[0]
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    health = list_suite_health(path=str(p))
    assert health == []


def test_list_suite_health_strips_suite_id_for_lookup_consistency(tmp_path, observatory):
    """A registry suite_id with surrounding whitespace (e.g. " fin ") is
    listed under its stripped form, matching what _find_suite() and the
    overdue throttle key use -- otherwise the suite would appear in
    list_suite_health() but be unreachable via the action endpoints."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][0]["suite_id"] = "  SUITE-FIN  "
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    health = {h.suite_id: h for h in list_suite_health(path=str(p))}
    assert "SUITE-FIN" in health
    assert "  SUITE-FIN  " not in health

    event = record_review_completed("SUITE-FIN", "Dorris", observatory=observatory, path=str(p))
    assert event.event_type == "governance.suite.financial.review.completed"


def test_emit_overdue_events_metadata_flags_invalid_next_review(tmp_path, observatory):
    """The overdue event's days_overdue is always 0 for the missing/
    unparseable-date fail-safe case (there's no real date to compute a count
    from) -- next_review_valid in the metadata lets a consumer distinguish
    that from a suite genuinely only 0-1 days overdue."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][0]["next_review"] = "not-a-date"  # SUITE-FIN
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    events = emit_overdue_events(observatory=observatory, path=str(p))
    fin_event = next(e for e in events if e.target == "SUITE-FIN")
    assert fin_event.metadata["next_review_valid"] is False
    assert fin_event.metadata["days_overdue"] == 0


def test_list_suite_health_skips_explicit_null_suite_id(tmp_path, observatory):
    """suite_id: null is present-but-None in the registry, not missing --
    suite.get(key, default) only supplies the default for a truly absent
    key, so a naive str(suite.get("suite_id", "")) would coerce None to the
    literal string "None" and list/emit it as a bogus suite instead of
    skipping the malformed entry."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][0]["suite_id"] = None  # was SUITE-FIN
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    health = list_suite_health(path=str(p))
    assert all(h.suite_id != "None" for h in health)
    assert len(health) == 1  # only SUITE-KNO survives

    events = emit_overdue_events(observatory=observatory, path=str(p))
    assert all(e.target != "None" for e in events)


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


def test_emit_overdue_events_does_not_throttle_on_record_failure(registry_path):
    """The suite must not be marked emitted for the day until obs.record()
    actually succeeds — otherwise a transient Observatory failure would
    silently suppress the overdue signal until the next calendar day even
    though no event ever reached the Observatory."""

    class _FailingObservatory:
        def record(self, *args, **kwargs):
            raise RuntimeError("observatory unavailable")

    with pytest.raises(RuntimeError):
        emit_overdue_events(
            observatory=_FailingObservatory(), path=registry_path, today=date(2026, 6, 1)
        )
    assert "SUITE-FIN" not in matrix_suites_module._last_overdue_emit

    real_observatory = Observatory()
    retried = emit_overdue_events(
        observatory=real_observatory, path=registry_path, today=date(2026, 6, 1)
    )
    assert len(retried) == 1  # not throttled -- the failed attempt didn't count


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


def test_record_review_completed_reaches_suite_with_non_string_suite_id(tmp_path, observatory):
    """A registry entry with a non-string suite_id (e.g. an unquoted YAML int)
    is listed by list_suite_health() as its str()-coerced form ("12345"). The
    action endpoints must resolve that same coerced string back to the suite —
    otherwise a suite visible in GET /compliance/suites would be permanently
    unreachable via POST /compliance/suites/12345/review."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][0]["suite_id"] = 12345  # SUITE-FIN, deliberately non-string
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    event = record_review_completed("12345", "Someone", observatory=observatory, path=str(p))
    assert event.event_type == "governance.suite.financial.review.completed"


def test_record_review_completed_rejects_null_suite_id(tmp_path, observatory):
    """A registry entry with suite_id: null must not be addressable as the
    literal string "None" -- _find_suite() applies the same missing/blank
    rule as list_suite_health(), which already excludes it from GET results."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][0]["suite_id"] = None  # was SUITE-FIN
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    with pytest.raises(MatrixSuitesError):
        record_review_completed("None", "Someone", observatory=observatory, path=str(p))


def test_record_review_completed_rejects_ambiguous_duplicate_suite_id(tmp_path, observatory):
    """Two registry entries sharing one suite_id are already excluded from
    list_suite_health() entirely -- _find_suite() must reject the same
    ambiguity rather than silently resolving to whichever came first, which
    could record an event against the wrong suite's configuration."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][1]["suite_id"] = "SUITE-FIN"  # collide with suites[0]
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    with pytest.raises(MatrixSuitesError):
        record_review_completed("SUITE-FIN", "Someone", observatory=observatory, path=str(p))


def test_record_review_completed_missing_prefix_raises(no_prefix_registry_path, observatory):
    with pytest.raises(MatrixSuitesRegistryError):
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


def test_record_matrix_changed_tolerates_non_list_matrices(tmp_path, observatory):
    """If `matrices` itself is the wrong type (e.g. a string or mapping,
    rather than an element inside it), the comprehension must not raise —
    it should degrade to an empty matrix set, matching the non-dict-entry
    guard above."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][0]["matrices"] = "not-a-list"  # SUITE-FIN
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    with pytest.raises(MatrixSuitesValidationError):
        record_matrix_changed("SUITE-FIN", "FINANCIAL-MATRIX", observatory=observatory, path=str(p))


def test_record_matrix_changed_missing_prefix_raises(no_prefix_registry_path, observatory):
    with pytest.raises(MatrixSuitesRegistryError):
        record_matrix_changed(
            "SUITE-NOPFX", "NOPFX-MATRIX", observatory=observatory, path=no_prefix_registry_path
        )


def test_record_matrix_changed_missing_prefix_wins_over_invalid_matrix_id(
    no_prefix_registry_path, observatory
):
    """Registry misconfiguration (missing observatory_events) must classify as
    MatrixSuitesRegistryError even when matrix_id is ALSO invalid (not a
    member) — the registry check runs before the membership check, so the
    400-vs-404 outcome doesn't depend on whether the request happens to be
    invalid too."""
    with pytest.raises(MatrixSuitesRegistryError):
        record_matrix_changed(
            "SUITE-NOPFX", "NOT-A-MEMBER", observatory=observatory, path=no_prefix_registry_path
        )


def test_record_matrix_changed_tolerates_unhashable_matrix_id(tmp_path, observatory):
    """A malformed registry entry whose `id` is itself a list/dict (invalid
    YAML drift) must not raise TypeError while building the membership set —
    it should be excluded like any other malformed entry, so a genuinely
    non-member matrix_id still raises the normal MatrixSuitesValidationError."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][0]["matrices"].append({"id": ["not", "hashable"]})  # SUITE-FIN
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    event = record_matrix_changed(
        "SUITE-FIN", "FINANCIAL-MATRIX", observatory=observatory, path=str(p)
    )
    assert event.event_type == "governance.suite.financial.matrix.changed"

    with pytest.raises(MatrixSuitesValidationError):
        record_matrix_changed("SUITE-FIN", "NOT-A-MEMBER", observatory=observatory, path=str(p))


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


def test_record_escalated_deduplicates_chain_with_repeated_steward(tmp_path, observatory):
    """escalation is raw registry data and can repeat steward_ai or contain
    blank/non-string entries. chain.index() must use each name's first
    occurrence consistently, or a duplicate could let a backward move be
    accepted (or a legitimate forward move be rejected)."""
    fixture = copy.deepcopy(FIXTURE)
    # SUITE-KNO: steward_ai "Zimik" also duplicated inside escalation, plus a
    # blank entry -- chain should still resolve to
    # ["Zimik", "Norman Hawkins", "Cornelius MacIntyre", "Human owner"].
    fixture["suites"][1]["escalation"] = [
        "Zimik",
        "",
        "Norman Hawkins",
        "Cornelius MacIntyre",
        "Human owner",
    ]
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    event = record_escalated(
        "SUITE-KNO", "Zimik", "Cornelius MacIntyre", "reason", observatory=observatory, path=str(p)
    )
    assert event.event_type == "governance.suite.knowledge.escalated"

    with pytest.raises(MatrixSuitesValidationError):
        record_escalated(
            "SUITE-KNO",
            "Cornelius MacIntyre",
            "Zimik",
            "reason",
            observatory=observatory,
            path=str(p),
        )


def test_record_escalated_tolerates_non_list_escalation(tmp_path, observatory):
    """If `escalation` is stored as e.g. a single string rather than a list,
    `list(...)` would iterate its characters and silently corrupt the chain.
    It must instead be normalized to an empty list, so the steward is the
    only valid chain link rather than a garbage set of single characters."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["suites"][1]["escalation"] = "Norman Hawkins"  # SUITE-KNO
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    with pytest.raises(MatrixSuitesValidationError):
        record_escalated(
            "SUITE-KNO",
            "Zimik",
            "Norman Hawkins",
            "reason",
            observatory=observatory,
            path=str(p),
        )


def test_record_escalated_missing_prefix_wins_over_invalid_roles(
    no_prefix_registry_path, observatory
):
    """Same ordering guarantee as matrix-changed: a suite with a misconfigured
    registry entry classifies as MatrixSuitesRegistryError even when
    from_role/to_role are ALSO not in the escalation chain."""
    with pytest.raises(MatrixSuitesRegistryError):
        record_escalated(
            "SUITE-NOPFX",
            "Nobody",
            "Also Nobody",
            "reason",
            observatory=observatory,
            path=no_prefix_registry_path,
        )


def test_record_escalated_missing_prefix_raises(no_prefix_registry_path, observatory):
    with pytest.raises(MatrixSuitesRegistryError):
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


@pytest.fixture()
def no_prefix_client(no_prefix_registry_path, monkeypatch):
    monkeypatch.setenv("MATRIX_SUITES_PATH", no_prefix_registry_path)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, headers={"X-Internal-Secret": _TEST_INTERNAL_SECRET})


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


def test_route_check_overdue_get_falls_through_to_suite_lookup(client):
    """A GET to the POST-only /check-overdue path resolves as a suite lookup
    (404 unknown suite) rather than 405 method-not-allowed. This is accepted,
    not fixed: Starlette's router scans all routes for a full match before
    falling back to any partial (method-mismatch) match, regardless of
    registration order, so a static route can never take priority over a
    catch-all GET /{suite_id} for a GET on that exact path without adding a
    path-pattern exclusion — not worth the complexity for a cosmetic status
    code with no security or data impact."""
    resp = client.get("/compliance/suites/check-overdue")
    assert resp.status_code == 404
    assert resp.json() == {"error": "Unknown suite_id: check-overdue"}


def test_route_complete_review(client):
    resp = client.post(
        "/compliance/suites/SUITE-KNO/review",
        json={"reviewer": "Zimik", "notes": "done"},
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "governance.suite.knowledge.review.completed"


def test_route_complete_review_rejects_blank_reviewer(client):
    resp = client.post(
        "/compliance/suites/SUITE-KNO/review",
        json={"reviewer": "   ", "notes": "done"},
    )
    assert resp.status_code == 422


def test_route_complete_review_rejects_oversized_notes(client):
    """notes is bounded via Field(max_length=...) so a caller can't grow the
    in-memory Observatory event buffer with an unbounded free-text payload."""
    resp = client.post(
        "/compliance/suites/SUITE-KNO/review",
        json={"reviewer": "Zimik", "notes": "x" * 5000},
    )
    assert resp.status_code == 422


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


def test_route_complete_review_missing_prefix_returns_invalid_registry_not_400(
    no_prefix_client,
):
    """A suite that exists but has no observatory_events configured is a
    registry problem, not something the caller's request can fix — must not
    be reported as invalid_suite_request (400)."""
    resp = no_prefix_client.post(
        "/compliance/suites/SUITE-NOPFX/review",
        json={"reviewer": "Solo Steward"},
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "invalid_registry"}


def test_route_matrix_changed_missing_prefix_returns_invalid_registry_not_400(
    no_prefix_client,
):
    resp = no_prefix_client.post(
        "/compliance/suites/SUITE-NOPFX/matrix-changed",
        json={"matrix_id": "NOPFX-MATRIX"},
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "invalid_registry"}


def test_route_escalate_missing_prefix_returns_invalid_registry_not_400(no_prefix_client):
    resp = no_prefix_client.post(
        "/compliance/suites/SUITE-NOPFX/escalate",
        json={"from_role": "Solo Steward", "to_role": "Human owner", "reason": "x"},
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "invalid_registry"}


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


def test_route_matrix_changed_rejects_blank_matrix_id(client):
    resp = client.post(
        "/compliance/suites/SUITE-FIN/matrix-changed",
        json={"matrix_id": "   "},
    )
    assert resp.status_code == 422


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


def test_route_escalate_rejects_blank_from_role(client):
    resp = client.post(
        "/compliance/suites/SUITE-KNO/escalate",
        json={"from_role": "   ", "to_role": "Norman Hawkins", "reason": "overdue"},
    )
    assert resp.status_code == 422


def test_route_escalate_rejects_blank_to_role(client):
    resp = client.post(
        "/compliance/suites/SUITE-KNO/escalate",
        json={"from_role": "Zimik", "to_role": "   ", "reason": "overdue"},
    )
    assert resp.status_code == 422


def test_route_escalate_unknown_suite_returns_404(client):
    resp = client.post(
        "/compliance/suites/SUITE-NOPE/escalate",
        json={"from_role": "Zimik", "to_role": "Norman Hawkins", "reason": "overdue"},
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "unknown_suite"}
