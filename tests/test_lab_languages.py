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

    def test_a_runtime_without_its_compiler_unlocks_nothing(self):
        """Calibrated: dropping Tool.requires fails this.

        node runs JavaScript. Given TypeScript it has nothing to run until
        tsc has compiled it, so a box with node and no tsc used to report
        TypeScript at TEST — the highest tier there is — for a language it
        could not compile. Written on TypeScript because it is the only
        language here whose runtime is not its own: on Python or Go the same
        mutation changes nothing.
        """
        assert verification_for("typescript", _has("node")) is Verification.NONE
        assert verification_for("typescript", _has("node", "tsc")) is Verification.TEST

    def test_a_prerequisite_does_not_suppress_a_lower_tier(self):
        """tsc alone still type-checks; only the TEST claim needed the pair."""
        assert verification_for("typescript", _has("tsc")) is Verification.TYPE

    def test_missing_tools_lists_only_what_is_absent(self):
        entry = language("python")
        assert entry is not None
        assert {t.binary for t in entry.missing_tools(_has("ruff"))} == {"mypy", "pytest"}


class TestTheImageReport:
    def test_the_report_measures_the_image_not_the_host(self):
        """Calibrated: using shutil.which fails this.

        The anchor is a fully-equipped machine, not this one. Comparing
        against the live host was the first version of this test and it
        proved nothing reliably: a dev box has node, go and gcc and beats the
        image, but a lean CI runner has none of them and loses to it, so the
        assertion changed meaning with the runner. Every binary present is a
        fixed upper bound that no host can move.
        """
        everything = skills_matrix(lambda binary: f"/usr/bin/{binary}")
        assert everything["verifiable"] == len(LANGUAGES)
        assert lab_capability_report.report()["verifiable"] < everything["verifiable"]

    def test_the_image_toolchain_comes_from_the_dockerfile_and_requirements(self):
        """Calibrated: dropping the pip parse fails this.

        ruff, mypy and pytest reach the image through requirements.txt, and
        shellcheck through the apt line.
        """
        toolchain = lab_capability_report.image_toolchain()
        assert {"ruff", "mypy", "pytest", "shellcheck"} <= toolchain

    def test_a_builder_stage_toolchain_is_not_credited_to_the_image(self):
        """Calibrated: scanning the whole Dockerfile fails this.

        A multi-stage build installs a toolchain in a stage that is then
        discarded. Crediting it to the shipped image reports verification
        tiers for tools the running container does not have — the over-claim
        this report exists to prevent, reintroduced by the report itself.
        """
        dockerfile = (
            "FROM golang:1.22 AS builder\n"
            "RUN apt-get install -y shellcheck\n"
            "RUN pip install ruff\n"
            "FROM python:3.11-slim\n"
            "COPY --from=builder /app /app\n"
        )
        stage = lab_capability_report.final_stage(dockerfile)
        assert "golang" not in stage
        assert "shellcheck" not in stage
        assert "ruff" not in stage

    def test_a_single_stage_dockerfile_is_read_whole(self):
        """The baseline the multi-stage rule must not be allowed to break."""
        stage = lab_capability_report.final_stage(
            (lab_capability_report.WORKER / "Dockerfile").read_text()
        )
        assert "shellcheck" in stage

    def test_a_narrow_copy_from_does_not_credit_the_source_image(self):
        """Calibrated: crediting every COPY --from fails this.

        `COPY --from=golang:1.22 /app/binary /app/binary` copies one file. It
        does not put `go` and `gofmt` in the shipped image, and crediting
        them because the source image contains them is the same over-claim
        this report exists to prevent, coming back through the back door.
        """
        dockerfile = "FROM python:3.11-slim\nCOPY --from=golang:1.22 /app/binary /app/binary\n"
        assert not {"go", "gofmt"} & lab_capability_report._base_binaries(dockerfile)

    def test_a_wholesale_copy_from_does_credit_it(self):
        """Calibrated: refusing every COPY --from fails this.

        A copy rooted at a toolchain directory genuinely does bring the
        executables across, and under-reporting is a fault too.
        """
        dockerfile = "FROM python:3.11-slim\nCOPY --from=golang:1.22 /usr/local /usr/local\n"
        assert {"go", "gofmt"} <= lab_capability_report._base_binaries(dockerfile)

    def test_a_narrow_copy_from_the_wrong_directory_is_not_credited(self):
        """Calibrated: a shared generic root list fails this.

        `/usr/bin` used to count as a toolchain root for every image. The
        golang image keeps nothing there — `go` and `gofmt` live under
        `/usr/local/go/bin` — so copying `/usr/bin` from it ships no Go
        toolchain, and crediting one is the over-claim in miniature.
        """
        dockerfile = "FROM python:3.11-slim\nCOPY --from=golang:1.22 /usr/bin /usr/bin\n"
        assert not {"go", "gofmt"} & lab_capability_report._base_binaries(dockerfile)

    def test_a_copy_of_the_images_own_toolchain_directory_is_credited(self):
        """Calibrated: the same generic root list fails this in the other
        direction — `/usr/local/go` was not on it, so the one copy that
        really does ship a Go toolchain read as shipping nothing."""
        dockerfile = "FROM python:3.11-slim\nCOPY --from=golang:1.22 /usr/local/go /usr/local/go\n"
        assert {"go", "gofmt"} <= lab_capability_report._base_binaries(dockerfile)

    def test_a_commented_out_install_is_not_an_install(self):
        """Calibrated: scanning raw Dockerfile lines fails this.

        `# RUN apt-get install -y gcc` is a comment. Reading it as an install
        reports a compiler tier for a compiler the image does not contain.
        """
        dockerfile = "FROM python:3.11-slim\n# RUN apt-get install -y gcc g++\n"
        assert not {"gcc", "g++"} & lab_capability_report._apt_binaries(dockerfile)
        live = "FROM python:3.11-slim\nRUN apt-get install -y gcc g++\n"
        assert {"gcc", "g++"} <= lab_capability_report._apt_binaries(live)

    def test_a_continued_pip_install_still_finds_the_requirements_file(self):
        """Calibrated: matching within a single raw line fails this.

        The ordinary way this line is written wraps across three lines with
        trailing backslashes, and a scanner that stops at the newline sees
        `pip install` with no arguments — so the whole requirements file
        dropped out of the toolchain silently.
        """
        dockerfile = (
            "FROM python:3.11-slim\n"
            "RUN pip install \\\n"
            "  --no-cache-dir \\\n"
            "  -r requirements.txt\n"
        )
        assert lab_capability_report._pip_binaries(dockerfile, "ruff==0.15.8\n") == {"ruff"}

    def test_the_other_spellings_of_a_requirements_install_are_found(self):
        """`python -m pip` and `--requirement=` are the same instruction."""
        dockerfile = (
            "FROM python:3.11-slim\nRUN python -m pip install --requirement=/app/requirements.txt\n"
        )
        assert lab_capability_report._pip_binaries(dockerfile, "mypy==1.19.0\n") == {"mypy"}

    def test_requirements_installed_only_in_a_builder_are_not_credited(self):
        """Calibrated: parsing requirements unconditionally fails this.

        Filtering the Dockerfile to its final stage does nothing for
        requirements.txt, which was read whatever the stages said — so a
        build installing them in a discarded builder still reported the
        tools as present in the shipped image.
        """
        dockerfile = (
            "FROM python:3.11-slim AS b\n"
            "RUN pip install -r requirements.txt\n"
            "FROM python:3.11-slim\n"
            "COPY --from=b /app /app\n"
        )
        assert lab_capability_report._pip_binaries(dockerfile, "ruff==0.15.8\n") == set()

    def test_requirements_installed_in_the_final_stage_are_credited(self):
        dockerfile = "FROM python:3.11-slim\nRUN pip install --no-cache-dir -r requirements.txt\n"
        assert lab_capability_report._pip_binaries(dockerfile, "ruff==0.15.8\n") == {"ruff"}

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


