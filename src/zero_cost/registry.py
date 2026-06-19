"""Zero-cost provider registry — approved IDs, rotation chains, hard stops."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "zero_cost" / "providers.yaml"

# Legacy rotator / env names → canonical chain names in providers.yaml
_CHAIN_ALIASES: dict[str, str] = {
    "inference_default": "zero_cost_cloud",
    "inference_local": "zero_cost_local",
    "inference_full": "zero_cost_full",
}


def _registry_path() -> Path:
    return _REGISTRY_PATH


def _load_root() -> dict[str, Any]:
    path = _registry_path()
    if not path.is_file():
        raise FileNotFoundError(f"Zero-cost registry missing: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("providers.yaml must be a mapping")
    return data


def _iter_capability_providers(root: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    caps = root.get("capabilities") or {}
    if not isinstance(caps, dict):
        return out
    for cap in caps.values():
        if not isinstance(cap, dict):
            continue
        for prov in cap.get("providers") or []:
            if isinstance(prov, dict) and prov.get("id"):
                out.append(prov)
    return out


def _collect_rotation_chains(root: dict[str, Any]) -> dict[str, list[str]]:
    """Merge top-level and per-capability rotation_chains into name → providers."""
    chains: dict[str, list[str]] = {}

    def _add(chain_obj: Any) -> None:
        if not isinstance(chain_obj, dict):
            return
        name = chain_obj.get("name")
        providers = chain_obj.get("providers")
        if not name or not isinstance(providers, list):
            return
        pid_list = [str(p) for p in providers if p]
        if name in chains and chains[name] != pid_list:
            raise ValueError(f"Duplicate rotation chain name with different providers: {name}")
        chains[name] = pid_list

    for chain in root.get("rotation_chains") or []:
        _add(chain)

    for cap in (root.get("capabilities") or {}).values():
        if isinstance(cap, dict):
            for chain in cap.get("rotation_chains") or []:
                _add(chain)

    return chains


def load_registry() -> dict[str, Any]:
    """Load YAML registry with normalized rotation_chains_map and version."""
    root = _load_root()
    chains_map = _collect_rotation_chains(root)
    result = dict(root)
    result["version"] = root.get("version", "unknown")
    result["rotation_chains_map"] = chains_map
    # Backward compatibility for audit scripts
    result.setdefault("conditional_cloud", [])
    result.setdefault("avoid_paid_default", root.get("blocked_paid", []))
    result.setdefault("language_ecosystems", {})
    return result


def get_chain(chain_name: str) -> list[str]:
    """Return ordered provider IDs for a named rotation chain."""
    resolved = _CHAIN_ALIASES.get(chain_name, chain_name)
    reg = load_registry()
    chains = reg.get("rotation_chains_map") or {}
    if resolved not in chains:
        known = ", ".join(sorted(chains.keys()))
        raise ValueError(f"Unknown rotation chain '{chain_name}' (resolved: '{resolved}'). Known: {known}")
    return list(chains[resolved])


def is_approved(provider_id: str) -> bool:
    """True if provider is on an approved list or a zero-cost capability entry."""
    reg = load_registry()
    if provider_id in reg.get("approved_self_hosted", []):
        return True
    if provider_id in reg.get("approved_free_tier", []):
        return True
    for prov in _iter_capability_providers(reg):
        if prov.get("id") == provider_id:
            cost = str(prov.get("cost", "zero")).lower()
            if cost in ("zero", "free", "0"):
                return True
    return False


def approved_ids() -> frozenset[str]:
    reg = load_registry()
    ids: set[str] = set(reg.get("approved_self_hosted", [])) | set(reg.get("approved_free_tier", []))
    for prov in _iter_capability_providers(reg):
        pid = prov.get("id")
        if pid and is_approved(str(pid)):
            ids.add(str(pid))
    return frozenset(ids)


def validate_all_chains() -> list[str]:
    """Return provider IDs in rotation chains that are not approved (empty if valid)."""
    reg = load_registry()
    bad: list[str] = []
    for chain_name, providers in (reg.get("rotation_chains_map") or {}).items():
        for pid in providers:
            if not is_approved(pid):
                bad.append(f"{chain_name}:{pid}")
    return bad


def assert_zero_cost(provider_or_chain: str | list[str]) -> None:
    """Hard stop: refuse paid or unlisted providers (single ID or full chain)."""
    if isinstance(provider_or_chain, list):
        for pid in provider_or_chain:
            assert_zero_cost(pid)
        return

    provider_id = provider_or_chain
    reg = load_registry()
    blocked = set(reg.get("blocked_paid") or [])
    if provider_id in blocked:
        raise ValueError(f"Provider '{provider_id}' is blocked (paid tier)")
    if not is_approved(provider_id):
        raise ValueError(f"Provider '{provider_id}' is not in the zero-cost registry")
