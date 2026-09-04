"""The generated solution packs, and the gate that keeps them current.

`build_solution_packs.py --check` is only worth wiring into CI if it fails
for reasons worth acting on. Two things stop that being true, and both have
already happened: output the repository's own formatter rewrites, and output
that churns on facts which do not change what a pack says.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PACKS = REPO / "docs" / "solution-packs"


def _load():
    path = REPO / "scripts" / "build_solution_packs.py"
    spec = importlib.util.spec_from_file_location("build_solution_packs", path)
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: the module defines dataclasses, and
    # dataclasses resolve their own annotations through sys.modules.
    sys.modules["build_solution_packs"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def packs():
    return _load()


class TestTheOutputAgreesWithTheHooks:
    def test_no_line_carries_trailing_whitespace(self, packs):
        """Calibrated: restoring the markdown hard break fails this.

        The pack header used a two-space line break. pre-commit's
        trailing-whitespace hook strips it, so the moment pre-commit.ci ran it
        rewrote all 44 packs and left `--check` failing on a diff nobody
        wrote — turning the drift gate into a standing red light.
        """
        rendered = packs._document(["a  ", "b\t", ""])
        assert rendered == "a\nb\n"

    def test_no_file_ends_with_a_blank_line(self, packs):
        """Calibrated: joining without trimming fails this.

        end-of-file-fixer removes it, with the same consequence.
        """
        assert packs._document(["a", "", ""]) == "a\n"

    def test_the_committed_packs_satisfy_both_rules(self):
        """The rules asserted against what is actually on disk."""
        offenders = []
        for path in sorted(PACKS.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if any(line != line.rstrip() for line in text.splitlines()):
                offenders.append(f"{path.name}: trailing whitespace")
            if text.endswith("\n\n") or not text.endswith("\n"):
                offenders.append(f"{path.name}: file does not end in exactly one newline")
        assert offenders == []


class TestTheGateFailsOnlyOnMeaning:
    def test_the_readiness_reasons_carry_no_exact_file_count(self, packs, tmp_path):
        """Calibrated: printing the count again fails this.

        The score buckets at one and three files, so an exact count adds
        nothing a reader can act on — and it made every pack stale on any
        commit that added a file beneath a Location's path, score unchanged.
        A gate that cries wolf is one people learn to regenerate past.
        """
        packs.build(tmp_path)
        chaos = (tmp_path / "the-chaos-party.md").read_text(encoding="utf-8")
        readiness = [line for line in chaos.splitlines() if "| Readiness |" in line]
        assert readiness, "the pack no longer states a readiness score"
        assert "test file(s) (+1)" not in readiness[0]
        assert "at least one test file present (+1)" in readiness[0]

    def test_the_committed_packs_are_current(self, packs, tmp_path):
        """Regenerate into a temp dir and compare, as --check does."""
        packs.build(tmp_path)
        rebuilt = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.glob("*.md")}
        committed = {p.name: p.read_text(encoding="utf-8") for p in PACKS.glob("*.md")}
        assert rebuilt == committed
