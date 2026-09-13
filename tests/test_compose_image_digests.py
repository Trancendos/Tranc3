"""The compose digest ratchet must fail on a NEW un-digested image pin.

cubic flagged one SBOM whose container reference was a mutable tag. The SBOM was
generated from compose and was reporting that pin accurately, so the defect was
upstream -- and measuring the class found un-digested pins across the estate,
most of them `:latest`. These tests hold the ratchet to its job: known debt
passes, new debt fails.

cubic then found three blind spots in the guard itself, and each has a paired
probe below -- one case that must be flagged, one that must stay green:

  coverage     a compose file outside the repository root must be scanned;
               one inside a submodule must not be
  stability    a pin's baseline identity must not move when an unrelated edit
               above it shifts its line number
  interpolation  `${VAR:-default}` must be resolved to its default; a bare
               `${VAR}` must still be skipped rather than guessed at
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.check_compose_image_digests import (
    CannotReadBaseline,
    Pin,
    compose_files,
    load_baseline,
    resolve,
    undigested,
)

REPO = Path(__file__).resolve().parent.parent
DIGEST = "@sha256:" + "a" * 64


@pytest.fixture
def estate(tmp_path: Path) -> Path:
    (tmp_path / "docker-compose.production.yml").write_text(
        "services:\n"
        "  good:\n"
        f"    image: minio/minio:latest{DIGEST}\n"
        "  bad:\n"
        "    image: cr.weaviate.io/semitechnologies/weaviate:1.25.4\n"
        "  interpolated:\n"
        "    image: ${REGISTRY}/thing:1.0\n"
    )
    return tmp_path


def _images(root: Path) -> set[str]:
    return {pin.image for pin in undigested(root=root)}


def test_an_undigested_pin_is_found(estate: Path) -> None:
    found = undigested(root=estate)
    assert len(found) == 1
    assert found[0].image == "cr.weaviate.io/semitechnologies/weaviate:1.25.4"
    assert found[0].file == "docker-compose.production.yml"
    assert found[0].line == 5


def test_a_digest_pinned_image_is_not_flagged(estate: Path) -> None:
    """The other half of the probe: a correctly pinned image must stay green."""
    assert not any("minio" in image for image in _images(estate))


def test_a_bare_interpolated_image_is_not_flagged(estate: Path) -> None:
    """`${REGISTRY}/thing:1.0` resolves at deploy time.

    This file cannot know what it becomes, and reporting it would be a finding
    nobody can act on -- the fastest way to get a guard switched off.
    """
    assert resolve("${REGISTRY}/thing:1.0") is None
    assert not any("REGISTRY" in image or "thing" in image for image in _images(estate))


# -- coverage: the guard globbed the repository root only -------------------


def test_a_compose_file_outside_the_root_is_scanned(tmp_path: Path) -> None:
    """Ten compose files live under deploy/ and docker/. A root-only glob passed
    every one of them without looking."""
    nested = tmp_path / "deploy" / "forgejo"
    nested.mkdir(parents=True)
    (nested / "docker-compose.yml").write_text(
        "services:\n  a:\n    image: gitea/act_runner:latest\n"
    )

    assert "gitea/act_runner:latest" in _images(tmp_path)
    assert nested / "docker-compose.yml" in compose_files(tmp_path)


def test_a_submodule_compose_file_is_not_scanned(tmp_path: Path) -> None:
    """`workers/cranbania` is another repository. Its pins are its own to guard,
    and failing this repo's CI for them would be a finding nobody here can fix."""
    sub = tmp_path / "workers" / "cranbania"
    sub.mkdir(parents=True)
    (sub / ".git").write_text("gitdir: ../../.git/modules/workers/cranbania\n")
    (sub / "docker-compose.dev.yml").write_text("services:\n  a:\n    image: someone/else:latest\n")

    assert "someone/else:latest" not in _images(tmp_path)
    assert sub / "docker-compose.dev.yml" not in compose_files(tmp_path)


def test_a_vendored_compose_file_is_not_scanned(tmp_path: Path) -> None:
    vendored = tmp_path / "node_modules" / "thing"
    vendored.mkdir(parents=True)
    (vendored / "docker-compose.yml").write_text(
        "services:\n  a:\n    image: vendored/thing:latest\n"
    )

    assert "vendored/thing:latest" not in _images(tmp_path)


