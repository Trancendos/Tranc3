#!/usr/bin/env python3
"""Validate zero-cost registry v2: capabilities, rotation chains, and hard stops."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.zero_cost.registry import load_registry, validate_all_chains  # noqa: E402


def main() -> int:
    reg = load_registry()
    chains_map = reg.get("rotation_chains_map") or {}
    violations = validate_all_chains()

    report = {
        "version": reg.get("version"),
        "approved_self_hosted_count": len(reg.get("approved_self_hosted", [])),
        "approved_free_tier_count": len(reg.get("approved_free_tier", [])),
        "blocked_paid_count": len(reg.get("blocked_paid", [])),
        "rotation_chains": {
            name: {"provider_count": len(providers), "providers": providers}
            for name, providers in sorted(chains_map.items())
        },
        "chain_validation_errors": violations,
        "capabilities": list((reg.get("capabilities") or {}).keys()),
        "languages": list((reg.get("language_ecosystems") or {}).keys()),
        "status": "PASS" if not violations else "FAIL",
    }
    print(json.dumps(report, indent=2))

    doc = ROOT / "docs" / "ZERO_COST_VENDOR_MATRIX.md"
    if not doc.is_file():
        print("WARN: docs/ZERO_COST_VENDOR_MATRIX.md missing", file=sys.stderr)
        return 1
    if violations:
        print("FAIL: unapproved providers in rotation chains:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
