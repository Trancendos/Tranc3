# tests/test_roles_suite_stewardship.py
# Matrix Suites Stage 7.5: src/roles/suite_stewardship.py cross-references
# Magna Carta's matrix_suites.yaml against the live Role Registry rather than
# seeding 8 synthetic new /roles rows. Uses a small fixture registry (not the
# real submodule file) so the test doesn't depend on the submodule pin.

from __future__ import annotations

import pytest
import yaml

from src.compliance.matrix_suites import MatrixSuitesRegistryError
from src.roles import registry as registry_module
from src.roles.registry import RoleRegistry
from src.roles.suite_stewardship import get_suite_stewardship, list_suite_stewardships

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
            "next_review": "2026-08-31",
        },
        {
            "suite_id": "SUITE-SEC",
            "name": "Security Suite",
            "pillar": "Security",
            "steward_ai": "Renik",
            "steward_location": "Cryptex",
            "presiding_prime": "The Guardian (Marcus Magnolia)",
            "escalation": ["The Guardian (Marcus Magnolia)", "Cornelius MacIntyre", "Human owner"],
            "review_cadence": "monthly",
            "next_review": "2026-08-31",
        },
    ],
}


def _write_fixture(tmp_path) -> str:
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(FIXTURE), encoding="utf-8")
    return str(p)


def _fresh_registry(tmp_path, monkeypatch) -> RoleRegistry:
    reg = RoleRegistry(db_path=tmp_path / "suite_stewardship_test.db")
    monkeypatch.setattr(registry_module, "_registry", reg)
    return reg


class TestListSuiteStewardships:
    def test_matches_baseline_when_untouched(self, tmp_path, monkeypatch):
        _fresh_registry(tmp_path, monkeypatch)
        path = _write_fixture(tmp_path)
        results = list_suite_stewardships(path)
        assert len(results) == 2
        fin = next(r for r in results if r.suite_id == "SUITE-FIN")
        assert fin.steward_location == "Royal Bank of Arcadia"
        assert fin.designed_steward_ai == "Dorris Fontaine"
        assert fin.current_steward_ai == "Dorris Fontaine"
        assert fin.drifted is False
        assert fin.review_cadence == "monthly"
        assert fin.next_review == "2026-08-31"
        assert fin.escalation == ["Dorris Fontaine (Prime)", "Cornelius MacIntyre", "Human owner"]

    def test_drift_detected_after_reassignment(self, tmp_path, monkeypatch):
        reg = _fresh_registry(tmp_path, monkeypatch)
        path = _write_fixture(tmp_path)
        reg.assign_ai("Cryptex", "New Security AI", changed_by="test", reason="rotation")
        results = list_suite_stewardships(path)
        sec = next(r for r in results if r.suite_id == "SUITE-SEC")
        assert sec.designed_steward_ai == "Renik"
        assert sec.current_steward_ai == "New Security AI"
        assert sec.drifted is True

    def test_drift_detected_when_vacated(self, tmp_path, monkeypatch):
        reg = _fresh_registry(tmp_path, monkeypatch)
        path = _write_fixture(tmp_path)
        reg.remove_ai("Cryptex", changed_by="test")
        results = list_suite_stewardships(path)
        sec = next(r for r in results if r.suite_id == "SUITE-SEC")
        assert sec.current_steward_ai is None
        assert sec.drifted is True

    def test_missing_registry_file_returns_empty(self, tmp_path, monkeypatch):
        _fresh_registry(tmp_path, monkeypatch)
        assert list_suite_stewardships(str(tmp_path / "nope.yaml")) == []

    def test_non_mapping_suite_entry_raises_registry_error(self, tmp_path, monkeypatch):
        """CodeQL/CodeRabbit-flagged regression: a null or scalar entry in the
        suites list used to reach suite.get(...) and raise an unhandled
        AttributeError — routes only catch MatrixSuitesError, so this became
        an unhandled 500 instead of a clean 404 invalid_registry."""
        _fresh_registry(tmp_path, monkeypatch)
        p = tmp_path / "matrix_suites.yaml"
        p.write_text(
            yaml.safe_dump({"meta": {}, "suites": [FIXTURE["suites"][0], None]}),
            encoding="utf-8",
        )
        with pytest.raises(MatrixSuitesRegistryError):
            list_suite_stewardships(str(p))


class TestGetSuiteStewardship:
    def test_known_suite(self, tmp_path, monkeypatch):
        _fresh_registry(tmp_path, monkeypatch)
        path = _write_fixture(tmp_path)
        result = get_suite_stewardship("SUITE-FIN", path)
        assert result is not None
        assert result.name == "Financial Suite"

    def test_unknown_suite_returns_none(self, tmp_path, monkeypatch):
        _fresh_registry(tmp_path, monkeypatch)
        path = _write_fixture(tmp_path)
        assert get_suite_stewardship("SUITE-NOPE", path) is None

    def test_duplicate_suite_id_raises_registry_error(self, tmp_path, monkeypatch):
        """cubic/Qodo-flagged regression: returning the first match for a
        duplicated suite_id could silently point a caller at the wrong
        suite's steward/escalation chain instead of surfacing the registry
        as broken — mirrors src/compliance/matrix_suites.py's _find_suite()."""
        _fresh_registry(tmp_path, monkeypatch)
        p = tmp_path / "matrix_suites.yaml"
        dup = dict(FIXTURE["suites"][0])
        p.write_text(
            yaml.safe_dump({"meta": {}, "suites": [FIXTURE["suites"][0], dup]}),
            encoding="utf-8",
        )
        with pytest.raises(MatrixSuitesRegistryError):
            get_suite_stewardship("SUITE-FIN", str(p))
