"""A suppression that silences nothing must not read as an adjudication.

Every case here comes from the state this repository was measured in on
2026-10-16, when `[tool.ruff] select` was `["E", "F", "W", "C", "B", "I"]`
and 172 of its 803 suppression codes named rules ruff therefore never raised
-- 61 of them in the security family.

The finding that started it: `scripts/check_app_inventory.py` carried
`S310 - fixed host` on a urlopen call. The rule was not selected, so the
comment suppressed nothing; the reason was false, because the path appended
to the constant base URL is reachable from `--repo`; and no lane in the
estate could see either, since bandit excludes `scripts/` and skips B310
globally. CodeFactor caught it only because it runs bandit with its own
configuration.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "cis", REPO / "scripts" / "check_inert_suppressions.py"
)
assert _SPEC and _SPEC.loader
cis = importlib.util.module_from_spec(_SPEC)
# Registered BEFORE exec: the module defines a frozen dataclass, and
# `dataclasses` resolves field types through `sys.modules[cls.__module__]`.
# Loading it unregistered raises AttributeError on a None module.
sys.modules[_SPEC.name] = cis
_SPEC.loader.exec_module(cis)

TOKEN = "no" + "qa"  # written apart so this file is not its own subject
SELECT = ["E", "F", "W", "C", "B", "I"]
IGNORE = {"B008", "C901", "E501"}


# ---------------------------------------------------------------------------
# The classification this module exists for.
# ---------------------------------------------------------------------------


def test_the_security_family_is_inert_under_this_repositorys_select():
    """REGRESSION: the exact suppression that started this.

    S is not in `select`, so ruff cannot raise S310 and the comment claiming
    it was adjudicated silences nothing.
    """
    for code in ("S310", "S603", "S608", "S102", "S105"):
        assert cis.classify(code, SELECT, IGNORE) == cis.INERT_NOT_SELECTED, code


def test_a_globally_ignored_code_is_inert_even_though_its_family_is_selected():
    """`C` is selected and C901 is ignored, so a suppression naming C901
    silences nothing. pyproject.toml already records this lesson for C901
    itself -- "an `ignore` entry means ruff never runs the rule"."""
    assert cis.classify("C901", SELECT, IGNORE) == cis.INERT_IGNORED
    assert cis.classify("E501", SELECT, IGNORE) == cis.INERT_IGNORED
    assert cis.classify("B008", SELECT, IGNORE) == cis.INERT_IGNORED


def test_a_live_code_is_not_reported():
    """The other half: this must not become a way to flag every suppression."""
    for code in ("F401", "E402", "B904", "C416", "I001", "W605"):
        assert cis.classify(code, SELECT, IGNORE) == "", code


def test_select_all_makes_nothing_inert_except_an_explicit_ignore():
    assert cis.classify("S310", ["ALL"], set()) == ""
    assert cis.classify("S310", ["ALL"], {"S310"}) == cis.INERT_IGNORED


def test_a_narrower_select_beats_a_broader_ignore():
    """ruff ranks the two lists by specificity; it does not just prefer ignore.

    Probed against the installed ruff on a file holding one D205:
    `--select D205 --ignore D` reports "Found 1 error". A membership test
    called that suppression inert, which would have been an instruction to
    delete a comment that is doing its job.
    """
    assert cis.classify("D205", ["D205"], {"D"}) == ""
    assert cis.classify("S310", ["S310"], {"S"}) == ""


def test_a_narrower_ignore_beats_a_broader_select():
    """The other direction, same probe: `--select D --ignore D205` reports
    two errors and not the D205 one, so the suppression really is inert."""
    assert cis.classify("D205", ["D"], {"D205"}) == cis.INERT_IGNORED


def test_equal_specificity_goes_to_ignore():
    """`--select D205 --ignore D205` reports "All checks passed!"."""
    assert cis.classify("D205", ["D205"], {"D205"}) == cis.INERT_IGNORED


def test_a_per_file_ignore_outranks_any_select():
    """Per-file ignores are not ranked against `select` at all. Probed:
    per-file `["D"]` against `select = ["D205"]` passes cleanly, so the
    narrower select does NOT win here the way it does above."""
    assert cis.classify("D205", ["D205"], set(), frozenset({"D"})) == cis.INERT_IGNORED


def test_an_unreadable_pyproject_yields_no_select_rather_than_a_guess(tmp_path):
    """Failing closed here would mark every suppression in the tree inert.
    Returning an empty config is honest, and `scan` reports it as such."""
    assert cis.ruff_rule_config(tmp_path / "absent.toml") == ([], set(), {})
    bad = tmp_path / "pyproject.toml"
    bad.write_text("this is not = = toml", encoding="utf-8")
    assert cis.ruff_rule_config(bad) == ([], set(), {})


def test_the_newer_lint_table_is_read_as_well_as_the_legacy_top_level(tmp_path):
    """ruff accepts both and this repository still uses the older form.
    Reading only one would report on a configuration not in force."""
    legacy = tmp_path / "legacy.toml"
    legacy.write_text('[tool.ruff]\nselect = ["E"]\nignore = ["E501"]\n', encoding="utf-8")
    assert cis.ruff_rule_config(legacy) == (["E"], {"E501"}, {})
    modern = tmp_path / "modern.toml"
    modern.write_text('[tool.ruff.lint]\nselect = ["F"]\nignore = ["F401"]\n', encoding="utf-8")
    assert cis.ruff_rule_config(modern) == (["F"], {"F401"}, {})


def test_extend_select_counts_as_selected(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text('[tool.ruff.lint]\nselect = ["E"]\nextend-select = ["S"]\n', encoding="utf-8")
    select, _, _ = cis.ruff_rule_config(p)
    assert cis.classify("S310", select, set()) == ""


# ---------------------------------------------------------------------------
# Scanning a tree, and the planted-defect probe.
# ---------------------------------------------------------------------------


def _tree(tmp_path: Path, body: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff]\nselect = ["E", "F"]\nignore = ["E501"]\n', encoding="utf-8"
    )
    (tmp_path / "mod.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_a_planted_inert_suppression_is_found(tmp_path):
    """The probe. A guard that cannot see a defect it was built for reports
    exactly what a clean tree reports -- IMMUNE-SYSTEM.md's founding rule."""
    inert, bare, live, _ = cis.scan(_tree(tmp_path, f"x = 1  # {TOKEN}: S310 - fixed host\n"))
    assert [s.code for s in inert] == ["S310"]
    assert inert[0].inert is True
    assert bare == [] and live == 0


