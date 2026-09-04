#!/usr/bin/env python3
"""Drop the path-injection alerts that were adjudicated false positives — and only those.

WHY THIS EXISTS

`codeql.yml` filtered its Python SARIF with an inline heredoc that removed
EVERY alert whose location fell in one of three files. The step was named
"Filter false-positive path-injection alerts" and its scope was every rule at
every severity: a SQL injection, a hardcoded credential or a deserialisation
alert introduced in `src/agents/goal_manager.py` would have been deleted from
the upload before it reached the Security tab, where nothing would ever show
it had existed.

That is the estate's recurring defect in the place it costs most. The
suppression was not wrong to exist — the three files were adjudicated — but it
was broader than its own name, invisible when it fired, and untestable because
it lived as a heredoc inside a workflow.

WHAT CHANGED

  1. Path AND rule. An alert is dropped only when its file is listed AND its
     rule is a path-injection rule. Everything else is left alone.
  2. It says what it did. The count and the rule of every dropped alert are
     printed, so a filter that suddenly eats forty alerts does not look like
     one that ate none.
  3. It fails on a surprise. An alert in a listed file under a rule NOT being
     suppressed is reported and kept — the adjudication covered path injection,
     not whatever else turns up there later.
  4. It fails on rot. A listed path that no longer exists is a suppression
     nobody has revisited, and it is reported.

Usage:
    python scripts/filter_codeql_alerts.py sarif-results/python.sarif
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Adjudicated false positives, each with the reason it is here. The reason is
# not decoration: without it, a reader six months from now cannot tell a
# considered suppression from somebody silencing a red build.
SUPPRESSED_PATHS: dict[str, str] = {
    "Dimensional/path_validation.py": (
        "the module IS the path validator — CodeQL flags the very code that "
        "performs the containment check it is asking for"
    ),
    "Dimensional/orchestration/heartbeat_aggregator.py": (
        "paths here are built from an internal service registry, never from request data"
    ),
    "src/agents/goal_manager.py": (
        "goal ids are validated against a fixed allow-list before they reach any path expression"
    ),
}

# Only these rules are covered by the adjudication above. Substring match
# rather than exact ids, because CodeQL renames and re-scopes query ids between
# releases and a suppression keyed to an exact id silently stops applying —
# which fails in the SAFE direction (the alert reappears) and so is the right
# way round to be imprecise.
SUPPRESSED_RULE_MARKERS = ("path-injection", "path-traversal")


def _rule_id(result: dict) -> str:
    return str(result.get("ruleId") or result.get("rule", {}).get("id") or "")


def _paths(result: dict) -> list[str]:
    out = []
    for location in result.get("locations", []):
        uri = location.get("physicalLocation", {}).get("artifactLocation", {}).get("uri", "")
        if uri:
            out.append(uri)
    return out


def _is_suppressed_rule(rule_id: str) -> bool:
    lowered = rule_id.lower()
    return any(marker in lowered for marker in SUPPRESSED_RULE_MARKERS)


def filter_sarif(sarif: dict) -> tuple[dict, list[str], list[str]]:
    """Returns (filtered sarif, what was dropped, what was kept but surprising)."""
    dropped: list[str] = []
    surprises: list[str] = []
    for run in sarif.get("runs", []):
        kept = []
        for result in run.get("results", []):
            rule_id = _rule_id(result)
            hit = [p for p in _paths(result) if p in SUPPRESSED_PATHS]
            if not hit:
                kept.append(result)
                continue
            if _is_suppressed_rule(rule_id):
                dropped.append(f"{hit[0]} — {rule_id}")
                continue
            # A listed file, a rule nobody adjudicated. Keep it and say so: the
            # decision covered path injection, not everything that file might
            # ever trip.
            surprises.append(
                f"{hit[0]} raised {rule_id}, which is NOT covered by the "
                "path-injection adjudication — kept, and it needs a decision"
            )
            kept.append(result)
        run["results"] = kept
    return sarif, dropped, surprises


def stale_paths() -> list[str]:
    return [
        f"{path} is listed as an adjudicated false positive but no longer exists"
        for path in SUPPRESSED_PATHS
        if not os.path.exists(os.path.join(REPO_ROOT, path))
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sarif", help="path to the SARIF file to filter in place")
    parser.add_argument(
        "--strict-surprises",
        action="store_true",
        help="exit 1 when a listed file raises an unadjudicated rule",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    problems = stale_paths()

    if not os.path.exists(args.sarif):
        # Nothing to filter is not a failure: the analyze step skips languages
        # it did not run. Stale-path problems are still reported.
        print(f"{args.sarif} does not exist — nothing to filter")
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        return 1 if problems else 0

    with open(args.sarif, encoding="utf-8") as handle:
        sarif = json.load(handle)

    sarif, dropped, surprises = filter_sarif(sarif)

    with open(args.sarif, "w", encoding="utf-8") as handle:
        json.dump(sarif, handle)

    print(f"Suppressed path-injection alerts dropped: {len(dropped)}")
    for line in dropped:
        print(f"  {line}")
    for line in surprises:
        print(f"KEPT {line}", file=sys.stderr)
    for problem in problems:
        print(f"FAIL {problem}", file=sys.stderr)

    if problems:
        return 1
    if surprises and args.strict_surprises:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
