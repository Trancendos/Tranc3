#!/usr/bin/env python3
"""Fail closed on privileged Forgejo runner routing.

Static offline guard: no network, tokens, workflow execution or changes to files.
A deploy-host job is permitted only when it has the exact main-ref guard and
is not reachable through privileged untrusted event contexts. Branch protection
and independent reviews remain mandatory; this is defense in depth.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MAIN_GUARD = re.compile(r"^github\.ref\s*==\s*(['\"])refs/heads/main\1$")
UNTRUSTED_EVENTS = {"pull_request_target", "workflow_run", "issue_comment"}


def _finding(path: str, job: str, code: str, message: str) -> dict[str, str]:
    return {"path": path, "job": job, "code": code, "message": message}


def _guarded(value: object) -> bool:
    if not isinstance(value, str):
        return False
    expression = value.strip()
    if expression.startswith(chr(36) + "{{") and expression.endswith("}}"):
        expression = expression[3:-2].strip()
    return bool(MAIN_GUARD.fullmatch(expression))


def _events(document: dict) -> set[str]:
    # PyYAML 1.1 interprets the YAML key "on" as boolean True.
    triggers = document.get("on", document.get(True, {}))
    if isinstance(triggers, str):
        return {triggers}
    if isinstance(triggers, list):
        return {str(x) for x in triggers}
    if isinstance(triggers, dict):
        return {str(x) for x in triggers}
    return set()


def _runner(value: object) -> tuple[bool, bool]:
    """(Explicit deploy-host, dynamic selector referencing deploy-host)."""
    if isinstance(value, str):
        if chr(36) + "{{" in value and "deploy-host" in value:
            return False, True
        return value == "deploy-host", False
    if isinstance(value, list):
        parts = [_runner(item) for item in value]
        return any(part[0] for part in parts), any(part[1] for part in parts)
    if isinstance(value, dict):
        return False, "deploy-host" in repr(value)
    return False, False


def audit(root: Path) -> dict:
    folder = root / ".forgejo/workflows"
    findings: list[dict[str, str]] = []
    count = privileged = 0
    if not folder.is_dir():
        findings.append(_finding(
            ".forgejo/workflows", "", "MISSING_WORKFLOWS",
            "Cannot inspect the missing Forgejo workflow directory.",
        ))
    else:
        for file in sorted((*folder.glob("*.yml"), *folder.glob("*.yaml"))):
            count += 1
            path = file.relative_to(root).as_posix()
            try:
                workflow = yaml.safe_load(file.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:
                findings.append(_finding(
                    path, "", "INVALID_WORKFLOW", f"Cannot parse workflow: {type(exc).__name__}.",
                ))
                continue
            if not isinstance(workflow, dict) or not isinstance(workflow.get("jobs"), dict):
                findings.append(_finding(
                    path, "", "INVALID_JOBS", "Workflow must define a jobs mapping.",
                ))
                continue
            for name, job in sorted(workflow["jobs"].items()):
                if not isinstance(job, dict):
                    continue
                explicit, dynamic = _runner(job.get("runs-on"))
                if dynamic:
                    findings.append(_finding(
                        path, str(name), "DYNAMIC_RUNNER",
                        "Dynamic runner selection mentions deploy-host; use an explicit label.",
                    ))
                if not explicit:
                    continue
                privileged += 1
                if not _guarded(job.get("if")):
                    findings.append(_finding(
                        path, str(name), "MISSING_MAIN_GUARD",
                        "deploy-host requires job-level github.ref == 'refs/heads/main'.",
                    ))
                unsafe = sorted(UNTRUSTED_EVENTS & _events(workflow))
                if unsafe:
                    findings.append(_finding(
                        path, str(name), "UNTRUSTED_TRIGGER",
                        "deploy-host cannot run under " + ", ".join(unsafe) + ".",
                    ))
    if privileged:
        config = root / "deploy/forgejo/act-runner-deploy.yml"
        try:
            data = yaml.safe_load(config.read_text(encoding="utf-8"))
            labels = (data or {}).get("runner", {}).get("labels", [])
            if "deploy-host:host" not in labels:
                findings.append(_finding(
                    "deploy/forgejo/act-runner-deploy.yml", "", "RUNNER_CONFIG",
                    "Privileged runner label deploy-host:host is missing.",
                ))
        except (OSError, yaml.YAMLError, TypeError, AttributeError) as exc:
            findings.append(_finding(
                "deploy/forgejo/act-runner-deploy.yml", "", "RUNNER_CONFIG",
                f"Cannot validate runner config: {type(exc).__name__}.",
            ))
    if count == 0:
        findings.append(_finding(
            ".forgejo/workflows", "", "NO_WORKFLOWS",
            "No workflow evidence to inspect; refusing a green result.",
        ))
    return {
        "status": "pass" if not findings else "fail",
        "files_scanned": count,
        "privileged_jobs": privileged,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = audit(args.root)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"Workshop runner guard: {result['status'].upper()}; "
            f"{result['files_scanned']} workflows, "
            f"{result['privileged_jobs']} privileged jobs"
        )
        for item in result["findings"]:
            print(f"  {item['path']}::{item['job']} [{item['code']}] {item['message']}")
    return 0 if not result["findings"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
