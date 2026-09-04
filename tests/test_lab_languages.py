"""Calibration for The Lab's language and skill capability registry.

The Lab's worker declared twelve languages in a set it referenced exactly
once — at its own definition. Nothing validated against it, nothing exposed
it, and a request naming any language at all went straight into a prompt.
So the tests here are mostly about the difference between a capability claim
and a capability.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import check_lab_languages, lab_capability_report  # noqa: E402
from src.lab.languages import (  # noqa: E402
    LANGUAGES,
    Verification,
    language,
    resolve_language,
    skills_matrix,
    verification_for,
)


def _has(*binaries: str):
    """A `which` that knows exactly this toolchain and nothing else."""
    available = set(binaries)
    return lambda binary: f"/usr/bin/{binary}" if binary in available else None


_NOTHING = _has()


class TestVerificationIsMeasuredNotDeclared:
    def test_an_empty_toolchain_leaves_most_languages_unverifiable(self):
        """Calibrated: returning a declared tier instead of measuring fails this.

        This is the finding the registry exists to state. With no binaries
        on PATH, The Lab can write twenty-nine languages and prove something
        about two.
        """
        matrix = skills_matrix(_NOTHING)
        assert matrix["verifiable"] == 2
        assert matrix["by_verification"]["none"] == len(LANGUAGES) - 2

    def test_python_is_verifiable_with_no_binaries_at_all(self):
        """`ast` is in the standard library of the process doing the asking."""
        assert verification_for("python", _NOTHING) is Verification.PARSE

    def test_a_present_linter_raises_the_tier(self):
        """Calibrated: ignoring the toolchain fails this."""
        assert verification_for("python", _has("ruff")) is Verification.LINT

    def test_the_highest_available_tier_wins_not_the_last_listed(self):
        """Calibrated: taking the last matching tool fails this.

        Shell is the case that proves it, and Python is not. Python's tools
        ascend — ruff, mypy, pytest — so last-listed and highest agree for
        every subset, and a test written on Python passes under the mutation
        it names. Shell declares shellcheck (lint) before bash (parse), so
        with both present the last match is *lower* than the maximum.
        """
        assert verification_for("shell", _has("shellcheck", "bash")) is Verification.LINT

    def test_a_tool_that_is_absent_contributes_nothing(self):
        assert verification_for("rust", _has("ruff")) is Verification.NONE

    def test_tiers_are_ranked_by_capability_not_alphabetically(self):
        """Calibrated: comparing enum values as strings fails this.

        Sorted as text the order is lint, none, parse, test, type — so an
        alphabetical comparison ranks a type checker above a test runner.
        Go does not expose that (parse before test agrees either way);
        TypeScript does, because tsc unlocks TYPE and node unlocks TEST, and
        only a capability-ordered comparison prefers the runner.
        """
        assert verification_for("typescript", _has("eslint", "tsc", "node")) is Verification.TEST

    def test_an_unknown_language_is_none_rather_than_an_error(self):
        """The caller asked what can be proved; for something unknown it is nothing."""
        assert verification_for("brainfuck", _NOTHING) is Verification.NONE


class TestNameResolution:
    @pytest.mark.parametrize(
        ("spelling", "expected"),
        [
            ("Golang", "go"),
            ("C++", "cpp"),
            ("  node  ", "javascript"),
            ("PY", "python"),
            ("yml", "yaml"),
        ],
    )
    def test_common_spellings_resolve(self, spelling, expected):
        """Calibrated: dropping the alias table fails this.

        Refusing "golang" would push callers back to the free-form string
        this registry replaced.
        """
        entry = resolve_language(spelling)
        assert entry is not None and entry.id == expected

    def test_an_unknown_spelling_resolves_to_nothing(self):
        assert resolve_language("cobol") is None

    def test_lookup_by_id_does_not_accept_an_alias(self):
        """Calibrated: making `language()` alias-aware fails this.

        The two functions answer different questions, and collapsing them
        would let an alias be stored as a canonical id.
        """
        assert language("golang") is None
        assert language("go") is not None


class TestTheRegistryIsCoherent:
    def test_ids_and_aliases_never_collide(self):
        """Calibrated: adding an alias equal to another language's id fails this.

        A collision would make resolution depend on iteration order.
        """
        seen: dict[str, str] = {}
        for entry in LANGUAGES:
            for name in entry.names():
                assert name not in seen, f"{name} claimed by {seen.get(name)} and {entry.id}"
                seen[name] = entry.id

    def test_every_language_declares_a_family_and_a_paradigm(self):
        for entry in LANGUAGES:
            assert entry.family.strip(), entry.id
            assert entry.paradigms, entry.id

    def test_a_language_with_no_toolchain_declares_why_it_is_still_verifiable(self):
        """Calibrated: giving a language an intrinsic tier with no note fails this.

        PARSE with nothing installed is a claim, and a claim needs its
        reason on the record.
        """
        for entry in LANGUAGES:
            if entry.intrinsic is not Verification.NONE and not entry.toolchain:
                assert entry.notes.strip(), entry.id

    def test_missing_tools_lists_only_what_is_absent(self):
        entry = language("python")
        assert entry is not None
        assert {t.binary for t in entry.missing_tools(_has("ruff"))} == {"mypy", "pytest"}


class TestTheImageReport:
    def test_the_report_measures_the_image_not_the_host(self):
        """Calibrated: using shutil.which fails this on any dev machine.

        A developer box has node, go and gcc, so the host answer and the
        image answer differ by an order of magnitude. Only one of them is
        about the platform.
        """
        matrix = lab_capability_report.report()
        assert matrix["verifiable"] < skills_matrix()["verifiable"]

    def test_the_image_toolchain_comes_from_the_dockerfile_and_requirements(self):
        """Calibrated: dropping the pip parse fails this.

        ruff, mypy and pytest reach the image through requirements.txt, and
        shellcheck through the apt line.
        """
        toolchain = lab_capability_report.image_toolchain()
        assert {"ruff", "mypy", "pytest", "shellcheck"} <= toolchain

    def test_an_uninstalled_toolchain_is_not_claimed(self):
        """Calibrated: defaulting unknown binaries to present fails this."""
        toolchain = lab_capability_report.image_toolchain()
        assert "node" not in toolchain
        assert "cargo" not in toolchain

    def test_python_reaches_the_test_tier_in_the_image(self):
        """The remediation, asserted: pytest is in the image, so it counts."""
        matrix = lab_capability_report.report()
        python = next(e for e in matrix["languages"] if e["id"] == "python")
        assert python["verification"] == Verification.TEST.value

    def test_most_languages_remain_unverifiable_and_the_report_says_so(self):
        """Honest about what the remediation did not fix.

        Five of twenty-nine. node, go, rustc and javac are not pip-installable
        and belong in a verification sidecar, not in this image.
        """
        matrix = lab_capability_report.report()
        assert matrix["verifiable"] == 5
        assert matrix["by_verification"]["none"] == 24


class TestTheWorkerMirror:
    def test_the_worker_and_the_registry_agree(self):
        """Calibrated: adding a language to the registry alone fails this."""
        assert check_lab_languages.main() == 0

    def test_the_worker_actually_validates_its_language(self):
        """Calibrated: removing the _validate_language calls fails this.

        ALLOWED_LANGUAGES existed for a long time and was referenced once,
        at its own definition. The set is not the control; the call is.
        """
        source = (REPO / "workers" / "the-lab" / "main.py").read_text()
        assert source.count("req.language = _validate_language(req.language)") == 5

    def test_the_worker_exposes_the_set_it_enforces(self):
        """A caller refused for guessing wrong must be able to stop guessing."""
        source = (REPO / "workers" / "the-lab" / "main.py").read_text()
        assert '@app.get("/lab/languages")' in source
