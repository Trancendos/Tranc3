#!/usr/bin/env python3
"""Audit pinned GitHub Action references for version drift.

Parses every workflow YAML under `.github/workflows/` and `.forgejo/workflows/`,
extracts `uses:` references that pin a commit SHA, resolves the latest released
commit for each action via the GitHub REST API, and reports any reference whose
pinned SHA differs from the latest as a build annotation.

Only the default ``GITHUB_TOKEN`` is used (read-only public metadata access).
Actions hosted on non-GitHub domains (e.g. ``code.forgejo.org``) are recorded but
not audited, since their latest version cannot be resolved through api.github.com.

Outputs:
  * ``ACTION_AUDIT.md``   human-readable summary (uploaded as artifact)
  * ``action-audit.json`` machine-readable report (uploaded as artifact)
  * ``::warning::`` annotations for every outdated reference (file + line)
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import OrderedDict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

WORKFLOW_DIRS = [".github/workflows", ".forgejo/workflows"]
SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
USES_RE = re.compile(r"^\s*-?\s*uses:\s*(\S+)\s*(?:#.*)?$")
GITHUB_API = "https://api.github.com"

# Exit code when outdated references are found (annotations are still emitted).
FAIL_ON_OUTDATED = os.environ.get("FAIL_ON_OUTDATED", "false").lower() in ("1", "true", "yes")


def github_get(path: str, token: str | None) -> tuple[int, dict]:
    url = f"{GITHUB_API}{path}"
    req = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "action-version-audit",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode())
    except HTTPError as exc:
        body = {}
        try:
            body = json.loads(exc.read().decode())
        except Exception:
            pass
        return exc.code, body
    except URLError as exc:
        return 0, {"message": str(exc.reason)}


def resolve_latest_commit(owner: str, repo: str, token: str | None) -> tuple[str, str, str]:
    """Return (tag, commit_sha, error). error is '' on success."""
    status, data = github_get(f"/repos/{owner}/{repo}/releases/latest", token)
    tag = None
    if status == 200 and data.get("tag_name"):
        tag = data["tag_name"]
    else:
        status, data = github_get(f"/repos/{owner}/{repo}/tags?per_page=1", token)
        if status == 200 and isinstance(data, list) and data:
            tag = data[0].get("name")
    if not tag:
        return "", "", f"no released tag found (api status {status})"
    status, data = github_get(f"/repos/{owner}/{repo}/commits/{tag}", token)
    if status == 200 and data.get("sha"):
        return tag, data["sha"].lower(), ""
    return tag, "", f"could not resolve commit for tag {tag!r} (api status {status})"


def parse_uses(value: str) -> dict | None:
    """Normalise a `uses:` value into owner/repo + pinned sha, or None if unpinned."""
    if "@" not in value:
        return None
    ref, _, sha = value.rpartition("@")
    if not SHA_RE.match(sha):
        return None
    if ref.startswith("https://"):
        host = ref.split("/", 3)[2]
        if host != "github.com":
            return {"kind": "external", "host": host, "ref": ref, "sha": sha.lower()}
        ref = ref.replace("https://github.com/", "", 1)
    # ref is now "owner/repo[/subpath...]"
    parts = ref.split("/")
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    subpath = "/".join(parts[2:]) if len(parts) > 2 else ""
    return {
        "kind": "github",
        "owner": owner,
        "repo": repo,
        "subpath": subpath,
        "ref": ref,
        "sha": sha.lower(),
    }


def main() -> int:
    root = Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd()))
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("INPUT_GITHUB_TOKEN")
    findings = []
    repo_cache: "OrderedDict[str, tuple[str, str, str]]" = OrderedDict()
    external = []

    for wf_dir in WORKFLOW_DIRS:
        base = root / wf_dir
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.yml")) + sorted(base.rglob("*.yaml")):
            rel = path.relative_to(root).as_posix()
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError as exc:
                print(f"::warning::Could not read {rel}: {exc}")
                continue
            for idx, line in enumerate(lines, start=1):
                m = USES_RE.match(line)
                if not m:
                    continue
                parsed = parse_uses(m.group(1))
                if parsed is None:
                    continue
                if parsed["kind"] == "external":
                    external.append({"file": rel, "line": idx, **parsed})
                    continue
                owner, repo = parsed["owner"], parsed["repo"]
                key = f"{owner}/{repo}"
                if key not in repo_cache:
                    tag, commit, err = resolve_latest_commit(owner, repo, token)
                    repo_cache[key] = (tag, commit, err)
                tag, commit, err = repo_cache[key]
                if err:
                    findings.append(
                        {
                            "file": rel,
                            "line": idx,
                            "ref": parsed["ref"],
                            "pinned": parsed["sha"],
                            "status": "unknown",
                            "detail": err,
                        }
                    )
                    continue
                if parsed["sha"] == commit:
                    status = "current"
                else:
                    status = "outdated"
                findings.append(
                    {
                        "file": rel,
                        "line": idx,
                        "ref": parsed["ref"],
                        "pinned": parsed["sha"],
                        "latest_tag": tag,
                        "latest_commit": commit,
                        "status": status,
                    }
                )

    outdated = [f for f in findings if f["status"] == "outdated"]
    unknown = [f for f in findings if f["status"] == "unknown"]

    for f in outdated:
        msg = (
            f"Outdated action {f['ref']} pinned at {f['pinned'][:12]} "
            f"but latest ({f['latest_tag']}) is {f['latest_commit'][:12]}"
        )
        print(f"::warning file={f['file']},line={f['line']}::{msg}")
    for f in unknown:
        print(
            f"::warning file={f['file']},line={f['line']}::"
            f"Could not verify {f['ref']}: {f['detail']}"
        )

    report = {
        "total_references": len(findings) + len(external),
        "github_references": len(findings),
        "external_references": len(external),
        "outdated": len(outdated),
        "unknown": len(unknown),
        "findings": findings,
        "external": external,
    }
    (root / "action-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = [
        "# GitHub Action Version Audit",
        "",
        f"- Total pinned references: **{report['total_references']}**",
        f"- GitHub-hosted audited: **{report['github_references']}** "
        f"(outdated: **{len(outdated)}**, unverifiable: **{len(unknown)}**)",
        f"- External-host references (not audited): **{len(external)}**",
        "",
        "## Outdated references",
    ]
    if outdated:
        for f in outdated:
            md.append(
                f"- `{f['ref']}` in `{f['file']}:{f['line']}` — "
                f"pinned `{f['pinned'][:12]}` vs latest `{f['latest_tag']}` "
                f"(`{f['latest_commit'][:12]}`)"
            )
    else:
        md.append("- None — all pinned SHAs match the latest released commit.")
    md.append("")
    md.append("## Unverifiable references")
    if unknown:
        for f in unknown:
            md.append(f"- `{f['ref']}` in `{f['file']}:{f['line']}` — {f['detail']}")
    else:
        md.append("- None.")
    md.append("")
    md.append("## External-host references (skipped)")
    if external:
        for f in external:
            md.append(f"- `{f['ref']}` in `{f['file']}:{f['line']}` (host: {f['host']})")
    else:
        md.append("- None.")
    (root / "ACTION_AUDIT.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(
        f"\nAudit complete: {len(outdated)} outdated, {len(unknown)} unverifiable "
        f"of {report['total_references']} pinned references."
    )
    if outdated and FAIL_ON_OUTDATED:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
