"""
Platform infrastructure mode — CLOUD_ONLY | HYBRID | LOCAL_ONLY

Default: CLOUD_ONLY (free-tier cloud rotation until your Citadel server is ready).

Environment (first match wins):
  PLATFORM_INFRA_MODE=CLOUD_ONLY|HYBRID|LOCAL_ONLY
  SYSTEM_MODE=CLOUD_ONLY|HYBRID|TRUE_NAS   # legacy alias (TRUE_NAS → LOCAL_ONLY)
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_FILE = _ROOT / "config" / "platform" / "infrastructure_mode.yaml"


class PlatformInfraMode(str, Enum):
    CLOUD_ONLY = "CLOUD_ONLY"
    HYBRID = "HYBRID"
    LOCAL_ONLY = "LOCAL_ONLY"


_LEGACY_MAP = {
    "TRUE_NAS": PlatformInfraMode.LOCAL_ONLY,
    "LOCAL": PlatformInfraMode.LOCAL_ONLY,
    "LOCAL_ONLY": PlatformInfraMode.LOCAL_ONLY,
    "CLOUD_ONLY": PlatformInfraMode.CLOUD_ONLY,
    "CLOUD": PlatformInfraMode.CLOUD_ONLY,
    "HYBRID": PlatformInfraMode.HYBRID,
}


def _load_yaml_defaults() -> dict[str, Any]:
    if not _CONFIG_FILE.is_file():
        return {}
    try:
        return yaml.safe_load(_CONFIG_FILE.read_text()) or {}
    except Exception:
        return {}


def get_infrastructure_mode() -> PlatformInfraMode:
    raw = (
        os.environ.get("PLATFORM_INFRA_MODE")
        or os.environ.get("SYSTEM_MODE")
        or _load_yaml_defaults().get("default_mode", "CLOUD_ONLY")
    )
    key = str(raw).strip().upper()
    if key in _LEGACY_MAP:
        return _LEGACY_MAP[key]
    return PlatformInfraMode.CLOUD_ONLY


def is_cloud_only() -> bool:
    return get_infrastructure_mode() == PlatformInfraMode.CLOUD_ONLY


def is_hybrid() -> bool:
    return get_infrastructure_mode() == PlatformInfraMode.HYBRID


def is_local_only() -> bool:
    return get_infrastructure_mode() == PlatformInfraMode.LOCAL_ONLY


def default_rotation_chain() -> str:
    mode = get_infrastructure_mode()
    cfg = _load_yaml_defaults()
    chains = cfg.get("rotation_chains") or {}
    if mode == PlatformInfraMode.CLOUD_ONLY:
        return os.environ.get(
            "ADAPTIVE_ROTATION_CHAIN",
            chains.get("CLOUD_ONLY", "zero_cost_cloud"),
        )
    if mode == PlatformInfraMode.HYBRID:
        return os.environ.get(
            "ADAPTIVE_ROTATION_CHAIN",
            chains.get("HYBRID", "zero_cost_full"),
        )
    return os.environ.get(
        "ADAPTIVE_ROTATION_CHAIN",
        chains.get("LOCAL_ONLY", "zero_cost_full"),
    )


def cloud_auto_rotation_enabled() -> bool:
    """Periodic rotation across free cloud providers (no local server required)."""
    flag = os.environ.get(
        "ADAPTIVE_CLOUD_AUTO_ROTATE",
        _load_yaml_defaults().get("cloud_auto_rotate", "true"),
    )
    if flag is not None and str(flag).lower() in ("0", "false", "no"):
        return False
    mode = get_infrastructure_mode()
    return mode in (PlatformInfraMode.CLOUD_ONLY, PlatformInfraMode.HYBRID)


def should_run_citadel_docker() -> bool:
    """Citadel compose deploy — only when explicitly local or hybrid with local stack."""
    if is_local_only():
        return True
    if is_hybrid() and os.environ.get("CITADEL_LOCAL_STACK", "").lower() in ("1", "true", "yes"):
        return True
    return False


def infrastructure_status() -> dict[str, Any]:
    mode = get_infrastructure_mode()
    cfg = _load_yaml_defaults()
    return {
        "mode": mode.value,
        "description": (cfg.get("modes") or {}).get(mode.value, ""),
        "rotation_chain": default_rotation_chain(),
        "cloud_auto_rotate": cloud_auto_rotation_enabled(),
        "adaptive_rotation_enabled": os.environ.get("ADAPTIVE_ROTATION_ENABLED", "true").lower()
        in ("1", "true", "yes"),
        "citadel_docker_recommended": should_run_citadel_docker(),
        "legacy_system_mode_env": "SYSTEM_MODE still supported (TRUE_NAS → LOCAL_ONLY)",
    }
