"""Inventory GitHub security alerts without changing their state.

The inventory is deliberately conservative: unavailable alert surfaces are
reported as unavailable, deterministic findings are never suppressed, and the
optional issue update is limited to one deduplicated status issue.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

API_ROOT = "https://api.github.com"
ISSUE_MARKER = "<!-- tranc3-security-backlog:v1 -->"
SURFACES = {
    "dependabot": "/dependabot/alerts?state=open&per_page=100",
    "code_scanning": "/code-scanning/alerts?state=open&per_page=100",
    "secret_scanning": "/secret-scanning/alerts?state=open&per_page=100",
}
SEVERITY_WEIGHTS = {"critical": 100, "high": 70, "medium": 40, "moderate": 40, "low": 15}


@dataclass(frozen=True)
class SurfaceResult:
    name: str
    status: str
    alerts: list[dict[str, Any]]
    error: str | None = None


def _get_path(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _severity(alert: dict[str, Any], surface: str) -> str:
    values = [
        alert.get("severity"),
        _get_path(alert, "security_vulnerability", "severity"),
        _get_path(alert, "security_advisory", "severity"),
        _get_path(alert, "rule", "security_severity_level"),
    ]
    for value in values:
        if isinstance(value, str) and value.lower() in SEVERITY_WEIGHTS:
            return value.lower()
    return "unknown" if surface != "secret_scanning" else "high"


def _identity(surface: str, alert: dict[str, Any]) -> str:
    number = alert.get("number")
    if number is not None:
        return f"{surface}:{number}"
    advisory = _get_path(alert, "security_advisory", "ghsa_id") or _get_path(
        alert, "security_advisory", "cve_id"
    )
    package = _get_path(alert, "dependency", "package", "name")
    manifest = _get_path(alert, "dependency", "manifest_path")
    rule = _get_path(alert, "rule", "id")
    location = _get_path(alert, "most_recent_instance", "location", "path")
    if surface == "dependabot" and (advisory or package or manifest):
        return f"{surface}:{advisory or 'unknown'}:{package or 'unknown'}:{manifest or 'unknown'}"
    if surface == "code_scanning" and (rule or location):
        return f"{surface}:{rule or 'unknown'}:{location or 'unknown'}"
    return f"{surface}:{alert.get('secret_type') or alert.get('secret_type_display_name') or 'unknown'}:{alert.get('created_at') or 'unknown'}"


def classify(surface: str, alert: dict[str, Any]) -> dict[str, Any]:
    severity = _severity(alert, surface)
    score = SEVERITY_WEIGHTS.get(severity, 10)
    if alert.get("is_exploited") or alert.get("exploitability") == "high":
        score += 25
    if surface == "secret_scanning":
        score += 20
    if surface == "dependabot" and _get_path(alert, "dependency", "scope") == "runtime":
        score += 10
    priority = "P0" if score >= 100 else "P1" if score >= 70 else "P2" if score >= 40 else "P3"
    return {
        "id": _identity(surface, alert),
        "surface": surface,
        "severity": severity,
        "score": score,
        "priority": priority,
        "summary": _summary(surface, alert),
    }


def _summary(surface: str, alert: dict[str, Any]) -> str:
    if surface == "dependabot":
        package = _get_path(alert, "dependency", "package", "name") or "dependency"
        advisory = _get_path(alert, "security_advisory", "ghsa_id") or _get_path(
            alert, "security_advisory", "cve_id"
        )
        return f"{package} ({advisory or 'advisory unavailable'})"
    if surface == "code_scanning":
        return str(
            _get_path(alert, "rule", "description")
            or _get_path(alert, "rule", "id")
            or "code finding"
        )
    return str(
        alert.get("secret_type_display_name") or alert.get("secret_type") or "secret finding"
    )


def inventory(
    repo: str,
    token: str,
    fetch: Callable[[str], list[dict[str, Any]]] | None = None,
) -> tuple[list[SurfaceResult], list[dict[str, Any]]]:
    fetch = fetch or make_fetcher(repo, token)
    results: list[SurfaceResult] = []
    findings: list[dict[str, Any]] = []
    for surface, path in SURFACES.items():
        try:
            alerts = fetch(path)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            results.append(SurfaceResult(surface, "unavailable", [], str(exc)))
            continue
        results.append(SurfaceResult(surface, "available", alerts))
        findings.extend(classify(surface, alert) for alert in alerts)
    return results, sorted(findings, key=lambda finding: (-finding["score"], finding["id"]))


def make_fetcher(repo: str, token: str) -> Callable[[str], list[dict[str, Any]]]:
    def fetch(path: str) -> list[dict[str, Any]]:
        request = urllib.request.Request(
            f"{API_ROOT}/repos/{repo}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "tranc3-security-backlog",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.load(response)
        if not isinstance(payload, list):
            raise ValueError("GitHub alert endpoint returned a non-list response")
        return payload

    return fetch


def build_report(
    repo: str, results: list[SurfaceResult], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": repo,
        "surfaces": {
            result.name: {
                "status": result.status,
                "count": len(result.alerts),
                "error": result.error,
            }
            for result in results
        },
        "total_findings": len(findings),
        "priority_counts": dict(Counter(finding["priority"] for finding in findings)),
        "findings": findings,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        ISSUE_MARKER,
        f"# Tranc3 security backlog ({report['generated_at']})",
        "",
        "This is an inventory only. It does not dismiss, close, merge, or suppress alerts.",
        "",
        f"**Open findings observed:** {report['total_findings']}",
        f"**Priority counts:** {report['priority_counts'] or 'none'}",
        "",
        "| Surface | Status | Count | Error |",
        "|---|---:|---:|---|",
    ]
    for name, surface in report["surfaces"].items():
        lines.append(
            f"| {name} | {surface['status']} | {surface['count']} | {surface['error'] or ''} |"
        )
    lines.extend(["", "## Highest-priority findings", ""])
    for finding in report["findings"][:25]:
        lines.append(
            f"- **{finding['priority']} / {finding['severity']}** `{finding['id']}` — {finding['summary']}"
        )
    lines.extend(["", "Generated by `.github/workflows/supply-chain-watch.yml`."])
    return "\n".join(lines) + "\n"


def write_issue(repo: str, token: str, body: str) -> None:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "tranc3-security-backlog",
    }
    search = urllib.request.Request(
        f"{API_ROOT}/repos/{repo}/issues?state=open&per_page=100",
        headers=headers,
    )
    with urllib.request.urlopen(search, timeout=30) as response:  # noqa: S310
        issues = json.load(response)
    existing = next((issue for issue in issues if ISSUE_MARKER in (issue.get("body") or "")), None)
    payload = json.dumps({"body": body}).encode()
    if existing:
        request = urllib.request.Request(
            existing["url"], data=payload, headers=headers, method="PATCH"
        )
    else:
        request = urllib.request.Request(
            f"{API_ROOT}/repos/{repo}/issues",
            data=json.dumps({"title": "Security backlog inventory", "body": body}).encode(),
            headers=headers,
            method="POST",
        )
    with urllib.request.urlopen(request, timeout=30):  # noqa: S310
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--output-dir", type=Path, default=Path("logs"))
    parser.add_argument("--write-issue", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not args.repo or not token:
        print("GITHUB_REPOSITORY and GITHUB_TOKEN are required", file=sys.stderr)
        return 2
    results, findings = inventory(args.repo, token)
    report = build_report(args.repo, results, findings)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "security_backlog.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    body = markdown_report(report)
    (args.output_dir / "security_backlog.md").write_text(body, encoding="utf-8")
    unavailable = [result for result in results if result.status == "unavailable"]
    if args.write_issue:
        write_issue(args.repo, token, body)
    if unavailable:
        print("One or more GitHub security alert surfaces were unavailable:", file=sys.stderr)
        for result in unavailable:
            print(f"- {result.name}: {result.error}", file=sys.stderr)
        return 1
    print(f"Security backlog inventory: {len(findings)} open findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
