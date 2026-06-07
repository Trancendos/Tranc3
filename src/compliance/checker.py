"""
DEFSTAN Compliance Checker — Tranc3 / Trancendos Platform

Loads compliance/register.yaml, verifies evidence paths exist, computes
compliance scores per standard area, and outputs a structured report.

Usage:
    python -m src.compliance.checker           # print summary
    python -m src.compliance.checker --report  # generate full report
    python -m src.compliance.checker --ci      # exit 1 if score < 70%
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Paths relative to repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTER_PATH = REPO_ROOT / "compliance" / "register.yaml"
WAIVERS_PATH = REPO_ROOT / "compliance" / "waivers.yaml"

# Status ordering for summary display
STATUS_ORDER = ["COMPLIANT", "PARTIAL", "PLANNED", "WAIVED", "NA"]

# Minimum score (%) to pass CI gate
CI_PASS_THRESHOLD = 70


@dataclass
class EvidenceCheck:
    evidence_type: str
    path: str
    description: str
    exists: bool
    full_path: str


@dataclass
class RequirementResult:
    req_id: str
    standard: str
    title: str
    status: str
    evidence_checks: list[EvidenceCheck] = field(default_factory=list)
    all_evidence_present: bool = True
    notes: str = ""

    @property
    def area(self) -> str:
        """Extract area code from requirement ID (e.g. REQ-IA-001 -> IA)"""
        parts = self.req_id.split("-")
        return parts[1] if len(parts) >= 3 else "UNKNOWN"


@dataclass
class AreaSummary:
    area: str
    standard: str
    total: int = 0
    compliant: int = 0
    partial: int = 0
    planned: int = 0
    waived: int = 0
    na: int = 0

    @property
    def score_pct(self) -> float:
        """Score = (COMPLIANT + 0.5 * PARTIAL) / (total - NA - WAIVED) * 100"""
        denominator = self.total - self.na - self.waived
        if denominator <= 0:
            return 100.0
        return round((self.compliant + 0.5 * self.partial) / denominator * 100, 1)


@dataclass
class ComplianceReport:
    generated_at: str
    platform: str
    classification: str
    register_version: str
    requirements: list[RequirementResult] = field(default_factory=list)
    areas: dict[str, AreaSummary] = field(default_factory=dict)
    waivers: list[dict[str, Any]] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        """Weighted overall compliance score across all areas."""
        total = sum(a.total for a in self.areas.values())
        na = sum(a.na for a in self.areas.values())
        waived = sum(a.waived for a in self.areas.values())
        compliant = sum(a.compliant for a in self.areas.values())
        partial = sum(a.partial for a in self.areas.values())
        denominator = total - na - waived
        if denominator <= 0:
            return 100.0
        return round((compliant + 0.5 * partial) / denominator * 100, 1)

    @property
    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = dict.fromkeys(STATUS_ORDER, 0)
        for req in self.requirements:
            s = req.status.upper()
            if s in counts:
                counts[s] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "platform": self.platform,
            "classification": self.classification,
            "register_version": self.register_version,
            "overall_score": self.overall_score,
            "status_counts": self.status_counts,
            "areas": {
                k: {
                    "area": v.area,
                    "standard": v.standard,
                    "total": v.total,
                    "compliant": v.compliant,
                    "partial": v.partial,
                    "planned": v.planned,
                    "waived": v.waived,
                    "na": v.na,
                    "score_pct": v.score_pct,
                }
                for k, v in self.areas.items()
            },
            "requirements": [
                {
                    "id": r.req_id,
                    "standard": r.standard,
                    "title": r.title,
                    "status": r.status,
                    "area": r.area,
                    "all_evidence_present": r.all_evidence_present,
                    "notes": r.notes,
                    "evidence": [
                        {
                            "type": e.evidence_type,
                            "path": e.path,
                            "description": e.description,
                            "exists": e.exists,
                        }
                        for e in r.evidence_checks
                    ],
                }
                for r in self.requirements
            ],
            "waivers": self.waivers,
        }


# Area code -> standard name mapping
AREA_STANDARDS = {
    "IA": "DEF STAN 00-700",
    "SA": "DEF STAN 00-055",
    "QA": "DEF STAN 05-086",
    "CM": "DEF STAN 00-044",
    "SU": "DEF STAN 00-600",
    "SD": "DEF STAN 00-056",
    "TD": "DEF STAN 05-057",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning empty dict on failure."""
    if yaml is None:
        raise ImportError("PyYAML is required: pip install pyyaml")
    if not path.exists():
        raise FileNotFoundError(f"Compliance file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _check_evidence(evidence_list: list[dict[str, Any]]) -> list[EvidenceCheck]:
    """Check whether each evidence path exists on disk."""
    results = []
    for ev in evidence_list:
        # Support both dict-style and legacy string-style evidence entries
        if isinstance(ev, str):
            # "path/to/file — description" or just "path/to/file"
            parts = ev.split(" — ", 1)
            ev_path = parts[0].strip()
            # Strip parenthetical suffixes like "(port 8046)"
            ev_path = ev_path.split(" (")[0].strip()
            ev = {
                "type": "code",
                "path": ev_path,
                "description": parts[1].strip() if len(parts) > 1 else "",
            }
        ev_path = ev.get("path", "")
        full_path = REPO_ROOT / ev_path
        # For directories, check the directory exists; for files, check the file
        exists = full_path.exists()
        results.append(
            EvidenceCheck(
                evidence_type=ev.get("type", "unknown"),
                path=ev_path,
                description=ev.get("description", ""),
                exists=exists,
                full_path=str(full_path),
            )
        )
    return results


def load_and_check(register_path: Path = REGISTER_PATH) -> ComplianceReport:
    """
    Load the compliance register, verify evidence, and build the report.
    """
    data = _load_yaml(register_path)
    meta = data.get("meta", {})

    # Load waivers
    waivers: list[dict[str, Any]] = []
    if WAIVERS_PATH.exists():
        waiver_data = _load_yaml(WAIVERS_PATH)
        waivers = waiver_data.get("waivers", [])
    waived_req_ids = {w["requirement_id"] for w in waivers if w.get("status") == "ACTIVE"}

    report = ComplianceReport(
        generated_at=datetime.utcnow().isoformat() + "Z",
        platform=meta.get("platform", "Tranc3"),
        classification=meta.get("classification", "UNCLASSIFIED"),
        register_version=meta.get("register_version", "unknown"),
        waivers=waivers,
    )

    requirements = data.get("requirements", [])

    # Initialise area summaries
    for area_code, standard in AREA_STANDARDS.items():
        report.areas[area_code] = AreaSummary(area=area_code, standard=standard)

    for req_raw in requirements:
        req_id = req_raw.get("id", "UNKNOWN")
        area = req_id.split("-")[1] if "-" in req_id else "UNKNOWN"
        evidence_list = req_raw.get("evidence") or []

        # Check if this item has an active waiver
        effective_status = req_raw.get("status", "PLANNED").upper()
        if req_id in waived_req_ids:
            effective_status = "WAIVED"

        checks = _check_evidence(evidence_list)
        all_present = all(c.exists for c in checks) if checks else True

        result = RequirementResult(
            req_id=req_id,
            standard=req_raw.get("standard", ""),
            title=req_raw.get("title", ""),
            status=effective_status,
            evidence_checks=checks,
            all_evidence_present=all_present,
            notes=req_raw.get("notes", ""),
        )
        report.requirements.append(result)

        # Accumulate area stats
        area_summary = report.areas.get(area)
        if area_summary is None:
            area_summary = AreaSummary(
                area=area,
                standard=AREA_STANDARDS.get(area, "Unknown Standard"),
            )
            report.areas[area] = area_summary

        area_summary.total += 1
        status_upper = effective_status
        if status_upper == "COMPLIANT":
            area_summary.compliant += 1
        elif status_upper == "PARTIAL":
            area_summary.partial += 1
        elif status_upper == "PLANNED":
            area_summary.planned += 1
        elif status_upper == "WAIVED":
            area_summary.waived += 1
        elif status_upper in ("NA", "N/A"):
            area_summary.na += 1

    return report


def print_summary(report: ComplianceReport) -> None:
    """Print a human-readable compliance summary to stdout."""
    sep = "=" * 70
    print(sep)
    print(f"  DEFSTAN COMPLIANCE REPORT — {report.platform}")
    print(f"  Generated: {report.generated_at}")
    print(f"  Classification: {report.classification}")
    print(sep)
    print(f"\n  Overall Compliance Score: {report.overall_score:.1f}%")
    print()

    # Status breakdown
    counts = report.status_counts
    print("  Status Breakdown:")
    for status in STATUS_ORDER:
        n = counts.get(status, 0)
        bar = "#" * n
        print(f"    {status:<10} {n:>3}  {bar}")
    print()

    # Per-area table
    print(
        f"  {'Area':<6} {'Standard':<22} {'Reqs':>4} {'Pass':>4} {'Part':>4} {'Plan':>4} {'Score':>6}"
    )
    print(f"  {'-' * 6} {'-' * 22} {'-' * 4} {'-' * 4} {'-' * 4} {'-' * 4} {'-' * 6}")
    for area_code in sorted(report.areas.keys()):
        a = report.areas[area_code]
        std_short = a.standard.replace("DEF STAN ", "DS ")
        print(
            f"  {a.area:<6} {std_short:<22} {a.total:>4} {a.compliant:>4} "
            f"{a.partial:>4} {a.planned:>4} {a.score_pct:>5.1f}%"
        )
    print()

    # Evidence warnings
    missing_evidence = [
        r
        for r in report.requirements
        if not r.all_evidence_present and r.status in ("COMPLIANT", "PARTIAL")
    ]
    if missing_evidence:
        print(f"  WARNING: {len(missing_evidence)} requirement(s) have missing evidence paths:")
        for r in missing_evidence:
            missing = [e.path for e in r.evidence_checks if not e.exists]
            print(f"    {r.req_id}: {', '.join(missing)}")
        print()

    ci_pass = report.overall_score >= CI_PASS_THRESHOLD
    print(f"  CI Gate ({'PASS' if ci_pass else 'FAIL'} — threshold {CI_PASS_THRESHOLD}%)")
    print(sep)


def run(args: argparse.Namespace | None = None) -> int:
    """Main entry point. Returns exit code."""
    parser = argparse.ArgumentParser(
        description="DEFSTAN Compliance Checker for Tranc3 / Trancendos"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate full JSON report to stdout",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: exit 1 if overall score < 70%%",
    )
    parser.add_argument(
        "--register",
        default=str(REGISTER_PATH),
        help="Path to compliance register YAML",
    )
    parsed = parser.parse_args(args)

    logging.basicConfig(level=logging.WARNING)

    try:
        report = load_and_check(Path(parsed.register))
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERROR loading compliance register: {e}", file=sys.stderr)
        return 2

    if parsed.report:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_summary(report)

    if parsed.ci:
        if report.overall_score < CI_PASS_THRESHOLD:
            print(
                f"\nCI GATE FAILED: compliance score {report.overall_score:.1f}% "
                f"< {CI_PASS_THRESHOLD}% threshold",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(run())
