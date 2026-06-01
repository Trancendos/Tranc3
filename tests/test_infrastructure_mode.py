"""Platform infrastructure mode — CLOUD_ONLY default and rotation chains."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_mode_env(monkeypatch):
    for key in ("PLATFORM_INFRA_MODE", "SYSTEM_MODE", "ADAPTIVE_ROTATION_CHAIN"):
        monkeypatch.delenv(key, raising=False)


def test_default_is_cloud_only(monkeypatch):
    from src.platform.infrastructure_mode import (
        PlatformInfraMode,
        cloud_auto_rotation_enabled,
        default_rotation_chain,
        get_infrastructure_mode,
    )

    assert get_infrastructure_mode() == PlatformInfraMode.CLOUD_ONLY
    assert default_rotation_chain() == "zero_cost_cloud"
    assert cloud_auto_rotation_enabled() is True


def test_local_only_chain(monkeypatch):
    monkeypatch.setenv("PLATFORM_INFRA_MODE", "LOCAL_ONLY")
    from src.platform.infrastructure_mode import (
        PlatformInfraMode,
        default_rotation_chain,
        get_infrastructure_mode,
        should_run_citadel_docker,
    )

    assert get_infrastructure_mode() == PlatformInfraMode.LOCAL_ONLY
    assert default_rotation_chain() == "zero_cost_full"
    assert should_run_citadel_docker() is True


def test_legacy_true_nas_maps_local(monkeypatch):
    monkeypatch.setenv("SYSTEM_MODE", "TRUE_NAS")
    from src.platform.infrastructure_mode import PlatformInfraMode, get_infrastructure_mode

    assert get_infrastructure_mode() == PlatformInfraMode.LOCAL_ONLY


def test_hybrid_citadel_flag(monkeypatch):
    monkeypatch.setenv("PLATFORM_INFRA_MODE", "HYBRID")
    from src.platform.infrastructure_mode import should_run_citadel_docker

    assert should_run_citadel_docker() is False
    monkeypatch.setenv("CITADEL_LOCAL_STACK", "true")
    assert should_run_citadel_docker() is True


def test_cloud_auto_rotate_disabled(monkeypatch):
    monkeypatch.setenv("ADAPTIVE_CLOUD_AUTO_ROTATE", "false")
    from src.platform.infrastructure_mode import cloud_auto_rotation_enabled

    assert cloud_auto_rotation_enabled() is False


def test_infrastructure_status_shape():
    from src.platform.infrastructure_mode import infrastructure_status

    st = infrastructure_status()
    assert st["mode"] == "CLOUD_ONLY"
    assert "rotation_chain" in st
    assert st["cloud_auto_rotate"] is True
    assert st["citadel_docker_recommended"] is False