def test_a_planted_bare_directive_is_found(tmp_path):
    inert, bare, live, _ = cis.scan(_tree(tmp_path, f"x = 1  # {TOKEN}\n"))
    assert len(bare) == 1 and bare[0].endswith("mod.py:1")
    assert inert == [] and live == 0


def test_a_live_suppression_is_counted_live_not_inert(tmp_path):
    inert, bare, live, _ = cis.scan(_tree(tmp_path, f"import os  # {TOKEN}: F401\n"))
    assert live == 1 and inert == [] and bare == []


def test_several_codes_on_one_line_are_classified_separately(tmp_path):
    inert, _, live, _ = cis.scan(_tree(tmp_path, f"x = 1  # {TOKEN}: F401, S603, E501\n"))
    assert sorted(s.code for s in inert) == ["E501", "S603"]
    assert live == 1


def test_a_clean_tree_reports_nothing(tmp_path):
    inert, bare, live, _ = cis.scan(_tree(tmp_path, "x = 1\n"))
    assert (inert, bare, live) == ([], [], 0)


def test_vendored_directories_are_not_scanned(tmp_path):
    tree = _tree(tmp_path, "x = 1\n")
    vendored = tree / "node_modules" / "pkg"
    vendored.mkdir(parents=True)
    (vendored / "v.py").write_text(f"x = 1  # {TOKEN}: S310\n", encoding="utf-8")
    inert, _, _, _ = cis.scan(tree)
    assert inert == [], "a vendored suppression is not this repository's decision"


# ---------------------------------------------------------------------------
# The ratchet. Each of these would be a way to let the backlog grow.
# ---------------------------------------------------------------------------


def test_a_missing_ceiling_is_unknown_and_fails_rather_than_passing(tmp_path, capsys):
    """An unrecorded ceiling cannot tell a clean tree from an unmeasured one.
    This is `grade.py`'s rule and `check_app_inventory.py`'s, applied here."""
    tree = _tree(tmp_path, "x = 1\n")
    assert cis.main(["--root", str(tree)]) == 1
    out = capsys.readouterr().out
    assert "UNKNOWN" in out and "PASSED" not in out


def test_a_malformed_ceiling_reads_as_absent_not_as_zero(tmp_path):
    """Zeros would read as "nothing is wrong" and fail every pull request."""
    path = tmp_path / "noqa_ceiling.txt"
    path.write_text("inert=notanumber\n", encoding="utf-8")
    assert cis.read_ceiling(path) == {}
    path.write_text("inert=5\n", encoding="utf-8")
    assert cis.read_ceiling(path) == {}, "a half-recorded ceiling is not a ceiling"
    path.write_text("# comment\ninert=5\nbare=1\n", encoding="utf-8")
    assert cis.read_ceiling(path) == {"inert": 5, "bare": 1}


