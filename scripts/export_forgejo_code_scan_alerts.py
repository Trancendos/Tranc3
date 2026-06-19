#!/usr/bin/env python3
"""Export Forgejo/Gitea code-scanning alerts into SECURITY_ALERT_REGISTER.md.

Requires:
  FORGEJO_URL   — e.g. https://trancendos.com/the-workshop (no trailing slash)
  FORGEJO_TOKEN — API token with repo read access
  FORGEJO_REPO  — optional, default Trancendos/Tranc3

Usage:
  python scripts/export_forgejo_code_scan_alerts.py
  python scripts/export_forgejo_code_scan_alerts.py --merge  # append to register
  python scripts/export_forgejo_code_scan_alerts.py --json-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "SECURITY_ALERT_REGISTER.md"
LOGS = ROOT / "logs"


def _api_base(url: str) -> str:
    base = url.rstrip("/")
    if base.endswith("/api/v1"):
        return base
    return f"{base}/api/v1"


def _fetch_json(url: str, token: str) -> object:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/json",
            "User-Agent": "tranc3-export-forgejo-alerts",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _list_alerts(api_base: str, owner: str, repo: str, token: str) -> list[dict]:
    alerts: list[dict] = []
    page = 1
    limit = 50
    while True:
        qs = urllib.parse.urlencode({"state": "all", "page": page, "limit": limit})
        url = f"{api_base}/repos/{owner}/{repo}/code-scanning/alerts?{qs}"
        try:
            payload = _fetch_json(url, token)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and page == 1:
                # Older Forgejo without code-scanning API
                print(
                    f"Code-scanning API not available at {url} (HTTP 404).",
                    file=sys.stderr,
                )
                return alerts
            raise
        batch = payload if isinstance(payload, list) else payload.get("data", [])
        if not batch:
            break
        for item in batch:
            if isinstance(item, dict):
                alerts.append(item)
        if len(batch) < limit:
            break
        page += 1
    return alerts


def _severity_rank(alert: dict) -> int:
    rule = alert.get("rule") or {}
    sev = (rule.get("severity") or alert.get("severity") or "").lower()
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "note": 4}.get(sev, 5)


def _alert_row(alert: dict) -> dict:
    rule = alert.get("rule") or {}
    loc = alert.get("most_recent_instance") or alert.get("location") or {}
    return {
        "number": alert.get("number") or alert.get("id"),
        "state": alert.get("state", "open"),
        "severity": rule.get("severity") or alert.get("severity") or "",
        "rule_id": rule.get("id") or rule.get("name") or "",
        "tool": rule.get("tool") or alert.get("tool_name") or "",
        "description": (rule.get("description") or alert.get("summary") or "")[:200],
        "path": loc.get("path") or loc.get("ref") or "",
        "start_line": loc.get("start_line") or loc.get("line") or "",
        "html_url": alert.get("html_url") or "",
    }


def _markdown_table(rows: list[dict]) -> str:
    lines = [
        "| # | Sev | State | Tool | Rule | Path | Line | Summary |",
        "|---|-----|-------|------|------|------|------|---------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['number']} | {r['severity']} | {r['state']} | {r['tool']} | "
            f"`{r['rule_id']}` | `{r['path']}` | {r['start_line']} | {r['description'][:80]} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merge", action="store_true", help="Append export section to register")
    parser.add_argument("--json-only", action="store_true", help="Write logs only, skip markdown merge")
    args = parser.parse_args()

    forgejo_url = os.environ.get("FORGEJO_URL", "https://trancendos.com/the-workshop")
    token = os.environ.get("FORGEJO_TOKEN") or os.environ.get("FORGEJO_ADMIN_TOKEN")
    repo_spec = os.environ.get("FORGEJO_REPO", "Trancendos/Tranc3")
    if not token:
        print(
            "Set FORGEJO_TOKEN (or FORGEJO_ADMIN_TOKEN) to export alerts.",
            file=sys.stderr,
        )
        return 2

    if "/" in repo_spec:
        owner, repo = repo_spec.split("/", 1)
    else:
        owner, repo = "Trancendos", repo_spec

    api_base = _api_base(forgejo_url)
    alerts = _list_alerts(api_base, owner, repo, token)
    rows = [_alert_row(a) for a in sorted(alerts, key=_severity_rank)]
    critical_open = [
        r for r in rows if r["state"] == "open" and str(r["severity"]).lower() == "critical"
    ]

    LOGS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = LOGS / f"forgejo-code-scanning-alerts-{ts}.json"
    json_path.write_text(json.dumps({"alerts": alerts, "rows": rows}, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} alert(s) to {json_path}")

    if args.json_only:
        return 0 if not critical_open else 1

    section = [
        f"\n## Forgejo export ({ts} UTC)\n",
        f"Repository: `{owner}/{repo}` — **{len(rows)}** alert(s), "
        f"**{len(critical_open)}** open Critical.\n",
        _markdown_table(rows),
    ]
    if critical_open:
        section.append("\n**Open Critical (must FIX/FP/SUPPRESS/ACCEPT):**\n")
        for r in critical_open:
            section.append(f"- #{r['number']} `{r['rule_id']}` {r['path']}:{r['start_line']}\n")

    md_block = "".join(section)
    if args.merge:
        existing = REGISTER.read_text(encoding="utf-8") if REGISTER.is_file() else ""
        marker = "## Forgejo export ("
        if marker in existing:
            existing = existing.split(marker)[0].rstrip() + "\n"
        REGISTER.write_text(existing + md_block, encoding="utf-8")
        print(f"Merged export into {REGISTER}")
    else:
        out = LOGS / f"forgejo-code-scanning-alerts-{ts}.md"
        out.write_text(md_block, encoding="utf-8")
        print(f"Wrote markdown to {out}")

    if critical_open:
        print(f"FAIL: {len(critical_open)} open Critical alert(s) remain.", file=sys.stderr)
        return 1
    print("PASS: 0 open Critical alerts in export.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
