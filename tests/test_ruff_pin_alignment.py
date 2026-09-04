"""Tests for scripts/check_ruff_pin_alignment.py.

Each test is a fault that was injected against the real files to confirm the
check fires, then restored. Synthetic trees under `tmp_path` keep the suite from
depending on whichever ruff the estate is currently pinned to, which moves.

The unpinned-install and Dockerfile cases are not hypothetical: the first
version of this check scanned only `ruff==<version>` inside `*.yml` under the
two workflow directories and skipped everything else in silence, so it reported
"5 surfaces, all on ruff 0.15.8" while `.forgejo/workflows/ci.yml`,
`.forgejo/workflows/nightly.yml`, `.forgejo/workflows/security-scan.yml` and
`.woodpecker.yml` installed ruff unpinned and `deploy/forgejo/runner.Dockerfile`
pinned a third version, 0.4.4.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_ruff_pin_alignment.py"

# The comment sits BETWEEN the repo line and its rev, which is the branch of
# PRE_COMMIT_REV that a comment above the repo line would never exercise.
PRE_COMMIT_TEMPLATE = """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-yaml
  - repo: https://github.com/astral-sh/ruff-pre-commit
    # a comment between the repo and its rev
    rev: {rev}
    hooks:
      - id: ruff-format
"""

WORKFLOW_TEMPLATE = """\
name: Example
jobs:
  lint:
    steps:
      - name: Install ruff
        run: pip install "ruff=={version}"
