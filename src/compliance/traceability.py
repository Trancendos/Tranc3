"""
Traceability Matrix Builder — Tranc3 / Trancendos Platform

Maps requirements -> code paths -> test file IDs.
Detects orphaned requirements (no evidence) and orphaned tests (no requirement mapping).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.compliance.checker import ComplianceReport

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_EVIDENCE_PATH = REPO_ROOT / "compliance" / "test_evidence.yaml"


def _load_test_evidence() -> list[dict[str, Any]]:
    """Load test_evidence.yaml mapping test files to requirement IDs."""
    if yaml is None or not TEST_EVIDENCE_PATH.exists():
        return []
    with open(TEST_EVIDENCE_PATH) as f:
        data = yaml.safe_load(f) or {}
    return data.get("test_evidence", [])


def build_matrix(report: "ComplianceReport") -> dict[str, Any]:
    """
    Build a full traceability matrix from the compliance report.

    Returns:
        {
          "requirements": {
            "REQ-IA-001": {
              "title": "...",
              "status": "COMPLIANT",
              "code_paths": [...],
              "test_paths": [...],
              "orphaned": false
            },
            ...
          },
          "test_files": {
            "tests/test_auth.py": ["REQ-IA-001", ...],
            ...
          },
          "orphaned_requirements": [...],   # requirements with no evidence
          "orphaned_tests": [...],          # test files with no requirement mapping
          "summary": { ... }
        }
    """
    test_evidence = _load_test_evidence()

    # Build test-file -> requirements mapping from test_evidence.yaml
    test_to_reqs: dict[str, list[str]] = {}
    for te in test_evidence:
        tf = te.get("test_file", "")
        covers = te.get("covers", [])
        test_to_reqs[tf] = covers

    # Build requirement -> details
    req_map: dict[str, dict[str, Any]] = {}
    for r in report.requirements:
        code_paths = [
            e.path for e in r.evidence_checks if e.evidence_type == "code"
        ]
        test_paths = [
            e.path for e in r.evidence_checks if e.evidence_type == "test"
        ]
        req_map[r.req_id] = {
            "title": r.title,
            "standard": r.standard,
            "status": r.status,
            "code_paths": code_paths,
            "test_paths": test_paths,
            "orphaned": not r.evidence_checks,
        }

    # Collect all test files referenced in requirements
    all_req_test_files: set[str] = set()
    for r in report.requirements:
        for e in r.evidence_checks:
            if e.evidence_type == "test":
                all_req_test_files.add(e.path)

    # Orphaned requirements: COMPLIANT/PARTIAL with no evidence at all
    orphaned_reqs = [
        r.req_id
        for r in report.requirements
        if not r.evidence_checks and r.status in ("COMPLIANT", "PARTIAL")
    ]

    # Orphaned tests: test files in test_evidence.yaml that map to no requirements
    # All requirement IDs that exist
    all_req_ids = {r.req_id for r in report.requirements}
    orphaned_tests = [
        tf
        for tf, reqs in test_to_reqs.items()
        if not any(r in all_req_ids for r in reqs)
    ]

    summary = {
        "total_requirements": len(report.requirements),
        "requirements_with_code_evidence": sum(
            1 for r in req_map.values() if r["code_paths"]
        ),
        "requirements_with_test_evidence": sum(
            1 for r in req_map.values() if r["test_paths"]
        ),
        "orphaned_requirement_count": len(orphaned_reqs),
        "orphaned_test_count": len(orphaned_tests),
        "test_files_mapped": len(test_to_reqs),
    }

    return {
        "requirements": req_map,
        "test_files": test_to_reqs,
        "orphaned_requirements": orphaned_reqs,
        "orphaned_tests": orphaned_tests,
        "summary": summary,
    }
