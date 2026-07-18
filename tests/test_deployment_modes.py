# tests/test_deployment_modes.py
# Tests for src/deployment_modes/registry.py — the Deployment Mode Registry
# (Location -> Cloud Only/Hybrid/Local mode + Dev/UAT on-demand provisioning).

from __future__ import annotations

import pytest

from src.deployment_modes.registry import (
    DeploymentMode,
    DeploymentModeRegistry,
    Environment,
    ProdNotOnDemandError,
    UnknownLocationError,
)
from src.entities.platform import PLATFORM_ENTITIES


@pytest.fixture
def registry(tmp_path):
    db_path = tmp_path / "deployment_mode_registry_test.db"
    reg = DeploymentModeRegistry(db_path=db_path)
    yield reg
    reg.close()


class TestSeeding:
    def test_seeds_one_mode_row_per_entity(self, registry):
        modes = registry.list_modes()
        assert len(modes) == len(PLATFORM_ENTITIES)

    def test_default_mode_is_cloud_only(self, registry):
        for state in registry.list_modes():
            assert state.mode == DeploymentMode.CLOUD_ONLY

    def test_seed_is_idempotent_across_reconnect(self, tmp_path):
        db_path = tmp_path / "reopen.db"
        reg1 = DeploymentModeRegistry(db_path=db_path)
        reg1.close()
        reg2 = DeploymentModeRegistry(db_path=db_path)
        assert len(reg2.list_modes()) == len(PLATFORM_ENTITIES)
        reg2.close()

    def test_seeds_three_environments_per_entity(self, registry):
        envs = registry.list_environments("The Nexus")
        assert {e.environment for e in envs} == {
            Environment.DEV,
            Environment.UAT,
            Environment.PROD,
        }

    def test_prod_seeded_provisioned(self, registry):
        prod = registry.get_environment("The Nexus", Environment.PROD)
        assert prod is not None
        assert prod.provisioned is True

    def test_dev_and_uat_seeded_unprovisioned(self, registry):
        dev = registry.get_environment("The Nexus", Environment.DEV)
        uat = registry.get_environment("The Nexus", Environment.UAT)
        assert dev.provisioned is False
        assert uat.provisioned is False


class TestGetMode:
    def test_get_known_location(self, registry):
        state = registry.get_mode("The Nexus")
        assert state is not None
        assert state.location == "The Nexus"
        assert state.mode == DeploymentMode.CLOUD_ONLY

    def test_get_unknown_location_returns_none(self, registry):
        assert registry.get_mode("Nonexistent Place") is None