"""


def _load():
    """Load the checker by path; it is a script, not an installed module."""
    spec = importlib.util.spec_from_file_location("_rpa", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_rpa"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def checker(tmp_path, monkeypatch):
    """The checker pointed at a synthetic repo under tmp_path."""

    def _build(*, workflow_versions=("0.15.8",), rev="v0.15.8", pre_commit_body=None, files=None):
        gh = tmp_path / ".github" / "workflows"
        gh.mkdir(parents=True, exist_ok=True)
        for i, version in enumerate(workflow_versions):
            (gh / f"wf{i}.yml").write_text(
                WORKFLOW_TEMPLATE.format(version=version), encoding="utf-8"
            )
        for name, body in (files or {}).items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

        pre_commit = tmp_path / ".pre-commit-config.yaml"
        if pre_commit_body is None:
            pre_commit_body = PRE_COMMIT_TEMPLATE.format(rev=rev)
        pre_commit.write_text(pre_commit_body, encoding="utf-8")

        module = _load()
        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(module, "PRE_COMMIT", pre_commit)
        return module

    return _build


def test_passes_when_every_surface_agrees(checker):
    module = checker(workflow_versions=("0.15.8", "0.15.8", "0.15.8"), rev="v0.15.8")
    assert module.main() == 0


def test_fails_when_pre_commit_diverges_from_the_workflows(checker):
    """The real defect: pre-commit on v0.16.4 while the workflows ran 0.15.8."""
    module = checker(workflow_versions=("0.15.8", "0.15.8"), rev="v0.16.4")
    assert module.main() == 1


def test_fails_when_two_workflows_disagree(checker):
    """Drift between workflows is the same split gate, in the other direction."""
    module = checker(workflow_versions=("0.15.8", "0.16.4"), rev="v0.15.8")
    assert module.main() == 1


def test_the_leading_v_on_the_pre_commit_rev_is_not_a_divergence(checker):
    """`vX.Y.Z` and `X.Y.Z` name the same ruff; only that difference is tolerated."""
    module = checker(workflow_versions=("0.15.8",), rev="0.15.8")
    assert module.main() == 0


def test_fails_closed_when_the_ruff_rev_cannot_be_read(checker):
    """A file it cannot understand is a failure, never a pass."""
    module = checker(
        workflow_versions=("0.15.8",),
        pre_commit_body="repos:\n  - repo: https://example.invalid/other\n    rev: v1.0.0\n",
    )
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == 1


def test_fails_when_nothing_installs_ruff(checker):
    """An empty surface set must not read as 'all surfaces agree'."""
    module = checker(workflow_versions=(), rev="v0.15.8")
    assert module.main() == 1


def test_fails_when_one_workflow_pins_two_ruff_versions(checker, tmp_path):
    """A single file disagreeing with itself is drift too."""
    module = checker(workflow_versions=("0.15.8",), rev="v0.15.8")
    wf = tmp_path / ".github" / "workflows" / "wf0.yml"
    wf.write_text(
        wf.read_text(encoding="utf-8") + '      - run: pip install "ruff==0.16.4"\n',
        encoding="utf-8",
    )
    assert module.main() == 1


def test_a_rev_for_a_different_repo_is_not_mistaken_for_ruffs(checker):
    """The rev must be read from the ruff-pre-commit block, not the nearest one."""
    body = (
        "repos:\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v0.16.4\n"
        "    hooks:\n"
        "      - id: check-yaml\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        "    rev: v0.15.8\n"
        "    hooks:\n"
        "      - id: ruff-format\n"
    )
    module = checker(workflow_versions=("0.15.8",), pre_commit_body=body)
    assert module.main() == 0


# ── the gap the first version of this check could not see ────────────────────


def test_fails_on_an_unpinned_install(checker):
    """`.forgejo/workflows/ci.yml`: `uv pip install --system ruff --quiet`.

    The original check's `if not found: continue` skipped this file entirely
    and still printed PASSED.
    """
    module = checker(
        files={
            ".forgejo/workflows/ci.yml": (
                "jobs:\n  lint:\n    steps:\n      - run: |\n"
                "          uv pip install --system ruff --quiet\n"
                "          ruff check src/\n"
            )
        }
    )
    assert module.main() == 1


def test_a_yaml_extension_is_scanned_too(checker):
    """Renaming a workflow `.yaml` must not drop it out of the gate."""
    module = checker(
        workflow_versions=(),
        files={".github/workflows/lint.yaml": WORKFLOW_TEMPLATE.format(version="0.16.4")},
    )
    assert module.main() == 1


def test_woodpecker_is_scanned(checker):
    """`.woodpecker.yml` sits under no workflows directory and was invisible."""
    module = checker(
        files={
            ".woodpecker.yml": (
                "steps:\n  ruff-lint:\n    commands:\n"
                '      - pip install --quiet "ruff==0.16.4"\n'
                "      - ruff check .\n"
            )
        }
    )
    assert module.main() == 1


def test_a_dockerfile_pin_is_scanned_across_line_continuations(checker):
    """`deploy/forgejo/runner.Dockerfile` pinned 0.4.4 inside a multi-line RUN.

    The agreeing workflow surface is what makes this test discriminate. Without
    it the Dockerfile was the ONLY possible surface, so `main()` returned 1
    whether the Dockerfile was scanned (0.4.4 diverges) or not scanned at all
    (the "nothing installs ruff" fallback) — a test that could not fail for the
    reason it names.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={
            "deploy/forgejo/runner.Dockerfile": (
                "FROM python:3.11\n"
                "RUN python3 -m pip install --no-cache-dir \\\n"
                "        bandit==1.8.3 \\\n"
                "        ruff==0.4.4 \\\n"
                "        mypy==1.10.0\n"
            )
        },
    )
    assert module.main() == 1


def test_the_dockerfile_finding_points_at_the_ruff_line(checker, tmp_path, capsys):
    """A finding inside a 25-line RUN block must not name the line it opens on."""
    module = checker(
        workflow_versions=(),
        files={
            "deploy/forgejo/runner.Dockerfile": (
                "FROM python:3.11\n"
                "RUN python3 -m pip install --no-cache-dir \\\n"
                "        bandit==1.8.3 \\\n"
                "        ruff==0.4.4 \\\n"
                "        mypy==1.10.0\n"
            )
        },
    )
    module.main()
    assert "runner.Dockerfile:4" in capsys.readouterr().out


