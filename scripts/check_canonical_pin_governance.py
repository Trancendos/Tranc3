#!/usr/bin/env python3
"""Keep the centrally-governed framework pins out of both dependency bots.

WHY THIS EXISTS

`scripts/align_framework_pins.py` owns five pins (`CANONICAL`) that are
restated in 63 requirements files. One version decision therefore arrives as
63 identical line changes, and that script applies them in a single reviewed
pass. Its docstring is explicit that editing `CANONICAL` is how the stack is
bumped.

Nothing stopped the bots from proposing those packages anyway, and on
2026-09-03 the estate was carrying the consequences:

  * #1139, #1140, #1141 — Dependabot `safe-updates` groups that each moved
    `pydantic` in some requirements files but not `CANONICAL`, so the
    `Framework pin check` in `ci.yml` failed them. Unmergeable by
    construction, not by accident.
  * #1054 — Renovate proposing the same `pydantic` bump across all 63 files
    at once, under a `FastAPI stack` rule that set `automerge: true`. The pin
    gate was the only thing between an unreviewed 63-file framework change
    and `main`.

Both configs were fixed. This check exists so they stay fixed: a sixth entry
added to `CANONICAL` without the matching bot exclusions would quietly
restart the whole pattern, and nothing else in CI would notice.

WHAT IT CHECKS

1. Every `CANONICAL` package is listed under `ignore:` for every `pip`
   ecosystem in `.github/dependabot.yml`.
2. Every `CANONICAL` package is disabled in `renovate.json`.
3. No rule *after* the disabling rule matches a governed package. This is the
   subtle half: Renovate applies `packageRules` in order and a later match
   wins, so a disabling rule can be silently undone by a grouping rule placed
   below it — which is exactly how `automerge: true` came to apply to these
   packages. A rule that merely *reads* as a block is the failure mode here.

It fails closed. A config it cannot parse is a failure, never a pass — a
governance check that reports success on a file it did not understand is
worse than no check.

Usage:
    python scripts/check_canonical_pin_governance.py      # exit 1 on drift
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PIN_SCRIPT = REPO_ROOT / "scripts" / "align_framework_pins.py"
DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yml"
RENOVATE = REPO_ROOT / "renovate.json"


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def canonical_packages() -> set[str]:
    """Read CANONICAL out of the pin script without importing it.

    Importing would drag in whatever that module imports; this job installs
    only PyYAML. `check_ai_register.py` learned the same lesson the hard way.
    """
    if not PIN_SCRIPT.is_file():
        _fail(f"{PIN_SCRIPT.relative_to(REPO_ROOT)} is missing")
        raise SystemExit(1)
    tree = ast.parse(PIN_SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "CANONICAL":
                try:
                    value = ast.literal_eval(node.value)  # type: ignore[arg-type]
                except (ValueError, SyntaxError) as exc:
                    _fail("CANONICAL is not a literal dict — cannot verify governance")
                    raise SystemExit(1) from exc
                if not isinstance(value, dict) or not value:
                    _fail("CANONICAL is not a non-empty dict")
                    raise SystemExit(1)
                return {str(k) for k in value}
    _fail("no CANONICAL assignment found in align_framework_pins.py")
    raise SystemExit(1)


def _rule_names(rule: dict) -> list[str]:
    """Package names a Renovate rule targets, as written.

    Renovate accepts both bare names and `/regex/` forms in
    `matchPackageNames`. Both are returned verbatim; matching is done by
    `_rule_matches`.
    """
    names = rule.get("matchPackageNames")
    if names is None:
        return []
    if isinstance(names, str):
        return [names]
    if isinstance(names, list):
        return [str(n) for n in names]
    return []


def _rule_matches(rule: dict, package: str) -> bool:
    for written in _rule_names(rule):
        if written.startswith("/") and written.endswith("/") and len(written) > 1:
            try:
                if re.search(written[1:-1], package):
                    return True
            except re.error:
                # An unparseable pattern is treated as matching, so a broken
                # rule surfaces here rather than being skipped over.
                return True
        elif written == package:
            return True
    return False


def check_dependabot(packages: set[str]) -> list[str]:
    try:
        import yaml
    except ModuleNotFoundError:
        return ["PyYAML is not installed, so dependabot.yml could not be read"]
    if not DEPENDABOT.is_file():
        return [f"{DEPENDABOT.relative_to(REPO_ROOT)} is missing"]
    try:
        config = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"dependabot.yml is not valid YAML ({exc.__class__.__name__})"]
    if not isinstance(config, dict) or not isinstance(config.get("updates"), list):
        return ["dependabot.yml has no updates list"]

    problems: list[str] = []
    pip_blocks = [
        u for u in config["updates"] if isinstance(u, dict) and u.get("package-ecosystem") == "pip"
    ]
    if not pip_blocks:
        return ["dependabot.yml declares no pip ecosystem — expected at least one"]

    for block in pip_blocks:
        directory = block.get("directory", "?")
        ignored = {
            entry.get("dependency-name")
            for entry in block.get("ignore", []) or []
            if isinstance(entry, dict)
        }
        missing = sorted(packages - ignored)
        if missing:
            problems.append(
                f"dependabot.yml pip ecosystem {directory!r} does not ignore: " + ", ".join(missing)
            )
    return problems


def check_renovate(packages: set[str]) -> list[str]:
    if not RENOVATE.is_file():
        return [f"{RENOVATE.relative_to(REPO_ROOT)} is missing"]
    try:
        config = json.loads(RENOVATE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"renovate.json is not valid JSON ({exc.msg})"]
    rules = config.get("packageRules")
    if not isinstance(rules, list):
        return ["renovate.json has no packageRules list"]

    problems: list[str] = []
    for package in sorted(packages):
        disabling = [
            i
            for i, rule in enumerate(rules)
            if isinstance(rule, dict)
            and rule.get("enabled") is False
            and _rule_matches(rule, package)
            and not rule.get("matchUpdateTypes")
        ]
        if not disabling:
            problems.append(
                f"renovate.json does not disable {package!r} for all update types "
                "(a rule scoped to matchUpdateTypes leaves the rest enabled)"
            )
            continue
        # Renovate applies rules in order; a later match wins. A disabling rule
        # undone by a rule below it is the defect this half exists to catch.
        last_disable = max(disabling)
        for i in range(last_disable + 1, len(rules)):
            rule = rules[i]
            if isinstance(rule, dict) and _rule_matches(rule, package):
                label = rule.get("groupName") or rule.get("description") or f"rule {i}"
                problems.append(
                    f"renovate.json rule {i} ({label!r}) matches governed package "
                    f"{package!r} after it was disabled at rule {last_disable}; a "
                    "later match overrides the block"
                )
    return problems


def main() -> int:
    packages = canonical_packages()
    problems = check_dependabot(packages) + check_renovate(packages)

    print(f"Centrally governed pins: {', '.join(sorted(packages))}")
    if problems:
        print()
        for problem in problems:
            _fail(problem)
        print(
            "\nCanonical pin governance: FAILED — these packages are governed by "
            "scripts/align_framework_pins.py, so neither bot may propose them. "
            "Bump them by editing CANONICAL and running that script with --write.",
            file=sys.stderr,
        )
        return 1
    print("Canonical pin governance: PASSED — both bots exclude every governed pin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
