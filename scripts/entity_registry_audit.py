#!/usr/bin/env python3
"""Proactive audit: canonical entity registry vs common mislabels."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.entities.platform import PLATFORM_ENTITIES, get_entity_by_pid


def main() -> int:
    issues: list[dict] = []

    lab = get_entity_by_pid("PID-LAB")
    if lab and lab.agent_beta:
        if lab.agent_beta.code_name == "Syntax-Sage":
            primes = list(lab.primes) if lab.primes else []
            if "Syntax-Sage" in primes or "Sage" in primes:
                issues.append(
                    {
                        "severity": "error",
                        "pid": "PID-LAB",
                        "message": "Syntax-Sage must not appear in primes list",
                    }
                )

    nexus = get_entity_by_pid("PID-NXS")
    if nexus and nexus.lead_ai == "The Nexus":
        issues.append(
            {
                "severity": "warn",
                "pid": "PID-NXS",
                "message": "Lead AI should be Nexus-Prime not The Nexus",
            }
        )

    undefined = [n for n, e in PLATFORM_ENTITIES.items() if "To be Defined" in (e.lead_ai or "")]
    for name in undefined:
        issues.append(
            {
                "severity": "info",
                "location": name,
                "message": "Lead AI still placeholder To be Defined",
            }
        )

    report = {"issues": issues, "total_entities": len(PLATFORM_ENTITIES), "issue_count": len(issues)}
    print(json.dumps(report, indent=2))
    return 1 if any(i["severity"] == "error" for i in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
