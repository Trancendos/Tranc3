"""Where this repository ends, every counting control must stop.

`ci.yml`'s Pytest job is the only one that checks out with
`submodules: recursive`. So before `src/immune/repo.py` existed, the
suppression ratchet, the bandit ratchet and the disposition-premise checker
all measured a larger tree in that one job than anywhere else — and the
ceilings recorded in a normal worktree failed there for a reason nobody's diff
had caused. Measured on #1403: `Pytest` red on `5a309946` while every other
job on the same commit, and `main`, were green.

Each case here plants a file where a submodule would be and asserts the
control ignores it. The boundary itself is derived from GITLINKS, so a
submodule added later is excluded without anyone remembering to -- and a
`.gitmodules` entry that is only a declaration excludes nothing. That second
half matters: reading the file alone let a change assert `path = src` and drop
every file under `src/` out of three ratchets at once (cubic, #1403), so the
fixtures below build real repositories with real gitlinks rather than writing
a text file and hoping.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from src.immune.repo import (
    declared_non_gitlinks,
    declared_paths,
    inside_submodule,
    submodule_paths,
    undeclared_gitlinks,
)

ROOT = Path(__file__).resolve().parents[1]


def _repo_with_gitlinks(root: Path, *paths: str, declare: bool = True) -> Path:
    """A real git repository with a real gitlink at each of `paths`.

    `git update-index --cacheinfo 160000` records a gitlink without needing an
    actual nested clone, which is exactly the structure `submodule_paths` reads
    and the thing a `.gitmodules` line cannot fake.
    """
    subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=30)
    for i, path in enumerate(paths):
        sha = f"{i + 1:040x}"
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{sha},{path}",
            ],
            check=True,
            timeout=30,
        )
    if declare:
        (root / ".gitmodules").write_text(
            "".join(
                f'[submodule "{path}"]\n\tpath = {path}\n\turl = https://example.invalid/{i}.git\n'
                for i, path in enumerate(paths)
            ),
            encoding="utf-8",
        )
    return root


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# --- the boundary itself ---------------------------------------------------


def test_this_repository_declares_its_submodules():
    """A fact about the tree, asserted so the tests below mean something."""
    assert submodule_paths(ROOT) == {"compliance/magna-carta", "workers/cranbania"}


def test_a_tree_with_no_gitmodules_excludes_nothing(tmp_path):
    """Empty is the right answer, not a guess at what might be a submodule."""
    assert submodule_paths(tmp_path) == frozenset()


def test_the_boundary_is_derived_not_hardcoded(tmp_path):
    _repo_with_gitlinks(tmp_path, "vendor/thing")
    assert submodule_paths(tmp_path) == {"vendor/thing"}


def test_a_declaration_with_no_gitlink_excludes_nothing(tmp_path):
    """THE EVASION. `.gitmodules` is repository content; a gitlink is
    repository structure. Reading the file alone meant a change could name
    `src` and remove it from the suppression ratchet, the bandit ceiling and
    the SEC-006/020/021 manifest scans in one line. Raised by cubic on #1403.
    """
    _repo_with_gitlinks(tmp_path, "vendor/real")
    (tmp_path / ".gitmodules").write_text(
        '[submodule "vendor/real"]\n\tpath = vendor/real\n\turl = https://example.invalid/0.git\n'
        '[submodule "fake"]\n\tpath = src\n\turl = https://example.invalid/fake.git\n',
        encoding="utf-8",
    )
    assert submodule_paths(tmp_path) == {"vendor/real"}
    assert inside_submodule("src/immune/repo.py", submodule_paths(tmp_path)) is False
    # Reported, not merely distrusted -- so the shape is visible to a reader.
    assert declared_non_gitlinks(tmp_path) == {"src"}
    assert declared_paths(tmp_path) == {"vendor/real", "src"}


def test_a_gitlink_with_no_declaration_is_still_a_boundary(tmp_path):
    """The other direction. Git records it, so it IS another repository; the
    missing entry is a defect `validate_submodule_pins.py` already fails on,
    not a reason to start counting its files here."""
    _repo_with_gitlinks(tmp_path, "vendor/thing", declare=False)
    assert submodule_paths(tmp_path) == {"vendor/thing"}
    assert undeclared_gitlinks(tmp_path) == {"vendor/thing"}


def test_a_tree_that_is_not_a_repository_excludes_nothing(tmp_path):
    """No gitlinks to read means no exclusions, never invented ones. A
    boundary that cannot be established must not become one."""
    (tmp_path / ".gitmodules").write_text(
        '[submodule "x"]\n\tpath = anything\n\turl = https://example.invalid/x.git\n',
        encoding="utf-8",
    )
    assert submodule_paths(tmp_path) == frozenset()
    assert declared_non_gitlinks(tmp_path) == frozenset()


def test_matching_is_segment_wise_not_a_string_prefix():
    """`workers/cranbania` must not swallow a sibling `workers/cranbania-notes`."""
    subs = frozenset({"workers/cranbania"})
    assert inside_submodule("workers/cranbania/app/x.py", subs)
    assert inside_submodule("workers/cranbania", subs)
    assert not inside_submodule("workers/cranbania-notes/x.py", subs)
    assert not inside_submodule("workers/other/x.py", subs)


# --- the controls that depend on it ----------------------------------------


def test_the_suppression_ratchet_ignores_a_submodule_file(tmp_path):
    """A suppression in CranBania is CranBania's to adjudicate."""
    cis = _load("cis_boundary", "scripts/check_inert_suppressions.py")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E", "F"]\n', encoding="utf-8"
    )
    # A real gitlink, not just a declaration: that is what the boundary reads.
    _repo_with_gitlinks(tmp_path, "workers/sub")
    (tmp_path / "mine.py").write_text("x = 1  # " + "no" + "qa: ABC001\n", encoding="utf-8")
    sub = tmp_path / "workers" / "sub"
    sub.mkdir(parents=True)
    (sub / "theirs.py").write_text("y = 2  # " + "no" + "qa: ABC002\n", encoding="utf-8")

    inert, _bare, _live, unreadable = cis.scan(tmp_path)
    assert unreadable == []
    shown = {s.path for s in inert}
    assert shown == {"mine.py"}, shown