def test_a_file_that_runs_ruff_without_installing_it_is_a_failure(checker):
    """It inherits whatever the runner image carries -- an unpinned surface."""
    module = checker(
        files={
            ".forgejo/workflows/nightly.yml": (
                "jobs:\n  lint:\n    steps:\n      - run: ruff check src/ api.py\n"
            )
        }
    )
    assert module.main() == 1


def test_an_install_and_an_invocation_on_one_line_is_not_read_as_unpinned(checker):
    """`pip install "ruff==X" && ruff check .` installs once, pinned."""
    module = checker(
        workflow_versions=(),
        files={
            ".github/workflows/lint.yml": (
                "jobs:\n  lint:\n    steps:\n"
                '      - run: pip install "ruff==0.15.8" && ruff check .\n'
            )
        },
    )
    assert module.main() == 0


def test_prose_and_step_names_are_not_surfaces(checker):
    """Only installs and invocations count; a mention in a comment does not."""
    module = checker(
        files={
            ".forgejo/workflows/docs.yml": (
                "# ruff is documented here but never installed or run\n"
                "jobs:\n  docs:\n    steps:\n"
                "      - name: ruff-lint results\n"
                "        run: cat logs/ruff-results.json\n"
            )
        }
    )
    assert module.main() == 0


def test_ruff_pre_commit_is_not_mistaken_for_the_ruff_package(checker):
    """`ruff-pre-commit` is a different name and must not read as a ruff pin."""
    module = checker(
        files={
            ".github/workflows/other.yml": (
                "jobs:\n  x:\n    steps:\n      - run: pip install ruff-pre-commit\n"
            )
        }
    )
    assert module.main() == 0


def test_fails_closed_on_a_file_it_cannot_read(checker, tmp_path, monkeypatch):
    """An unreadable surface is a file it did not verify, so it is a failure.

    The permission is simulated rather than applied: CI runs this suite as
    root, for whom `chmod 000` is not a denial, so the real mode bits would
    prove nothing.
    """
    module = checker()
    unreadable = tmp_path / ".github" / "workflows" / "locked.yml"
    unreadable.write_text("jobs: {}\n", encoding="utf-8")

    real_read_text = Path.read_text

    def _deny(self, *args, **kwargs):
        if self.name == "locked.yml":
            raise PermissionError(13, "Permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _deny)
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == 1


def test_the_real_repo_surfaces_agree():
    """The estate's actual files, not a synthetic stand-in."""
    module = _load()
    assert module.main() == 0


# ── fail-open paths found by review on the rewritten scanner ─────────────────


def test_a_quoted_hash_does_not_hide_a_later_install(checker):
    """`echo "a # b" && pip install ruff` — the naive comment strip cut here.

    Truncating at the quoted hash meant the unpinned install after it was never
    seen: a fail-open path in the one check whose whole job is to fail closed.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={
            ".github/workflows/quoted.yml": (
                'jobs:\n  lint:\n    steps:\n      - run: echo "a # b" && pip install ruff\n'
            )
        },
    )
    assert module.main() == 1


def test_a_wrapped_invocation_counts_as_running_ruff(checker):
    """`uv run ruff check .` runs ruff; requiring the segment to START with
    `ruff` meant a file doing this and installing nothing looked inert."""
    module = checker(
        workflow_versions=("0.15.8",),
        files={
            ".forgejo/workflows/wrapped.yml": (
                "jobs:\n  lint:\n    steps:\n      - run: uv run ruff check src/\n"
            )
        },
    )
    assert module.main() == 1


def test_a_python_dash_m_invocation_counts_too(checker):
    module = checker(
        workflow_versions=("0.15.8",),
        files={
            ".forgejo/workflows/dashm.yml": (
                "jobs:\n  lint:\n    steps:\n      - run: python -m ruff check src/\n"
            )
        },
    )
    assert module.main() == 1


def test_a_dockerfile_exec_form_invocation_counts(checker):
    """`CMD ["ruff", "check", "."]` starts no shell, so no segment begins with ruff."""
    module = checker(
        workflow_versions=("0.15.8",),
        files={"lint.Dockerfile": 'FROM python:3.11\nCMD ["ruff", "check", "."]\n'},
    )
    assert module.main() == 1


def test_two_installs_on_one_line_do_not_overwrite_each_other(checker):
    """Keying the report by location alone hid the second version entirely.

    `pip install ruff==0.15.8 && pip install ruff==0.16.4` is one line, so the
    later pin overwrote the earlier one in the map and the divergence vanished
    from the very report meant to show it.
    """
    # pre-commit is pinned to the SECOND version deliberately. With the bug the
    # second install overwrote the first, leaving one surface on 0.16.4 that
    # agreed with pre-commit — the check returned 0 on a file pinning two ruffs.
    # Any other rev would make this test pass either way.
    module = checker(
        workflow_versions=(),
        rev="v0.16.4",
        files={
            ".github/workflows/both.yml": (
                "jobs:\n  lint:\n    steps:\n"
                '      - run: pip install "ruff==0.15.8" && pip install "ruff==0.16.4"\n'
            )
        },
    )
    assert module.main() == 1


# ── forms review found the scanner still could not see ───────────────────────


def test_a_dockerfile_run_invocation_is_detected(checker):
    """`RUN ruff check .` carries no colon, so the YAML `key:` prefix missed it.

    A Dockerfile could run ruff without installing it and still pass the gate.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={"lint.Dockerfile": "FROM python:3.11\nRUN ruff check .\n"},
    )
    assert module.main() == 1


