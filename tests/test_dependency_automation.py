"""The dependency-update configuration is a control, so it is tested like one.

This file exists because of a measured failure, not a hypothetical one. On
2026-08-21 the estate had 98 simultaneously-open Dependabot pull requests. The
cause was not neglect: `.github/dependabot.yml` declared twelve ecosystem
entries, each allowed five open PRs, and had no `groups:` key anywhere.
Ungrouped, Dependabot opens one pull request per dependency. The queue it
produced was larger than anyone would review, so nothing in it was reviewed --
including the security patches mixed in among the noise.

A configuration file that produces that outcome is a defect, and a defect that
is fixed without a test is a defect waiting to return the next time someone
regenerates the file from a template.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
DEPENDABOT = REPO / ".github" / "dependabot.yml"

SAFE_TYPES = {"minor", "patch"}

# The exact set this config is supposed to cover. Asserting membership rather
# than just "every entry that exists is well-formed" is what stops the file
# being emptied -- a template regeneration that dropped every entry would
# otherwise satisfy every per-entry check by having nothing to check.
#
# This was a bare count (`EXPECTED_ENTRIES = 12`) until 2026-09-28, while the
# comment above it already claimed it asserted "the exact set". It did not: a
# count cannot tell a removal from a swap, so replacing `docker:/web` with
# `docker:/nonexistent` would have kept it green. That gap is the same shape as
# the defect that prompted the change which exposed it -- a control that reports
# on something narrower than what it claims to check.
#
# `docker:/workers` and `docker:/deploy` were removed deliberately, not lost.
# Neither had ever scanned a file: dependabot's docker ecosystem does not search
# below the directory it is given, `/workers` holds its 90 Dockerfiles one level
# down, and `/deploy` has no Dockerfile anywhere. Both paths are already covered
# by renovate. See tests/test_dependency_policy_parity.py, whose
# `test_every_docker_block_can_find_something_to_scan` is what keeps a dead
# block from being added back.
EXPECTED_ENTRIES = {
    "pip:/",
    "pip:/tranc3-bots",
    "pip:/workers",
    "npm:/",
    "npm:/web",
    "docker:/",
    "docker:/docker",
    "docker:/tranc3-bots",
    "docker:/web",
    "github-actions:/",
}


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))


def _entry_id(entry: dict) -> str:
    return f"{entry.get('package-ecosystem')}:{entry.get('directory')}"


def test_the_config_still_covers_every_ecosystem(config):
    """Fail closed: an empty `updates:` list must not pass as "all grouped"."""
    present = {_entry_id(entry) for entry in config.get("updates") or []}

    missing = sorted(EXPECTED_ENTRIES - present)
    extra = sorted(present - EXPECTED_ENTRIES)
    assert not missing and not extra, (
        f"dependabot.yml no longer covers what it is supposed to. "
        f"Missing: {missing}. Unexpected: {extra}. A regenerated file that "
        f"dropped entries would otherwise pass every other test here by having "
        f"nothing left to check, and one that swapped a live directory for a "
        f"dead one would have passed the count this replaced."
    )


def test_every_ecosystem_groups_its_safe_updates(config):
    """One reviewed PR per ecosystem beats thirty unreviewed ones."""
    ungrouped = [_entry_id(e) for e in config["updates"] if "groups" not in e]
    assert not ungrouped, (
        f"these ecosystem entries would open one PR per dependency again: {ungrouped}"
    )


def test_safe_updates_cover_patch_and_minor(config):
    """The group has to actually catch the high-volume updates.

    A `groups:` key that grouped nothing would satisfy the check above while
    changing no behaviour -- the shape of control this estate keeps finding.
    """
    for entry in config["updates"]:
        groups = entry["groups"]
        covered = {t for g in groups.values() for t in g.get("update-types", [])}
        assert SAFE_TYPES <= covered, (
            f"{_entry_id(entry)} groups {sorted(covered)}; "
            f"patch and minor must both be grouped or the backlog re-forms"
        )


def test_major_updates_are_never_grouped(config):
    """The property that makes grouping safe rather than merely quiet.

    A Python 3.11 -> 3.14 or Next 15 -> 16 bump changes a runtime. Swept into a
    group of forty patch bumps it gets merged as a side effect of approving
    something else. Majors must stay on their own so they can be refused.
    """
    for entry in config["updates"]:
        for name, group in entry["groups"].items():
            # An omitted `update-types` is NOT an empty list to Dependabot: the
            # group then matches major, minor and patch. Defaulting to [] here
            # would let the assertion below pass on exactly the configuration it
            # exists to forbid, so the key must be present before it is read.
            assert "update-types" in group, (
                f"{_entry_id(entry)} group '{name}' omits update-types; "
                f"Dependabot reads that as 'all types', majors included"
            )
            types = group["update-types"]
            assert "major" not in types, (
                f"{_entry_id(entry)} group '{name}' includes major updates; "
                f"a runtime change must not ride along with patch bumps"
            )


def test_open_pr_limit_is_bounded(config):
    """Grouping reduces PR count; it does not remove the need for a ceiling.

    The lower bound was `0 < limit` until 2026-10-06, which read "every
    ecosystem must open at least one pull request". That is not the invariant;
    the invariant is that no ecosystem is *unbounded*. `0` is GitHub's
    documented value for "disable version updates", and it leaves Dependabot
    *security* updates untouched -- those come from the advisory database and
    take no entry in this file. So 0 is the tightest bound available, not the
    absence of one, and excluding it meant this test forbade turning a
    duplicated generator off.

    Why that matters here: Renovate sets no `enabledManagers`, so it already
    covers every manager this file declares. Two bots editing the same manifest
    lines produced pull requests that conflicted by construction -- vite stood
    at three versions at once. `0` is how that is resolved, and the ceiling this
    test exists to defend is unaffected.
    """
    for entry in config["updates"]:
        limit = entry.get("open-pull-requests-limit")
        # `bool` subclasses `int`, so isinstance(True, int) is True and a stray
        # `open-pull-requests-limit: true` would satisfy a naive check. Note
        # `type(limit) is int` also rejects `True`, which would otherwise pass
        # as 1 -- kept deliberately.
        assert type(limit) is int and 0 <= limit <= 10, (
            f"{_entry_id(entry)} has open-pull-requests-limit={limit!r}; "
            f"an unbounded or missing limit is how 98 PRs happened"
        )