class TestSetMode:
    def test_set_mode_updates_current(self, registry):
        updated = registry.set_mode(
            "The Nexus", DeploymentMode.HYBRID, changed_by="admin:alice", reason="pilot"
        )
        assert updated.mode == DeploymentMode.HYBRID
        assert updated.changed_by == "admin:alice"

    def test_unknown_location_raises(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.set_mode("Nonexistent Place", DeploymentMode.HYBRID)

    def test_set_mode_records_history(self, registry):
        registry.set_mode("The Nexus", DeploymentMode.HYBRID, changed_by="admin:bob", reason="test")
        history = registry.get_mode_history("The Nexus")
        assert len(history) == 1
        assert history[0].previous_mode == DeploymentMode.CLOUD_ONLY
        assert history[0].new_mode == DeploymentMode.HYBRID
        assert history[0].changed_by == "admin:bob"

    def test_multiple_mode_changes_all_recorded(self, registry):
        registry.set_mode("The Nexus", DeploymentMode.HYBRID)
        registry.set_mode("The Nexus", DeploymentMode.LOCAL)
        registry.set_mode("The Nexus", DeploymentMode.CLOUD_ONLY)
        history = registry.get_mode_history("The Nexus")
        assert len(history) == 3
        # Most recent first.
        assert [h.new_mode for h in history] == [
            DeploymentMode.CLOUD_ONLY,
            DeploymentMode.LOCAL,
            DeploymentMode.HYBRID,
        ]

    def test_mode_history_unknown_location_raises(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.get_mode_history("Nonexistent Place")

    def test_no_history_before_any_change(self, registry):
        assert registry.get_mode_history("Luminous") == []


class TestProvisionEnvironment:
    def test_provision_dev_requires_scoped_by(self, registry):
        with pytest.raises(ValueError):
            registry.provision_environment("The Nexus", Environment.DEV, scoped_by="")

    def test_provision_dev_sets_provisioned(self, registry):
        state = registry.provision_environment(
            "The Nexus",
            Environment.DEV,
            scoped_by="think-tank:rfc-042",
            changed_by="admin:carol",
            reason="new integration spike",
        )
        assert state.provisioned is True
        assert state.scoped_by == "think-tank:rfc-042"
        assert state.provisioned_at is not None

    def test_provision_uat_independent_of_dev(self, registry):
        registry.provision_environment("The Nexus", Environment.DEV, scoped_by="rfc-1")
        uat = registry.get_environment("The Nexus", Environment.UAT)
        assert uat.provisioned is False

    def test_cannot_provision_prod(self, registry):
        with pytest.raises(ProdNotOnDemandError):
            registry.provision_environment("The Nexus", Environment.PROD, scoped_by="rfc-1")

    def test_unknown_location_raises(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.provision_environment("Nonexistent Place", Environment.DEV, scoped_by="rfc-1")

    def test_provision_records_history(self, registry):
        registry.provision_environment(
            "The HIVE", Environment.DEV, scoped_by="rfc-1", changed_by="admin:dave"
        )
        history = registry.get_environment_history("The HIVE", Environment.DEV)
        assert len(history) == 1
        assert history[0].action == "provisioned"
        assert history[0].scoped_by == "rfc-1"


class TestDeprovisionEnvironment:
    def test_deprovision_clears_provisioned(self, registry):
        registry.provision_environment("The HIVE", Environment.DEV, scoped_by="rfc-1")
        state = registry.deprovision_environment(
            "The HIVE", Environment.DEV, changed_by="admin:erin", reason="work complete"
        )
        assert state.provisioned is False
        assert state.provisioned_at is None
        assert state.scoped_by == ""

    def test_cannot_deprovision_prod(self, registry):
        with pytest.raises(ProdNotOnDemandError):
            registry.deprovision_environment("The Nexus", Environment.PROD)

    def test_unknown_location_raises(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.deprovision_environment("Nonexistent Place", Environment.DEV)

    def test_deprovision_records_history(self, registry):
        registry.provision_environment("The HIVE", Environment.UAT, scoped_by="rfc-2")
        registry.deprovision_environment("The HIVE", Environment.UAT, reason="done")
        history = registry.get_environment_history("The HIVE", Environment.UAT)
        assert len(history) == 2
        assert history[0].action == "deprovisioned"
        assert history[1].action == "provisioned"

    def test_can_reprovision_after_deprovision(self, registry):
        registry.provision_environment("The HIVE", Environment.DEV, scoped_by="rfc-1")
        registry.deprovision_environment("The HIVE", Environment.DEV)
        state = registry.provision_environment("The HIVE", Environment.DEV, scoped_by="rfc-2")
        assert state.provisioned is True
        assert state.scoped_by == "rfc-2"


class TestEnvironmentHistory:
    def test_all_environments_history_when_none_specified(self, registry):
        registry.provision_environment("Luminous", Environment.DEV, scoped_by="rfc-1")
        registry.provision_environment("Luminous", Environment.UAT, scoped_by="rfc-2")
        history = registry.get_environment_history("Luminous")
        assert len(history) == 2
        assert {h.environment for h in history} == {Environment.DEV, Environment.UAT}

    def test_unknown_location_raises(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.get_environment_history("Nonexistent Place")


class TestEnvironmentsAreModeScoped:
    """Regression coverage: Dev/UAT provisioning must not leak across a mode
    switch — switching from Cloud Only to Hybrid/Local must present fresh,
    unprovisioned Dev/UAT for the new mode, not the old mode's state."""

    def test_provisioning_under_cloud_only_does_not_carry_to_hybrid(self, registry):
        registry.provision_environment("The Nexus", Environment.DEV, scoped_by="rfc-1")
        registry.set_mode("The Nexus", DeploymentMode.HYBRID)
        dev = registry.get_environment("The Nexus", Environment.DEV)
        assert dev.provisioned is False
        assert dev.mode == DeploymentMode.HYBRID

    def test_switching_back_restores_original_mode_state(self, registry):
        registry.provision_environment("The Nexus", Environment.DEV, scoped_by="rfc-1")
        registry.set_mode("The Nexus", DeploymentMode.HYBRID)
        registry.set_mode("The Nexus", DeploymentMode.CLOUD_ONLY)
        dev = registry.get_environment("The Nexus", Environment.DEV)
        assert dev.provisioned is True
        assert dev.scoped_by == "rfc-1"

    def test_list_environments_reflects_current_mode(self, registry):
        registry.provision_environment("The HIVE", Environment.UAT, scoped_by="rfc-9")
        registry.set_mode("The HIVE", DeploymentMode.LOCAL)
        envs = registry.list_environments("The HIVE")
        uat = next(e for e in envs if e.environment == Environment.UAT)
        assert uat.provisioned is False
        assert uat.mode == DeploymentMode.LOCAL

    def test_prod_always_provisioned_regardless_of_mode(self, registry):
        registry.set_mode("Luminous", DeploymentMode.HYBRID)
        prod = registry.get_environment("Luminous", Environment.PROD)
        assert prod.provisioned is True
        registry.set_mode("Luminous", DeploymentMode.LOCAL)
        prod = registry.get_environment("Luminous", Environment.PROD)
        assert prod.provisioned is True

    def test_environment_history_records_mode_per_entry(self, registry):
        registry.provision_environment("The HIVE", Environment.DEV, scoped_by="rfc-1")
        registry.set_mode("The HIVE", DeploymentMode.HYBRID)
        registry.provision_environment("The HIVE", Environment.DEV, scoped_by="rfc-2")
        history = registry.get_environment_history("The HIVE", Environment.DEV)
        assert len(history) == 2
        assert history[0].mode == DeploymentMode.HYBRID
        assert history[1].mode == DeploymentMode.CLOUD_ONLY


class TestScopedByValidation:
    def test_whitespace_only_scoped_by_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.provision_environment("The Nexus", Environment.DEV, scoped_by="   ")

    def test_scoped_by_is_stripped(self, registry):
        state = registry.provision_environment("The Nexus", Environment.DEV, scoped_by="  rfc-1  ")
        assert state.scoped_by == "rfc-1"


class TestDeprovisionPreservesScopeInHistory:
    def test_deprovision_history_entry_keeps_scoped_by(self, registry):
        registry.provision_environment("The HIVE", Environment.DEV, scoped_by="think-tank:rfc-77")
        registry.deprovision_environment("The HIVE", Environment.DEV, reason="done")
        history = registry.get_environment_history("The HIVE", Environment.DEV)
        deprovisioned_entry = next(h for h in history if h.action == "deprovisioned")
        assert deprovisioned_entry.scoped_by == "think-tank:rfc-77"

    def test_live_state_scoped_by_still_cleared_after_deprovision(self, registry):
        registry.provision_environment("The HIVE", Environment.DEV, scoped_by="rfc-1")
        state = registry.deprovision_environment("The HIVE", Environment.DEV)
        assert state.scoped_by == ""