def test_an_exec_form_python_dash_m_invocation_is_detected(checker):
    """`CMD ["python", "-m", "ruff", …]` runs ruff without `ruff` as argv[0]."""
    module = checker(
        workflow_versions=("0.15.8",),
        files={"lint.Dockerfile": 'FROM python:3.11\nCMD ["python", "-m", "ruff", "check", "."]\n'},
    )
    assert module.main() == 1


def test_uv_run_with_an_unpinned_package_is_an_install(checker, capsys):
    """`uv run --with ruff` installs into a throwaway env — unpinned is drift.

    The word "install" never appears, and the option sits between the wrapper
    and ruff, so neither the install nor the invocation was seen.

    The assertion is on the REASON, not just the exit code. Both "unpinned
    install" and "runs ruff but never installs it" exit 1, so an exit-code-only
    test passes even when the install is not recognised at all — which is
    exactly what the calibration run showed.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={
            ".github/workflows/uvrun.yml": (
                "jobs:\n  lint:\n    steps:\n      - run: uv run --with ruff ruff check .\n"
            )
        },
    )
    assert module.main() == 1
    assert "installs ruff without pinning a version" in capsys.readouterr().err


def test_uv_run_with_a_pinned_package_is_not_reported_twice(checker):
    """The second `ruff` on that line is the COMMAND, not a second install.

    Scanning to the end of the segment counted it as an unpinned install and
    failed a correctly pinned line — a false positive on valid usage.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={
            ".github/workflows/uvrun.yml": (
                "jobs:\n  lint:\n    steps:\n"
                '      - run: uv run --with "ruff==0.15.8" ruff check .\n'
            )
        },
    )
    assert module.main() == 0


