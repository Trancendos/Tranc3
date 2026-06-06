"""
DEFSTAN Compliance Checker — reads compliance/register.yaml and reports
overall score. Used by `make gate-check` and the Forgejo compliance-gate CI.

Usage::

    python -m src.compliance.checker            # human-readable summary
    python -m src.compliance.checker --ci       # exit 1 if score < 70%
    python -m src.compliance.checker --report   # JSON to stdout
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REGISTER_PATH = Path(__file__).parents[2] / "compliance" / "register.yaml"
GATE_THRESHOLD = 70  # percent


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore[import]
        return yaml.safe_load(path.read_text())
    except ImportError:
        # Minimal YAML fallback — good enough for our flat register structure
        raise RuntimeError(
            "PyYAML not installed. Run: pip install pyyaml"
        )


def load_and_check() -> Dict[str, Any]:
    """Parse the register and return a structured compliance report."""
    if not REGISTER_PATH.exists():
        return {
            "error": f"Register not found at {REGISTER_PATH}",
            "overall_score": 0.0,
            "areas": {},
            "status_counts": {},
        }

    data = _load_yaml(REGISTER_PATH)
    meta = data.get("meta", {})
    threshold = meta.get("gate_threshold", GATE_THRESHOLD)

    areas: Dict[str, Dict] = {}
    all_reqs: List[Dict] = []

    skip_keys = {"meta"}
    for area_key, area_data in data.items():
        if area_key in skip_keys or not isinstance(area_data, dict):
            continue
        reqs = area_data.get("requirements", [])
        if not reqs:
            continue

        compliant = sum(1 for r in reqs if r.get("status") == "COMPLIANT")
        total = len(reqs)
        score_pct = (compliant / total * 100) if total else 0.0

        areas[area_key] = {
            "area": area_key.replace("_", " ").title(),
            "standard": area_data.get("standard", ""),
            "total": total,
            "compliant": compliant,
            "score_pct": score_pct,
            "requirements": reqs,
        }
        all_reqs.extend(reqs)

    total_all = len(all_reqs)
    compliant_all = sum(1 for r in all_reqs if r.get("status") == "COMPLIANT")
    overall = (compliant_all / total_all * 100) if total_all else 0.0

    status_counts: Dict[str, int] = {}
    for r in all_reqs:
        s = r.get("status", "UNKNOWN")
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "overall_score": overall,
        "total": total_all,
        "compliant": compliant_all,
        "gate_threshold": threshold,
        "gate": "PASS" if overall >= threshold else "FAIL",
        "areas": areas,
        "status_counts": status_counts,
    }


def print_summary(report: Dict[str, Any]) -> None:
    score = report["overall_score"]
    gate = report["gate"]
    print(f"\nDEFSTAN Compliance Gate — {gate}")
    print(f"Overall: {score:.1f}% ({report['compliant']}/{report['total']} requirements)")
    print(f"Gate threshold: {report['gate_threshold']}%\n")

    for area_key, area in report.get("areas", {}).items():
        marker = "✓" if area["score_pct"] == 100 else ("~" if area["score_pct"] >= 70 else "✗")
        print(f"  {marker} {area['area']} ({area['standard']}): "
              f"{area['score_pct']:.0f}% ({area['compliant']}/{area['total']})")
        for req in area["requirements"]:
            status = req.get("status", "UNKNOWN")
            sym = "✓" if status == "COMPLIANT" else ("~" if status == "PARTIAL" else "✗")
            print(f"      {sym} {req['id']} — {req['title']} [{status}]")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DEFSTAN compliance checker")
    parser.add_argument("--ci", action="store_true", help="Exit 1 if score < threshold")
    parser.add_argument("--report", action="store_true", help="Emit JSON report to stdout")
    args = parser.parse_args()

    report = load_and_check()

    if args.report:
        print(json.dumps(report, indent=2))
    else:
        print_summary(report)

    if args.ci and report["gate"] == "FAIL":
        sys.exit(1)
