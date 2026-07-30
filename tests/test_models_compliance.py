# tests/test_models_compliance.py
# Tests for src/models/compliance.py — the Models Matrix <-> Magna-Carta
# MC-013 training-data-provenance gate.

from __future__ import annotations

import pytest

import src.models.compliance as compliance_module
from src.models.compliance import (
    ProvenanceClearanceRegistry,
    ProvenanceStatus,
    check_provenance,
    get_clearance_registry,
    platform_wide_risks,
)

MADAM_KRYSTAL = "Madam Krystal"  # Sashas Photo Studio — seeded NOT_ASSESSED risk
GEORGE_PORTER = "George Porter"  # no seed risk at all


@pytest.fixture
def registry(tmp_path):
    reg = ProvenanceClearanceRegistry(db_path=tmp_path / "provenance.db")
    yield reg
    reg.close()


class TestCheckProvenance:
    def test_ai_with_no_seed_risk_is_always_cleared(self, registry):
        result = check_provenance(GEORGE_PORTER, clearance_registry=registry)
        assert result.cleared is True
        assert result.risk is None

    def test_ai_with_open_seed_risk_is_not_cleared(self, registry):
        result = check_provenance(MADAM_KRYSTAL, clearance_registry=registry)
        assert result.cleared is False
        assert result.risk is not None
        assert result.risk.status == ProvenanceStatus.NOT_ASSESSED
        assert result.risk.mc_reference == "MC-013"

    def test_cleared_override_unblocks(self, registry):
        registry.clear(MADAM_KRYSTAL, cleared_by="Andrew Porter", notes="review complete")
        result = check_provenance(MADAM_KRYSTAL, clearance_registry=registry)
        assert result.cleared is True
        assert result.risk.status == ProvenanceStatus.CLEARED
        assert result.risk.cleared_by == "Andrew Porter"
        assert result.risk.admin_notes == "review complete"

    def test_verified_caveat_override_also_unblocks(self, registry):
        registry.clear(
            MADAM_KRYSTAL,
            cleared_by="Andrew Porter",
            notes="caveat accepted",
            status=ProvenanceStatus.VERIFIED_CAVEAT,
        )
        result = check_provenance(MADAM_KRYSTAL, clearance_registry=registry)
        assert result.cleared is True
        assert result.risk.status == ProvenanceStatus.VERIFIED_CAVEAT

    def test_override_is_idempotent_per_ai(self, registry):
        registry.clear(MADAM_KRYSTAL, cleared_by="first", notes="a")
        registry.clear(MADAM_KRYSTAL, cleared_by="second", notes="b")
        result = check_provenance(MADAM_KRYSTAL, clearance_registry=registry)
        assert result.risk.cleared_by == "second"

    def test_invalid_persisted_status_fails_closed(self, registry):
        # Simulates a corrupted/legacy row bypassing clear()'s enum-typed
        # `status` param — check_provenance() must not raise ValueError.
        registry._conn.execute(
            "INSERT INTO provenance_clearances "
            "(ai_name, status, cleared_by, notes, cleared_at) VALUES (?, ?, ?, ?, ?)",
            (MADAM_KRYSTAL, "not-a-real-status", "someone", "", 0.0),
        )
        registry._conn.commit()
        result = check_provenance(MADAM_KRYSTAL, clearance_registry=registry)
        assert result.cleared is False
        assert result.risk.status == ProvenanceStatus.NOT_ASSESSED


class TestPlatformWideRisks:
    def test_returns_at_least_the_ai_gateway_entry(self):
        risks = platform_wide_risks()
        assert any("AI Gateway" in r.entity for r in risks)

    def test_never_ties_to_a_named_ai(self):
        for r in platform_wide_risks():
            assert r.ai_name is None


class TestPersistenceAcrossReconnect:
    def test_clearance_survives_reopen(self, tmp_path):
        db_path = tmp_path / "reopen.db"
        reg1 = ProvenanceClearanceRegistry(db_path=db_path)
        reg1.clear(MADAM_KRYSTAL, cleared_by="ops", notes="done")
        reg1.close()
        reg2 = ProvenanceClearanceRegistry(db_path=db_path)
        result = check_provenance(MADAM_KRYSTAL, clearance_registry=reg2)
        assert result.cleared is True
        reg2.close()


class TestClearanceRegistrySingleton:
    def test_get_clearance_registry_lazily_creates_and_reuses_singleton(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(compliance_module, "_registry", None)
        monkeypatch.setattr(compliance_module, "DEFAULT_DB_PATH", tmp_path / "singleton.db")
        try:
            first = get_clearance_registry()
            assert isinstance(first, ProvenanceClearanceRegistry)
            assert get_clearance_registry() is first
        finally:
            compliance_module._registry.close()
            monkeypatch.setattr(compliance_module, "_registry", None)


class TestEmitProvenanceEventNeverRaises:
    def test_clear_swallows_observatory_failure(self, registry, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("Observatory unreachable")

        monkeypatch.setattr("src.observability.observatory.observe", _boom, raising=False)
        registry.clear(MADAM_KRYSTAL, cleared_by="ops", notes="done")
        result = check_provenance(MADAM_KRYSTAL, clearance_registry=registry)
        assert result.cleared is True