def test_an_escaped_quote_does_not_hide_a_later_install(checker):
    r"""In `echo "a\" # b" && pip install ruff` the backslash closes nothing.

    A stripper that ignores escapes thinks the string is still open and keeps
    the whole line; one that ignores quotes cuts at the hash. Either way an
    install goes missing.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={
            ".github/workflows/esc.yml": (
                'jobs:\n  lint:\n    steps:\n      - run: echo "a\\" # b" && pip install ruff\n'
            )
        },
    )
    assert module.main() == 1


def test_a_comment_ending_in_a_backslash_does_not_swallow_the_next_line(checker, capsys):
    r"""`# note \` is a comment, not a line continuation.

    A regression introduced when comment stripping moved to the JOINED logical
    line: the raw line ended in `\`, so the following command was appended to
    the comment and then cut away with it. The unpinned install on the next
    line became invisible — a fail-open path in the check whose whole job is to
    find unpinned installs.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={
            "tools/Dockerfile": ("RUN true\n# a trailing note \\\nRUN pip install ruff\n"),
        },
    )
    assert module.main() == 1
    assert "installs ruff without pinning a version" in capsys.readouterr().err


def test_a_quoted_hash_still_survives_a_continuation(checker, capsys):
    r"""The other half of the same fix: quote state must cross the join.

    Stripping each physical line independently reset the quote at every `\`,
    so a string carried across a continuation looked closed and the `#` inside
    it read as a comment. Both halves are needed and they pull opposite ways.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={
            "tools/Dockerfile": ('RUN echo "a # b \\\n  more" && pip install ruff\n'),
        },
    )
    assert module.main() == 1
    assert "installs ruff without pinning a version" in capsys.readouterr().err


def test_uvx_from_is_an_install_not_a_bare_invocation(checker):
    """`uvx --from ruff==X ruff check .` is the documented way to pin uvx.

    `--with` and `--spec` were install verbs and `--from` was not, so this read
    as an invocation with no install anywhere in the file and the gate failed a
    correctly pinned command. A check that rejects the right answer is one
    people route around.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={"tools/Dockerfile": "RUN uvx --from ruff==0.15.8 ruff check .\n"},
    )
    assert module.main() == 0


def test_a_second_with_option_is_still_read(checker, capsys):
    """`--with black --with ruff` names two packages; only the first was read.

    Stopping at the first install verb in a segment saw `black`, found no ruff
    install, and reported the line as running ruff without installing it —
    while an unpinned ruff sat in the option right next to it.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={"tools/Dockerfile": "RUN uv run --with black --with ruff ruff check .\n"},
    )
    assert module.main() == 1
    assert "installs ruff without pinning a version" in capsys.readouterr().err


def test_a_second_with_option_that_pins_is_accepted(checker, capsys):
    """The same shape, pinned: accepted AND recorded as a surface.

    Exit 0 alone proves nothing here. Before the fix this line also exited 0 --
    the first verb matched, so the invocation branch was skipped as an `elif`,
    and the file was reported as neither installing nor running ruff. Asserting
    the surface appears in the listing is what separates "recognised and
    pinned" from "not seen at all".
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={"tools/Dockerfile": "RUN uv run --with black --with ruff==0.15.8 ruff check .\n"},
    )
    assert module.main() == 0
    assert "tools/Dockerfile" in capsys.readouterr().out


def test_installing_another_package_does_not_hide_a_ruff_invocation(checker, capsys):
    """`uv run --with black ruff check .` runs ruff from the ambient env.

    The invocation check was an `elif` on "this segment installed something",
    so a segment that installed a DIFFERENT package recorded neither a ruff
    install nor a ruff invocation, and a file whose only use of ruff was that
    line passed the gate on whatever version the runner happened to have.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={"tools/Dockerfile": "RUN uv run --with black ruff check .\n"},
    )
    assert module.main() == 1
    assert "runs ruff" in capsys.readouterr().err


