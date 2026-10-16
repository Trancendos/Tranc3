"""One ratchet, and the two rules that make it worth having.

This estate arrived at the same mechanism three times -- bandit suppressions
with no reason, suppressions that silence nothing, and bandit findings on the
newly-covered surface. The semantics pinned here are what those three must
agree on, and the two that look wrong at first are the two that matter:

* **A FALL fails.** If falling quietly passed, the gap between the real count
  and the recorded ceiling would be room for a new item nobody sees.
* **An unrecorded ceiling is UNKNOWN, not zero.** Zero reads as "nothing is
  wrong" and would fail every pull request at once.
"""

from __future__ import annotations

from src.immune.ratchet import UNRECORDED, compare, describe, read_ceiling, write_ceiling

REQUIRE = ("medium_plus", "low")


# ---------------------------------------------------------------------------
# Reading. Every case here would otherwise become a silent pass.
# ---------------------------------------------------------------------------


def test_a_missing_file_is_unrecorded_not_zero(tmp_path):
    assert read_ceiling(tmp_path / "absent.txt", require=REQUIRE) == UNRECORDED


def test_a_half_written_ceiling_is_unrecorded(tmp_path):
    """REGRESSION: a file with one of two required keys compared today's count
    against nothing. Half a ceiling is not a ceiling."""
    p = tmp_path / "c.txt"
    p.write_text("medium_plus=5\n", encoding="utf-8")
    assert read_ceiling(p, require=REQUIRE) == UNRECORDED


def test_a_non_numeric_value_is_unrecorded_rather_than_skipped(tmp_path):
    """Skipping the bad line would silently narrow what is ratcheted."""
    p = tmp_path / "c.txt"
    p.write_text("medium_plus=five\nlow=1\n", encoding="utf-8")
    assert read_ceiling(p, require=REQUIRE) == UNRECORDED


