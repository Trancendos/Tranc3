#!/usr/bin/env python3
"""Prevent unreviewed vulnerability fixes from breaking coupled dependency families.

OpenTelemetry core and instrumentation dependencies must be upgraded together.
The regular update schedule cannot substitute for vulnerability-alert controls:
those alerts bypass normal Renovate scheduling and can use a separate automerge
setting. This checker has no external Python dependencies.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OTEL_RULE = "/^opentelemetry-/"


def issues(config: Any) -> list[str]:
    if not isinstance(config, dict):
        return ["Renovate configuration must be a JSON object"]
    problems: list[str] = []
    alerts = config.get("vulnerabilityAlerts")
    if not isinstance(alerts, dict) or alerts.get("enabled") is not True:
        problems.append("vulnerability alerts must remain explicitly enabled")
    if not isinstance(alerts, dict) or alerts.get("automerge") is not False:
        problems.append("vulnerability alerts must never auto-merge")
    rules = config.get("packageRules")
    if not isinstance(rules, list) or not rules:
        problems.append("non-empty packageRules are required")
    else:
        # Put the family guard last; a later matching rule could override it.
        final = rules[-1]
        if not isinstance(final, dict):
            problems.append("the final packageRule must be a JSON object")
        else:
            names = final.get("matchPackageNames")
            sources = final.get("matchDatasources")
            valid = (
                isinstance(names, list)
                and OTEL_RULE in names
                and isinstance(sources, list)
                and "pypi" in sources
                and final.get("automerge") is False
                and final.get("groupName") == "OpenTelemetry coordinated upgrades"
            )
            if not valid:
                problems.append(
                    "final packageRule must require reviewed, grouped OpenTelemetry updates"
                )
    return problems


def main() -> int:
    path = ROOT / "renovate.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Dependency bot safety: FAILED — cannot read {path.name}: {exc}", file=sys.stderr)
        return 1
    problems = issues(config)
    if problems:
        print("Dependency bot safety: FAILED", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(
        "Dependency bot safety: PASSED — urgent alerts remain enabled; unattended merging disabled"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
