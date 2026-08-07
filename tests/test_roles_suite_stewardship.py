# tests/test_roles_suite_stewardship.py
# Matrix Suites Stage 7.5: src/roles/suite_stewardship.py cross-references
# Magna Carta's matrix_suites.yaml against the live Role Registry rather than
# seeding 8 synthetic new /roles rows. Uses a small fixture registry (not the
# real submodule file) so the test doesn't depend on the submodule pin.

from __future__ import annotations

import yaml

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