class TestTheChatEndpointUsesTheLanguage:
    """Validating a value and then dropping it is validation theatre.

    `/lab/chat` resolved the language, refused an unknown one, and then made
    every backend call without it: a Rust question reached a model that had
    never been told it was Rust, and came back in a body that did not say
    what it had answered in. Every sibling handler interpolates the language;
    this one now does too.
    """

    @pytest.fixture
    def client(self, monkeypatch):
        import importlib.util

        from fastapi.testclient import TestClient

        monkeypatch.setenv("INTERNAL_SECRET", "a" * 64)
        path = REPO / "workers" / "the-lab" / "main.py"
        spec = importlib.util.spec_from_file_location("the_lab_main_under_test", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module, TestClient(module.app)

    def _post(self, client, body):
        module, http = client
        return http.post("/lab/chat", json=body, headers={"X-Internal-Secret": "a" * 64})

    def test_the_language_reaches_the_backend(self, client, monkeypatch):
        """Calibrated: passing req.messages straight through fails this."""
        module, _ = client
        seen: dict[str, object] = {}

        async def _capture(messages, max_tokens):
            seen["messages"] = messages
            return "ok"

        monkeypatch.setattr(module, "_tabby_chat", _capture)
        r = self._post(
            client, {"messages": [{"role": "user", "content": "hi"}], "language": "rust"}
        )
        assert r.status_code == 200
        assert seen["messages"][0] == {
            "role": "system",
            "content": "You are a rust code assistant.",
        }

    def test_the_response_says_what_it_answered_in(self, client, monkeypatch):
        module, _ = client

        async def _ok(messages, max_tokens):
            return "ok"

        monkeypatch.setattr(module, "_tabby_chat", _ok)
        r = self._post(client, {"messages": [{"role": "user", "content": "hi"}], "language": "go"})
        assert r.json()["language"] == "go"

    def test_a_caller_system_message_is_not_overridden(self, client, monkeypatch):
        """The caller's own framing is more specific than the worker's."""
        module, _ = client
        seen: dict[str, object] = {}

        async def _capture(messages, max_tokens):
            seen["messages"] = messages
            return "ok"

        monkeypatch.setattr(module, "_tabby_chat", _capture)
        self._post(
            client,
            {
                "messages": [
                    {"role": "system", "content": "You are terse."},
                    {"role": "user", "content": "hi"},
                ],
                "language": "go",
            },
        )
        assert seen["messages"][0]["content"] == "You are terse."

    def test_an_unknown_language_is_still_refused(self, client):
        r = self._post(
            client, {"messages": [{"role": "user", "content": "hi"}], "language": "brainfuck"}
        )
        assert r.status_code == 400
