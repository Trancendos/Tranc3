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
import fnmatch
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


# Renovate accepts several package selectors. Reading only `matchPackageNames`
# meant a rule written with any of the others was treated as matching nothing --
# so a later rule could re-enable a governed pin and this check would pass.
# `matchPackagePatterns` and `matchPackagePrefixes` are deprecated upstream but
# still honoured, so they still have to be read.
_NAME_SELECTORS = ("matchPackageNames", "matchDepNames")
_PATTERN_SELECTORS = ("matchPackagePatterns",)
_PREFIX_SELECTORS = ("matchPackagePrefixes",)
_ALL_SELECTORS = _NAME_SELECTORS + _PATTERN_SELECTORS + _PREFIX_SELECTORS


def _as_list(value: object) -> list[str]:
    """Normalise a Renovate selector value to a list of written patterns."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _regex_body(written: str) -> str | None:
    """The pattern inside a Renovate `/regex/` selector, or None if it is a glob.

    Renovate wraps regexes in slashes and allows a trailing `i` flag.
    """
    if not written.startswith("/"):
        return None
    for suffix in ("/i", "/"):
        if written.endswith(suffix) and len(written) > len(suffix):
            return written[1 : -len(suffix)]
    return None


def _one_pattern_matches(written: str, package: str) -> bool:
    """Does one written selector value match `package`?

    Renovate's `matchPackageNames` accepts `/regex/`, a minimatch glob, or a
    bare name, and any of them may be negated with a leading `!`. Matching is
    case-insensitive. A bare name is just a glob with no wildcards, so globs
    subsume the exact case.

    The regex form may carry a trailing `i` flag -- `/^py.*/i`. Without
    accepting it, `/^py.*/i` fell through to the glob branch, where a literal
    match against a name containing slashes is impossible, so the selector
    silently matched nothing and any rule using it was read as inert.
    """
    body = _regex_body(written)
    if body is not None:
        try:
            return re.search(body, package, re.IGNORECASE) is not None
        except re.error:
            # An unparseable pattern surfaces here rather than being skipped.
            return True
    return fnmatch.fnmatchcase(package.lower(), written.lower())


def _rule_matches(rule: dict, package: str) -> bool:
    """Does this Renovate rule apply to `package`?

    Renovate's documented semantics: with positive matchers present at least
    one must match; with negative matchers present none may match. A rule
    carrying NO package selector at all applies to every dependency -- treating
    that as "matches nothing" was the hole that let a selectorless rule through.
    """
    positives: list[str] = []
    negatives: list[str] = []

    for key in _NAME_SELECTORS:
        for written in _as_list(rule.get(key)):
            (negatives if written.startswith("!") else positives).append(
                written[1:] if written.startswith("!") else written
            )
    for key in _PATTERN_SELECTORS:
        for written in _as_list(rule.get(key)):
            neg = written.startswith("!")
            body = written[1:] if neg else written
            # matchPackagePatterns values are bare regexes, not /slash/ wrapped.
            (negatives if neg else positives).append(f"/{body}/")
    for key in _PREFIX_SELECTORS:
        for written in _as_list(rule.get(key)):
            neg = written.startswith("!")
            body = written[1:] if neg else written
            (negatives if neg else positives).append(f"{body}*")

    if not any(key in rule for key in _ALL_SELECTORS):
        return True  # selectorless: applies to everything

    if any(_one_pattern_matches(w, package) for w in negatives):
        return False
    if not positives:
        return True
    return any(_one_pattern_matches(w, package) for w in positives)


def _covers_pypi(rule: dict) -> bool:
    """True unless the rule is explicitly scoped away from the pypi datasource.

    The governed pins are Python packages. A disabling rule scoped to `pypi` is
    correct and preferred -- an unscoped one also suppresses the `redis` Docker
    image, whose digest bumps carry real fixes.
    """
    datasources = _as_list(rule.get("matchDatasources"))
    if not datasources:
        return True
    return any(d.lower() == "pypi" for d in datasources)


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
        # An `update-types`-scoped ignore is NOT a full ignore: a major-only
        # entry still lets minor and patch PRs through, which is the whole
        # class of PR this governance exists to stop. Only unrestricted
        # entries count.
        ignored = {
            entry.get("dependency-name")
            for entry in block.get("ignore", []) or []
            if isinstance(entry, dict)
            and not entry.get("update-types")
            and not entry.get("versions")
        }
        missing = sorted(packages - ignored)
        if missing:
            problems.append(
                f"dependabot.yml pip ecosystem {directory!r} does not ignore: " + ", ".join(missing)
            )
    return problems


def _bad_release_ages(config: dict, rules: list) -> list[str]:
    """`minimumReleaseAge` must be a duration string or null -- never `false`.

    Renovate's schema types it `string | null`. `false` was written in four
    places here, meaning "no cooldown", and Renovate rejects the whole config
    on a schema violation -- so the cooldown those rules exist to express, and
    every other rule in the file with it, stops being applied at all. A config
    that does not load is the loudest possible version of a control that does
    not act, and nothing in this repository read the file closely enough to say
    so.
    """
    problems: list[str] = []
    blocks: list[tuple[str, object]] = [("top level", config)]
    for key in ("vulnerabilityAlerts", "osvVulnerabilityAlerts"):
        if isinstance(config.get(key), dict):
            blocks.append((key, config[key]))
    blocks.extend((f"packageRules[{i}]", rule) for i, rule in enumerate(rules))

    for where, block in blocks:
        if not isinstance(block, dict) or "minimumReleaseAge" not in block:
            continue
        value = block["minimumReleaseAge"]
        if value is None or isinstance(value, str):
            continue
        problems.append(
            f"renovate.json {where} sets minimumReleaseAge to {value!r} — the schema "
            'accepts a duration string ("7 days") or null; anything else makes Renovate '
            "reject the entire config, so no rule in this file applies"
        )
    return problems


def check_renovate(packages: set[str]) -> list[str]:
    if not RENOVATE.is_file():
        return [f"{RENOVATE.relative_to(REPO_ROOT)} is missing"]
    try:
        config = json.loads(RENOVATE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"renovate.json is not valid JSON ({exc.msg})"]
    # Valid JSON is not the same as a valid config. A top-level list or scalar
    # parses fine and then raises AttributeError on `.get` -- a crash, which is
    # not the same as a reported failure and reads very differently in CI.
    if not isinstance(config, dict):
        return [f"renovate.json is not a JSON object (got {type(config).__name__})"]
    rules = config.get("packageRules")
    if not isinstance(rules, list):
        return ["renovate.json has no packageRules list"]

    problems: list[str] = _bad_release_ages(config, rules)
    for package in sorted(packages):
        disabling = [
            i
            for i, rule in enumerate(rules)
            if isinstance(rule, dict)
            and rule.get("enabled") is False
            and _rule_matches(rule, package)
            and not rule.get("matchUpdateTypes")
            and _covers_pypi(rule)
        ]
        if not disabling:
            problems.append(
                f"renovate.json does not disable {package!r} for all update types "
                "on the pypi datasource (a rule scoped to matchUpdateTypes, or to a "
                "datasource other than pypi, leaves the rest enabled)"
            )
            continue
        # Renovate evaluates every rule and merges the matches, with later rules
        # overriding earlier ones OPTION BY OPTION. So a later rule that merely
        # groups or sets automerge does not re-enable a disabled package -- only
        # one that sets `enabled: true` does. Flagging every later match would
        # reject legitimate grouping rules and train people to weaken the check.
        last_disable = max(disabling)
        for i in range(last_disable + 1, len(rules)):
            rule = rules[i]
            if (
                isinstance(rule, dict)
                and rule.get("enabled") is True
                and _rule_matches(rule, package)
            ):
                label = rule.get("groupName") or rule.get("description") or f"rule {i}"
                problems.append(
                    f"renovate.json rule {i} ({label!r}) re-enables governed package "
                    f"{package!r} after it was disabled at rule {last_disable}; a "
                    "later `enabled: true` overrides the block"
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