@pytest.mark.parametrize("body,expected", [("x = 1\n", "FELL"), (None, "ROSE")])
def test_the_ceiling_fails_in_both_directions(tmp_path, capsys, body, expected):
    """Rising hides a new unenforced claim. Falling without lowering the
    ceiling leaves room for one to be added back silently."""
    tree = _tree(tmp_path, body if body else f"x = 1  # {TOKEN}: S1\nz = 2  # {TOKEN}: S2\n")
    (tree / "config" / "immune").mkdir(parents=True)
    (tree / "config/immune/noqa_ceiling.txt").write_text("inert=1\nbare=0\n", encoding="utf-8")
    assert cis.main(["--root", str(tree)]) == 1
    assert expected in capsys.readouterr().out


def test_holding_at_the_ceiling_passes(tmp_path, capsys):
    tree = _tree(tmp_path, f"x = 1  # {TOKEN}: S310\n")
    (tree / "config" / "immune").mkdir(parents=True)
    (tree / "config/immune/noqa_ceiling.txt").write_text("inert=1\nbare=0\n", encoding="utf-8")
    assert cis.main(["--root", str(tree)]) == 0
    assert "PASSED" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# This repository, pinned so the finding cannot quietly rot.
# ---------------------------------------------------------------------------


def test_this_checker_is_not_part_of_its_own_subject():
    """It writes the directive token from parts for exactly this reason. If
    it ever contains one literally, ruff reads its source line as a real
    suppression and the count it reports includes itself."""
    inert, bare, _, _ = cis.scan(REPO)
    offenders = [s for s in inert if s.path.endswith("check_inert_suppressions.py")]
    assert offenders == [], f"the checker reported itself as inert: {offenders}"
    assert not [p for p in bare if "check_inert_suppressions.py" in p]

    # The precise property, which the earlier "no directive token anywhere"
    # assertion only approximated: the PATTERN must not be written as a single
    # literal. The file legitimately carries live E402 suppressions -- its
    # imports follow a sys.path insertion -- and those are counted live, which
    # is correct. What must never appear is the pattern itself spelled out,
    # because ruff would read that line as a directive and the count would
    # include its own source.
    source = (REPO / "scripts" / "check_inert_suppressions.py").read_text(encoding="utf-8")
    assert '_TOKEN = "no" + "qa"' in source, "the token must stay built from parts"
    assert f'r"#\\s*{TOKEN}' not in source, "the pattern must not be one literal"


def test_the_real_tree_holds_at_its_recorded_ceiling():
    assert cis.main([]) == 0


# ---------------------------------------------------------------------------
# Fixes from review, each with the defect it closes.
# ---------------------------------------------------------------------------


def test_a_directive_inside_a_string_literal_is_not_a_suppression(tmp_path):
    """REGRESSION: a raw-line scan counted this repository's own test fixtures
    and docstrings as real suppressions, so the instrument measured its own
    test data. Measured on tests/test_test_env_isolation.py:339."""
    tree = _tree(tmp_path, f'FIXTURE = "x = 1  # {TOKEN}: S310"\n')
    inert, bare, live, _ = cis.scan(tree)
    assert (inert, bare, live) == ([], [], 0), "a string is not a comment"


def test_a_per_file_ignored_code_is_inert_in_that_file(tmp_path):
    """`"tests/*" = ["B"]` means ruff never raises B008 there, so a directive
    naming it silences nothing. Without this a whole directory could collect
    inert suppressions under the ceiling. Measured on tests/test_cryptex.py:144."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E", "B"]\n'
        '[tool.ruff.lint.per-file-ignores]\n"tests/*" = ["B"]\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text(f"x = 1  # {TOKEN}: B008\n", encoding="utf-8")
    (tmp_path / "mod.py").write_text(f"x = 1  # {TOKEN}: B008\n", encoding="utf-8")
    inert, _, live, _ = cis.scan(tmp_path)
    assert [s.path for s in inert] == ["tests/t.py"], "only the ignored file is inert"
    assert live == 1, "the same code outside that scope is still live"


def test_an_unreadable_file_fails_rather_than_dropping_out(tmp_path, capsys, monkeypatch):
    """REGRESSION: an unreadable file was skipped with `continue`, so a file
    holding a new suppression could leave the measurement while the ceiling
    still held -- a gate passing on a count it never took."""
    tree = _tree(tmp_path, "x = 1\n")
    (tree / "config" / "immune").mkdir(parents=True)
    (tree / "config/immune/noqa_ceiling.txt").write_text("inert=0\nbare=0\n", encoding="utf-8")

    def boom(path):
        raise OSError("permission denied")

    monkeypatch.setattr(cis, "_comments", boom)
    assert cis.main(["--root", str(tree)]) == 1
    out = capsys.readouterr().out
    assert "UNKNOWN" in out and "could not be read" in out