def test_comments_and_blank_lines_are_ignored(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("# why this exists\n\nmedium_plus=81\nlow=189\n", encoding="utf-8")
    assert read_ceiling(p, require=REQUIRE) == {"medium_plus": 81, "low": 189}


def test_a_json_object_is_accepted_for_a_per_rule_breakdown(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('{"medium_plus": 3, "low": 4}', encoding="utf-8")
    assert read_ceiling(p, require=REQUIRE) == {"medium_plus": 3, "low": 4}


def test_a_boolean_is_not_an_integer_count(tmp_path):
    """`True` is an int in Python and would read as a ceiling of 1."""
    p = tmp_path / "c.json"
    p.write_text('{"medium_plus": true, "low": 4}', encoding="utf-8")
    assert read_ceiling(p, require=REQUIRE) == UNRECORDED


def test_malformed_json_is_unrecorded(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json", encoding="utf-8")
    assert read_ceiling(p, require=REQUIRE) == UNRECORDED


# ---------------------------------------------------------------------------
# Comparing.
# ---------------------------------------------------------------------------


def test_holding_exactly_at_the_ceiling_is_the_only_pass():
    assert compare({"a": 5}, {"a": 5}, what="thing") == []


def test_a_rise_fails_and_says_what_to_do():
    problems = compare({"a": 6}, {"a": 5}, what="inert suppression")
    assert len(problems) == 1
    assert "ROSE" in problems[0] and "inert suppression" in problems[0]


def test_a_fall_also_fails_and_asks_for_the_ceiling_to_be_lowered():
    """The rule that looks wrong and is the point: a fall that passed silently
    would leave the gap as room for a new item nobody sees."""
    problems = compare({"a": 4}, {"a": 5}, what="thing")
    assert len(problems) == 1
    assert "FELL" in problems[0] and "--set-ceiling" in problems[0]


def test_a_count_with_no_ceiling_is_reported_rather_than_skipped():
    """Otherwise adding a new tracked count silently ratchets nothing."""
    problems = compare({"a": 1, "b": 2}, {"a": 1}, what="thing")
    assert len(problems) == 1 and "b: no ceiling recorded" in problems[0]


def test_an_empty_ceiling_fails_every_count():
    assert len(compare({"a": 1, "b": 2}, UNRECORDED, what="thing")) == 2


# ---------------------------------------------------------------------------
# Round trip.
# ---------------------------------------------------------------------------


def test_what_is_written_reads_back_identically(tmp_path):
    p = tmp_path / "nested" / "c.txt"
    write_ceiling(p, {"medium_plus": 81, "low": 189}, header="why\nthis exists")
    assert read_ceiling(p, require=REQUIRE) == {"medium_plus": 81, "low": 189}
    assert p.read_text(encoding="utf-8").startswith("# why")


def test_describe_marks_each_count_against_its_ceiling():
    out = describe({"a": 5, "b": 6, "c": 7}, {"a": 5, "b": 9})
    assert "=" in out.splitlines()[0]
    assert "v" in out.splitlines()[1]
    assert "—" in out.splitlines()[2], "a count with no ceiling must not read as holding"


# ---------------------------------------------------------------------------
# Reported by cubic on #1403. All three are the same mistake in three places:
# a ratchet that treats "could not read this" or "did not measure this" as
# "nothing to complain about" -- in the module written to stop exactly that.
# ---------------------------------------------------------------------------


def test_an_undecodable_ceiling_is_unrecorded_not_a_crash(tmp_path):
    """`UnicodeDecodeError` is a ValueError, so `except OSError` missed it.

    A ceiling with a stray byte ended the checker in a traceback, which CI
    reads as broken tooling rather than as an unestablished verdict.
    """
    path = tmp_path / "ceiling.txt"
    path.write_bytes(b"inert=1\nbare=\xff\xfe2\n")
    assert read_ceiling(path, require=("inert", "bare")) == UNRECORDED


def test_a_line_that_is_neither_comment_nor_setting_voids_the_ceiling(tmp_path):
    """There is no such thing as a partly-valid ceiling.

    Skipping unrecognised lines meant a file holding the required keys plus
    arbitrary other text still became usable, so a truncated write or a merge
    conflict marker could leave a ceiling that merely LOOKED recorded.
    """
    for content in (
        "inert=177\nbare=2\nthis line is not a setting\n",
        "<<<<<<< HEAD\ninert=177\nbare=2\n",
        "inert=177\nbare=2\n]}\n",
    ):
        path = tmp_path / "c.txt"
        path.write_text(content, encoding="utf-8")
        assert read_ceiling(path, require=("inert", "bare")) == UNRECORDED, content


def test_comments_and_blank_lines_are_still_a_valid_ceiling(tmp_path):
    """The control. Tightening the reader must not reject the real files."""
    path = tmp_path / "c.txt"
    path.write_text("# why this exists\n#\n\ninert=177\nbare=2\n", encoding="utf-8")
    assert read_ceiling(path, require=("inert", "bare")) == {"inert": 177, "bare": 2}


def test_a_ceiling_key_the_run_did_not_measure_fails():
    """REGRESSION, and the sharpest of the three.

    `compare` iterated `now` alone, so a count the ceiling records and the run
    did not produce simply vanished: no rise, no fall, no complaint. Dropping a
    measurement passed the ratchet while removing a suppression failed it. An
    absent count is `env_unchecked` from `docs/governance/DOMAIN-MODEL.md` --
    not zero, not passing, unknown.
    """
    problems = compare({"inert": 177}, {"inert": 177, "bare": 2}, what="suppression")
    assert len(problems) == 1
    assert problems[0].startswith("bare: ")
    assert "produced no value" in problems[0]


def test_the_three_outcomes_it_always_caught_are_unchanged():
    """The controls, so the new branch cannot be mistaken for a behaviour change."""
    assert compare({"inert": 177}, {"inert": 177}, what="x") == []
    assert "ROSE" in compare({"inert": 178}, {"inert": 177}, what="x")[0]
    assert "FELL" in compare({"inert": 176}, {"inert": 177}, what="x")[0]
    assert compare({"new": 1}, {}, what="x") == ["new: no ceiling recorded for this count"]
