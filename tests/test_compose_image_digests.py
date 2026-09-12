"""The compose digest ratchet must fail on a NEW un-digested image pin.

cubic flagged one SBOM whose container reference was a mutable tag. The SBOM was
generated from compose and was reporting that pin accurately, so the defect was
upstream -- and measuring the class found 11 such pins, eight of them `:latest`.
These tests hold the ratchet to its job: known debt passes, new debt fails.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_compose_image_digests import (
    CannotReadBaseline,
    load_baseline,
    undigested,
)

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def estate(tmp_path: Path) -> Path:
    (tmp_path / "docker-compose.production.yml").write_text(
        "services:\n"
        "  good:\n"
        "    image: minio/minio:latest@sha256:" + "a" * 64 + "\n"
        "  bad:\n"
        "    image: cr.weaviate.io/semitechnologies/weaviate:1.25.4\n"
        "  interpolated:\n"
        "    image: ${REGISTRY}/thing:1.0\n"
    )
    return tmp_path


def test_an_undigested_pin_is_found(estate: Path) -> None:
    found = undigested(root=estate)
    assert len(found) == 1
    assert "weaviate:1.25.4" in found[0]
    assert "docker-compose.production.yml:5" in found[0]


def test_a_digest_pinned_image_is_not_flagged(estate: Path) -> None:
    """The other half of the probe: a correctly pinned image must stay green."""
    assert not any("minio" in entry for entry in undigested(root=estate))


def test_an_interpolated_image_is_not_flagged(estate: Path) -> None:
    """`${REGISTRY}/thing:1.0` resolves at deploy time.

    This file cannot know what it becomes, and reporting it would be a finding
    nobody can act on -- the fastest way to get a guard switched off.
    """
    assert not any(
        "interpolated" in entry or "REGISTRY" in entry for entry in undigested(root=estate)
    )


def test_a_missing_baseline_raises_rather_than_allowing_everything(tmp_path: Path) -> None:
    """No baseline must not read as an empty allowance.

    An empty allowance would fail the whole estate; a silently-empty *current*
    set would pass while comparing against nothing. Either way the guard has to
    say it could not see.
    """
    with pytest.raises(CannotReadBaseline, match="is missing"):
        load_baseline(tmp_path / "absent.json")


def test_a_corrupt_baseline_raises(tmp_path: Path) -> None:
    bad = tmp_path / "baseline.json"
    bad.write_text("{not json")
    with pytest.raises(CannotReadBaseline, match="not valid JSON"):
        load_baseline(bad)


def test_the_real_baseline_matches_the_real_tree() -> None:
    """The committed baseline must describe this repository, not a past one."""
    assert set(undigested()) == load_baseline(), (
        "the baseline has drifted from the tree — run "
        "scripts/check_compose_image_digests.py --update-baseline only when "
        "burning entries DOWN"
    )


def test_the_baseline_is_debt_not_an_allowance() -> None:
    """It must stay small and it must say so, so nobody grows it casually."""
    payload = json.loads((REPO / "config" / "estate" / "compose_digest_baseline.json").read_text())
    assert "burn down" in payload["_comment"]
    assert len(payload["undigested"]) <= 11, "un-digested compose pins must not grow"
