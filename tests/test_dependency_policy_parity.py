"""The two dependency bots must agree about what is blocked.

`renovate.json` and `.github/dependabot.yml` both propose upgrades into the
same directories, and neither reads the other. A policy written in one is
therefore enforced on one path and open on the other -- which is not a
hypothetical: the React-ecosystem major block added to `renovate.json` in
#1242 left `npm /web` with no dependabot ignore at all, and #1203 ("Bump
react, react-dom and @types/react in /web") arrived through the gap.

This is the same shape as the rest of that PR's findings: a control that
covers one route and reports nothing about the other.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
RENOVATE = REPO / "renovate.json"
DEPENDABOT = REPO / ".github/dependabot.yml"

#: renovate writes `matchPackageNames` as anchored regexes (`/^react$/`) for
#: exact names. Only those are compared -- a genuine pattern rule cannot be
#: restated as a dependabot `dependency-name`, so it is out of scope here
#: rather than silently treated as covered.
_EXACT = re.compile(r"^/\^([A-Za-z0-9@._/-]+)\$/$")


def _renovate_blocked_majors() -> set[str]:
    document = json.loads(RENOVATE.read_text(encoding="utf-8"))
    blocked: set[str] = set()
    for rule in document.get("packageRules") or []:
        if rule.get("enabled") is not False:
            continue
        if "major" not in (rule.get("matchUpdateTypes") or []):
            continue
        for entry in rule.get("matchPackageNames") or []:
            match = _EXACT.match(str(entry))
            if match:
                blocked.add(match.group(1))
    return blocked


def _dependabot_major_ignores() -> set[str]:
    document = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
    ignored: set[str] = set()
    for update in document.get("updates") or []:
        # Every ecosystem, not just npm. renovate's rules are ecosystem-
        # agnostic -- `torch` is pip and `postgres` is a docker image -- so
        # reading one ecosystem's ignores would report a gap that is covered
        # elsewhere, or miss one that is not. An earlier draft of this test did
        # exactly that and named five packages as missing while pointing at the
        # wrong config.
        for entry in update.get("ignore") or []:
            types = entry.get("update-types") or []
            if "version-update:semver-major" in types:
                ignored.add(str(entry.get("dependency-name", "")))
    return ignored


def test_every_major_renovate_blocks_is_also_ignored_by_dependabot() -> None:
    """A block in one config and not the other is a block only half the time."""
    blocked = _renovate_blocked_majors()
    assert blocked, "no exact-name major blocks found in renovate.json -- has the shape changed?"

    missing = sorted(blocked - _dependabot_major_ignores())
    assert not missing, (
        "renovate.json blocks major upgrades for these packages but "
        f".github/dependabot.yml does not ignore them, so dependabot will keep "
        f"proposing what the policy forbids: {missing}"
    )