def test_an_install_inside_quotes_is_not_an_install(checker, capsys):
    """`echo 'pip install ruff==0.15.8' && ruff check .` installs nothing.

    The quoted text was matched as a real install, so the file recorded a
    pinned install that never happens and the actual invocation beside it
    passed on whatever ruff the runner already had — the exact drift this check
    exists to catch, written as a string literal.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={"tools/Dockerfile": "RUN echo 'pip install ruff==0.15.8' && ruff check .\n"},
    )
    assert module.main() == 1
    assert "runs ruff" in capsys.readouterr().err


def test_a_quoted_package_on_a_real_install_is_still_read(checker):
    """The other side of the same change: quoting is normal on the ARGUMENT.

    Placing the verb by quote position must not stop the pin being read —
    `pip install "ruff==0.15.8"` is the ordinary way to write it.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={"tools/Dockerfile": 'RUN pip install "ruff==0.15.8"\n'},
    )
    assert module.main() == 0


def test_an_option_before_the_package_option_is_tolerated(checker):
    """`uv run --project . --with ruff==0.15.8 ruff check .` is valid usage.

    Requiring `--with` to follow the runner immediately missed the install and
    failed a correctly pinned command.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={"tools/Dockerfile": "RUN uv run --project . --with ruff==0.15.8 ruff check .\n"},
    )
    assert module.main() == 0


def test_a_tab_between_the_package_and_the_command_is_handled(checker):
    """`split(" ")` put `ruff check .` inside the package span.

    That reported a second, unpinned install on a line that had pinned it —
    a false failure on valid usage.
    """
    module = checker(
        workflow_versions=("0.15.8",),
        files={"tools/Dockerfile": "RUN uv run --with ruff==0.15.8\truff check .\n"},
    )
    assert module.main() == 0


def test_a_step_name_mentioning_ruff_is_not_unwrapped_as_a_command(checker):
    """The scalar pattern accepted ANY `key:`, not only command keys.

    `name: "pip install ruff"` was unwrapped and read as a command, so a job
    title describing what a step does produced a finding about a command
    nobody runs — a false failure on a correct workflow, which is how a gate
    earns a suppression instead of a fix.
    """
    module = checker(
        files={
            ".github/workflows/named.yml": (
                "jobs:\n  x:\n    steps:\n"
                '      - name: "pip install ruff"\n'
                "        run: pip install ruff==0.15.8 && ruff check .\n"
            )
        }
    )
    assert module.main() == 0


def test_a_shell_comment_inside_a_quoted_scalar_is_still_a_comment(checker):
    """YAML strips its quotes before the shell ever sees the line.

    `run: 'echo hi # pip install ruff'` runs `echo hi`; the rest is a shell
    comment. Stripping comments BEFORE unwrapping left the `#` intact (it
    looked quoted), and unwrapping then exposed it as command text — an
    unpinned-install finding for a command that never runs.
    """
    module = checker(
        files={
            ".github/workflows/commented.yml": (
                "jobs:\n  x:\n    steps:\n"
                "      - run: 'echo hi # pip install ruff'\n"
                "      - run: pip install ruff==0.15.8 && ruff check .\n"
            )
        }
    )
    assert module.main() == 0


def test_an_unterminated_quoted_scalar_is_reported_not_skipped(checker, capsys):
    """A quoted scalar spanning lines is one this reader cannot join.

    Left alone it fails OPEN: the shell-quote analysis sees an unclosed quote,
    treats everything after it as quoted, and an unpinned install inside
    becomes invisible. Reported instead, with the block-scalar form to use.
    """
    module = checker(
        files={
            ".github/workflows/multiline.yml": (
                "jobs:\n  x:\n    steps:\n"
                "      - run: 'pip install ruff\n"
                "          && ruff check .'\n"
            )
        }
    )
    assert module.main() == 1
    assert "quoted YAML scalar that does not close" in capsys.readouterr().err


def test_a_block_scalar_is_read_normally(checker):
    """`run: |` is the supported multi-line form and needs no special case."""
    module = checker(
        files={
            ".github/workflows/block.yml": (
                "jobs:\n  x:\n    steps:\n"
                "      - run: |\n"
                "          pip install ruff==0.15.8\n"
                "          ruff check .\n"
            )
        }
    )
    assert module.main() == 0
