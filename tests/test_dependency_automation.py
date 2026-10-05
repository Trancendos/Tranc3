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
# being emptied -- a template regeneration that dropped all twelve entries
# would otherwise satisfy every per-entry check by having nothing to check.
EXPECTED_ENTRIES = 12


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))


def _entry_id(entry: dict) -> str:
    return f"{entry.get('package-ecosystem')}:{entry.get('directory')}"


def test_the_config_still_covers_every_ecosystem(config):
    """Fail closed: an empty `updates:` list must not pass as "all grouped"."""
    entries = config.get("updates") or []
    assert len(entries) == EXPECTED_ENTRIES, (
        f"expected {EXPECTED_ENTRIES} ecosystem entries, found {len(entries)}; "
        f"a regenerated dependabot.yml that drops entries would otherwise pass "
        f"every other test in this file by having nothing left to check"
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
    """Grouping reduces PR count; it does not remove the need for a ceiling."""
    for entry in config["updates"]:
        limit = entry.get("open-pull-requests-limit")
        # `bool` subclasses `int`, so isinstance(True, int) is True and a stray
        # `open-pull-requests-limit: true` would satisfy a naive check.
        assert type(limit) is int and 0 < limit <= 10, (
            f"{_entry_id(entry)} has open-pull-requests-limit={limit!r}; "
            f"an unbounded or missing limit is how 98 PRs happened"
        )