def test_the_bandit_scope_guard_demands_every_submodule_be_excluded(tmp_path):
    """`[tool.bandit] exclude_dirs` and `.gitmodules` cannot be left to drift.

    `workers/cranbania` sits under the `workers` target, so an unexcluded
    submodule there is scanned into this repository's ceiling — in the one job
    that checks it out, and nowhere else.
    """
    cbc = _load("cbc_boundary", "scripts/check_bandit_coverage.py")
    # A real gitlink, not just a declaration: that is what the boundary reads.
    _repo_with_gitlinks(tmp_path, "workers/sub")
    problems = cbc.submodule_exclusions(tmp_path, ["src", "workers"], ["tests"])
    assert len(problems) == 1
    assert "workers/sub" in problems[0]

    assert cbc.submodule_exclusions(tmp_path, ["src", "workers"], ["tests", "workers/sub"]) == []
    # Outside every scanned target, so nothing to exclude.
    assert cbc.submodule_exclusions(tmp_path, ["src"], ["tests"]) == []


def test_the_real_bandit_config_excludes_every_submodule_under_a_target():
    """The live pair, so this cannot pass on synthetic input alone."""
    cbc = _load("cbc_boundary_real", "scripts/check_bandit_coverage.py")
    targets, excluded = cbc.configured_scope(ROOT / "pyproject.toml")
    assert cbc.submodule_exclusions(ROOT, targets, excluded) == []


def test_the_premise_checker_ignores_a_submodules_manifests(tmp_path, monkeypatch):
    """CranBania declaring `mcp` is not this repository declaring it.

    Without the boundary, SEC-006 and SEC-021 both reported
    `workers/cranbania/requirements.txt` and `workers/cranbania/pyproject.toml`
    as runtime declarations of nltk and mcp. Measured by disabling it.
    """
    cdp = _load("cdp_boundary", "scripts/check_disposition_premises.py")
    # A real gitlink, not just a declaration: that is what the boundary reads.
    _repo_with_gitlinks(tmp_path, "workers/sub")
    sub = tmp_path / "workers" / "sub"
    sub.mkdir(parents=True)
    (sub / "requirements.txt").write_text("mcp==1.29.0\nnltk==3.10.3\n", encoding="utf-8")
    (sub / "pyproject.toml").write_text(
        '[project]\nname = "sub"\ndependencies = ["mcp==1.30.0"]\n', encoding="utf-8"
    )
    (sub / "uses.py").write_text("import mcp\n", encoding="utf-8")

    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    cdp._boundary_reader.cache_clear()
    try:
        assert cdp._runtime_declarations("mcp") == []
        assert cdp._runtime_declarations("nltk") == []
        assert cdp._mcp_import_sites() == []
    finally:
        cdp._boundary_reader.cache_clear()


def test_the_premise_checker_still_sees_this_repositorys_own_files(tmp_path, monkeypatch):
    """The control. A boundary that hid everything would pass for free."""
    cdp = _load("cdp_boundary_control", "scripts/check_disposition_premises.py")
    # A real gitlink, not just a declaration: that is what the boundary reads.
    _repo_with_gitlinks(tmp_path, "workers/sub")
    (tmp_path / "requirements.txt").write_text("mcp==1.29.0\n", encoding="utf-8")
    (tmp_path / "ours.py").write_text("import mcp\n", encoding="utf-8")

    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    cdp._boundary_reader.cache_clear()
    try:
        assert cdp._runtime_declarations("mcp") == ["requirements.txt:1"]
        assert len(cdp._mcp_import_sites()) == 1
    finally:
        cdp._boundary_reader.cache_clear()