# -- stability: the baseline was keyed on file:line -------------------------


def test_a_pins_identity_survives_a_line_move(tmp_path: Path) -> None:
    """Adding a service above a listed pin used to report it [NEW] at its new
    line and [FIXED] at the old one -- CI red for an edit that changed nothing."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  a:\n    image: thing:latest\n")
    before = undigested(root=tmp_path)[0]

    compose.write_text(
        "services:\n  # an unrelated comment\n  b:\n    image: other"
        + DIGEST
        + "\n  a:\n    image: thing:latest\n"
    )
    after = undigested(root=tmp_path)[0]

    assert after.line != before.line, "the fixture must actually move the pin"
    assert after.key == before.key


def test_the_key_still_separates_the_same_image_in_two_files(tmp_path: Path) -> None:
    """Keying on file+image must not collapse two files' copies into one entry."""
    (tmp_path / "docker-compose.yml").write_text("services:\n  a:\n    image: thing:latest\n")
    nested = tmp_path / "deploy" / "x"
    nested.mkdir(parents=True)
    (nested / "docker-compose.yml").write_text("services:\n  a:\n    image: thing:latest\n")

    assert len({pin.key for pin in undigested(root=tmp_path)}) == 2


# -- interpolation: a default after :- is exactly what runs -----------------


def test_an_interpolated_default_without_a_digest_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  a:\n    image: ${RUNNER_IMAGE:-code.forgejo.org/forgejo/runner:3}\n"
    )
    assert "code.forgejo.org/forgejo/runner:3" in _images(tmp_path)


def test_an_interpolated_default_with_a_digest_is_not_flagged(tmp_path: Path) -> None:
    (tmp_path / "docker-compose.yml").write_text(
        f"services:\n  a:\n    image: ${{RUNNER_IMAGE:-forgejo/runner:3{DIGEST}}}\n"
    )
    assert not undigested(root=tmp_path)


def test_a_quoted_image_is_unwrapped(tmp_path: Path) -> None:
    """`image: "${VAR:-x}"` left the quotes attached, so the pin recorded a name
    no registry has. One estate pin was hidden this way."""
    (tmp_path / "docker-compose.yml").write_text(
        'services:\n  a:\n    image: "${RUNNER_IMAGE:-code.forgejo.org/forgejo/runner:3}"\n'
    )
    assert _images(tmp_path) == {"code.forgejo.org/forgejo/runner:3"}


# -- the baseline itself ----------------------------------------------------


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
    assert {pin.key for pin in undigested()} == load_baseline(), (
        "the baseline has drifted from the tree — run "
        "scripts/check_compose_image_digests.py --update-baseline only when "
        "burning entries DOWN"
    )


def test_the_baseline_carries_no_line_numbers() -> None:
    """A line number in a key is the instability this guard was re-keyed to fix."""
    for entry in load_baseline():
        assert not re.search(r"\.ya?ml:\d+", entry), entry
        file, _, image = entry.partition(" ")
        assert file.endswith((".yml", ".yaml")) and image, entry


def test_the_baseline_is_debt_not_an_allowance() -> None:
    """It must stay small and it must say so, so nobody grows it casually."""
    payload = json.loads((REPO / "config" / "estate" / "compose_digest_baseline.json").read_text())
    assert "burn down" in payload["_comment"]
    # 11 before the guard was widened to the whole tree and to interpolated
    # defaults; the three added are pins that were always there, unseen.
    assert len(payload["undigested"]) <= 14, "un-digested compose pins must not grow"


def test_the_real_estate_is_scanned_beyond_the_root() -> None:
    """The coverage hole, asserted against the real tree rather than a fixture."""
    scanned = {path.relative_to(REPO).as_posix() for path in compose_files()}
    assert "deploy/forgejo/docker-compose.yml" in scanned
    assert "docker-compose.production.yml" in scanned
    assert not any(part.startswith("workers/cranbania") for part in scanned)


def test_pin_reports_a_live_location() -> None:
    """The key is stable; the message still has to say where to go and fix it."""
    assert Pin(file="docker-compose.yml", line=7, image="x:latest").located() == (
        "docker-compose.yml:7 x:latest"
    )
