#!/usr/bin/env python3
"""Validate zero-cost registry and list approved vs conditional providers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.zero_cost.registry import load_registry  # noqa: E402


def main() -> int:
    reg = load_registry()
    report = {
        "version": reg.get("version"),
        "approved_count": len(reg.get("approved_self_hosted", [])),
        "conditional_count": len(reg.get("conditional_cloud", [])),
        "avoid_count": len(reg.get("avoid_paid_default", [])),
        "languages": list((reg.get("language_ecosystems") or {}).keys()),
    }
    print(json.dumps(report, indent=2))
    doc = ROOT / "docs" / "ZERO_COST_VENDOR_MATRIX.md"
    if not doc.is_file():
        print("WARN: docs/ZERO_COST_VENDOR_MATRIX.md missing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
