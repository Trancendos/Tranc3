import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.security_backlog import build_report, classify, inventory, markdown_report


def test_classifies_runtime_dependabot_alert_as_high_priority():
    finding = classify(
        "dependabot",
        {
            "number": 7,
            "dependency": {"package": {"name": "example"}, "scope": "runtime"},
            "security_advisory": {"ghsa_id": "GHSA-test", "severity": "high"},
        },
    )

    assert finding["priority"] == "P1"
    assert finding["id"] == "dependabot:7"


def test_inventory_reports_unavailable_surface_without_calling_it_healthy():
    def fetch(path):
        if "code-scanning" in path:
            raise TimeoutError("timeout")
        return []

    results, findings = inventory("owner/repo", "token", fetch)

    assert len(findings) == 0
    assert {result.name: result.status for result in results}["code_scanning"] == "unavailable"


def test_report_and_markdown_preserve_unavailable_surface():
    results, findings = inventory("owner/repo", "token", lambda path: [])
    report = build_report("owner/repo", results, findings)

    assert report["total_findings"] == 0
    assert "security backlog" in markdown_report(report)
    assert all(surface["status"] == "available" for surface in report["surfaces"].values())
