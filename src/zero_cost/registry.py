"""
Zero-cost provider registry — loads config/zero_cost/providers.yaml.

Use in CI and audits to ensure new integrations align with the Fortiere model.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = _ROOT / "config" / "zero_cost" / "providers.yaml"


@lru_cache(maxsize=1)
def load_registry(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or _DEFAULT_PATH
    if not cfg_path.is_file():
        return {"version": "unknown", "approved_self_hosted": [], "conditional_cloud": []}
    text = cfg_path.read_text()
    if yaml is None:
        raise RuntimeError("PyYAML required to load zero-cost registry")
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def approved_ids() -> set[str]:
    reg = load_registry()
    return {str(x["id"]) for x in reg.get("approved_self_hosted", []) if isinstance(x, dict) and x.get("id")}


def is_approved(provider_id: str) -> bool:
    return provider_id in approved_ids()
