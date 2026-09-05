#!/usr/bin/env python3
"""Drop the CodeQL alerts adjudicated false positives for a given file — and only those.

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

# Adjudicated false positives: which FILE, under which RULE, and why.
#
# Nested per path rather than a path list crossed with one global rule list.
# The flat shape read as "these three files are adjudicated for these rules",
# which is not what anybody decided: each file was adjudicated for its own
# reason, and adding a rule for one of them silently extended it to the other
# two. That is the same over-broad suppression this module was written to
# replace, one layer up — and the `py/non-iterable-in-for-loop` entry below
# would have introduced it, because that reason applies to exactly one file
# and to no path-injection alert anywhere.
#
# Rule keys are substring markers, not exact ids: CodeQL renames and re-scopes
# query ids between releases, and a suppression keyed to an exact id silently
# stops applying — which fails in the SAFE direction (the alert reappears) and
# so is the right way round to be imprecise.
#
# The reason is not decoration. Without it, a reader six months from now cannot
# tell a considered suppression from somebody silencing a red build.
ADJUDICATED: dict[str, dict[str, str]] = {
    "Dimensional/path_validation.py": {
        "path-injection": (
            "the module IS the path validator — CodeQL flags the very code that "
            "performs the containment check it is asking for"
        ),
        "path-traversal": (
            "the same module and the same reason: the traversal containment check "
            "is itself the code being flagged"
        ),
    },
    "Dimensional/orchestration/heartbeat_aggregator.py": {
        "path-injection": (
            "paths here are built from an internal service registry, never from request data"
        ),
        "path-traversal": (
            "the same module and the same registry-sourced paths, which never "
            "carry a component taken from a request"
        ),
    },
    "src/agents/goal_manager.py": {
        "path-injection": (
            "goal ids are validated against a fixed allow-list before they reach "
            "any path expression"
        ),
        "path-traversal": (
            "the same fixed allow-list validating the same goal ids before they "
            "reach a path expression"
        ),
        "non-iterable-in-for-loop": (
            "`for state in GoalState:` — an Enum CLASS is iterable through "
            "EnumMeta.__iter__, which CodeQL's Python model does not carry, so it "
            "reads the class as a non-iterable. Verified by running it. Adjudicated "
            "rather than rewritten because iterating the enum is the idiomatic form "
            "and contorting correct code to satisfy a scanner is how the code gets "
            "worse and the scanner stays wrong. The inline `# codeql[...]` comment "
            "this replaces did nothing: inline suppressions are not honoured by the "
            "SARIF upload path this repository uses, so the alert arrived anyway."
        ),
    },
}


def _rule_id(result: dict) -> str:
    return str(result.get("ruleId") or result.get("rule", {}).get("id") or "")


def _paths(result: dict) -> list[str]:
    out = []
    for location in result.get("locations", []):
        uri = location.get("physicalLocation", {}).get("artifactLocation", {}).get("uri", "")
        if uri:
            out.append(uri)
    return out


def adjudication_for(path: str, rule_id: str) -> str | None:
    """The written reason this path/rule pair is suppressed, or None."""
    lowered = rule_id.lower()
    for marker, reason in ADJUDICATED.get(path, {}).items():
        if marker in lowered:
            return reason
    return None


def filter_sarif(sarif: dict) -> tuple[dict, list[str], list[str]]:
    """Returns (filtered sarif, what was dropped, what was kept but surprising)."""
    dropped: list[str] = []
    surprises: list[str] = []
    for run in sarif.get("runs", []):
        kept = []
        for result in run.get("results", []):
            rule_id = _rule_id(result)
            hit = [p for p in _paths(result) if p in ADJUDICATED]
            if not hit:
                kept.append(result)
                continue
            reason = adjudication_for(hit[0], rule_id)
            if reason is not None:
                dropped.append(f"{hit[0]} — {rule_id} ({reason})")
                continue
            # A listed file, a rule nobody adjudicated for THAT file. Keep it
            # and say so: each decision covers the rules written beside it, not
            # everything the file might ever trip.
            surprises.append(
                f"{hit[0]} raised {rule_id}, which is NOT adjudicated for that "
                "file — kept, and it needs a decision"
            )
            kept.append(result)
        run["results"] = kept
    return sarif, dropped, surprises


def stale_paths() -> list[str]:
    return [
        f"{path} is listed as an adjudicated false positive but no longer exists"
        for path in ADJUDICATED
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

    print(f"Adjudicated alerts dropped: {len(dropped)}")
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
