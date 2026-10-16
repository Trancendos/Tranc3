"""The App register must be a usable document, and must not overclaim.

Installed GitHub Apps were the fourth class of control in this estate and the
only one with no register. Measured 2026-10-16: 22 Apps act on this
repository, 11 of them publishing commit checks, and four of those eleven were
named in no document in the tree -- including `gitguardian` (secret scanning)
and `debricked` (software composition analysis), both of which
`IMMUNE-SYSTEM.md` requires be read about before adding.

The tests that matter most here are not the format ones. They are the two that
pin what this checker must NEVER say: that an offline validation proves the
register complete, and that a row may be satisfied by restating its own name.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("cai", REPO / "scripts" / "check_app_inventory.py")
assert _SPEC and _SPEC.loader
cai = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cai)

GOOD_ROW = {
    "slug": "example-scanner",
    "does": "Scans the diff and publishes a check-run.",
    "publishes_checks": True,
    "opens_prs": False,
    "decision": "keep",
    "reason": "Measured catching two real findings on #1376 that nothing else saw.",
    "reviewed_on": "2026-10-16",
}


def _row(**kw):
    row = dict(GOOD_ROW)
    row.update(kw)
    return row


# ---------------------------------------------------------------------------
# The two properties this checker must never violate.
# ---------------------------------------------------------------------------


def test_measuring_without_a_token_reports_unknown_and_fails(capsys, monkeypatch):
    """REGRESSION, and the whole reason this file exists.

    A register validated offline is well-formed, never complete. If this
    reported PASSED without having looked, the checker would be an instance of
    the exact defect it was built to catch -- a control reporting a result it
    never measured.
    """
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    code = cai.main(["--measure"])
    out = capsys.readouterr().out
    assert code == 1, "no token must not exit 0"
    assert "UNKNOWN" in out
    assert "PASSED" not in out


def test_a_reason_that_restates_the_slug_is_not_a_reason():
    """A row has to say something its own name does not."""
    assert any("restates" in d for d in cai.row_defects(_row(reason="example-scanner")))
    for empty in ("", "n/a", "TBD", "see above", "none"):
        assert cai.row_defects(_row(reason=empty)), empty


# ---------------------------------------------------------------------------
# A row is a usable entry, or it is reported.
# ---------------------------------------------------------------------------


def test_a_well_formed_row_has_no_defects():
    assert cai.row_defects(GOOD_ROW) == []


def test_a_row_must_say_what_the_app_does():
    assert any("does" in d for d in cai.row_defects(_row(does="")))


def test_a_row_must_carry_a_decision_from_the_fixed_set():
    assert any("decision" in d for d in cai.row_defects(_row(decision="maybe")))
    assert any("decision" in d for d in cai.row_defects(_row(decision="")))
    for allowed in cai.DECISIONS:
        assert cai.row_defects(_row(decision=allowed)) == [], allowed


def test_undecided_is_allowed_because_a_queue_is_not_a_failure():
    """Follows the Backlog Routing Register: an undecided count is a queue the
    estate owes an answer to, not a number to assign away by judgement. A
    register that forced a verdict on every row on day one would record its
    author's guesses as the estate's decisions."""
    assert cai.row_defects(_row(decision="undecided")) == []


def test_a_row_must_carry_a_parseable_review_date():
    assert any("reviewed_on" in d for d in cai.row_defects(_row(reviewed_on="")))
    assert any("reviewed_on" in d for d in cai.row_defects(_row(reviewed_on="last Tuesday")))


def test_the_capability_flags_must_be_booleans_not_truthy_strings():
    """`publishes_checks: "no"` is truthy in Python and would read as "this can
    gate a merge" -- the single most consequential field in the register."""
    assert any("publishes_checks" in d for d in cai.row_defects(_row(publishes_checks="no")))
    assert any("opens_prs" in d for d in cai.row_defects(_row(opens_prs=None)))


# ---------------------------------------------------------------------------
# The register file itself.
# ---------------------------------------------------------------------------


def test_the_real_register_validates():
    assert cai.main([]) == 0


def test_a_missing_register_fails_rather_than_passing_vacuously(tmp_path, capsys):
    code = cai.main(["--register", str(tmp_path / "nope.yaml")])
    assert code == 1
    assert "missing" in capsys.readouterr().out


def test_a_register_with_no_apps_list_fails(tmp_path, capsys):
    p = tmp_path / "r.yaml"
    p.write_text("something_else: []\n", encoding="utf-8")
    assert cai.main(["--register", str(p)]) == 1
    assert "`apps:`" in capsys.readouterr().out


def test_a_duplicated_slug_is_reported(tmp_path, capsys):
    p = tmp_path / "r.yaml"
    p.write_text(yaml.safe_dump({"apps": [GOOD_ROW, dict(GOOD_ROW)]}), encoding="utf-8")
    assert cai.main(["--register", str(p)]) == 1
    assert "listed 2 times" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# What the register records about this estate, pinned so it cannot quietly rot.
# ---------------------------------------------------------------------------


def test_every_app_that_publishes_checks_is_marked_as_such():
    """The four Apps this register was created for. Each publishes a commit
    check -- which means each can in principle gate a merge -- and each was
    named in no document in this repository until now."""
    rows = {
        str(r["slug"]): r for r in yaml.safe_load(cai.REGISTER.read_text(encoding="utf-8"))["apps"]
    }
    for slug in ("debricked", "gitguardian", "codefactor-io", "mermaid-diagram-sync-assistant"):
        assert slug in rows, f"{slug} must be registered"
        assert rows[slug]["publishes_checks"] is True, slug


def test_mergify_is_registered_as_able_to_merge():
    """The highest-authority App here. Its row carries the measured finding
    that its auto-merge conditions name the Production merge gate zero times."""
    rows = {
        str(r["slug"]): r for r in yaml.safe_load(cai.REGISTER.read_text(encoding="utf-8"))["apps"]
    }
    assert "mergify" in rows
    assert "Production merge gate" in rows["mergify"]["reason"]


def test_socket_security_is_recorded_as_the_honest_sensor():
    """It declined to report when it blew its scan limit, which is
    IMMUNE-SYSTEM.md's founding rule obeyed by a vendor unprompted. Worth
    pinning so the next reader does not mistake its silence for a gap."""
    rows = {
        str(r["slug"]): r for r in yaml.safe_load(cai.REGISTER.read_text(encoding="utf-8"))["apps"]
    }
    assert rows["socket-security"]["decision"] == "keep"
    assert "cannot see" in rows["socket-security"]["reason"]


@pytest.mark.parametrize("flag", ["publishes_checks", "opens_prs"])
def test_no_registered_row_omits_a_capability_flag(flag):
    for row in yaml.safe_load(cai.REGISTER.read_text(encoding="utf-8"))["apps"]:
        assert isinstance(row.get(flag), bool), f"{row.get('slug')} has no {flag}"


# ---------------------------------------------------------------------------
# The fetch guard, probed rather than asserted.
#
# `_api` carries a `# nosec B310` suppression. That suppression is only honest
# if the check it points at actually refuses something, so these two tests are
# the probe for it -- the same discipline IMMUNE-SYSTEM.md requires of a
# sensor. A guard nothing ever tested is indistinguishable from a comment.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base",
    [
        "file:///etc",
        "http://api.github.com",
        "https://api.github.com.example.invalid",
        "https://evil.invalid",
    ],
)
def test_the_fetch_guard_refuses_anything_but_the_github_api_over_https(base, monkeypatch):
    """`file://` is the one that matters: `urlopen` follows it happily, and it
    reads local files with whatever the process can read."""
    monkeypatch.setattr(cai, "GITHUB_API", base)
    with pytest.raises(ValueError, match="not the GitHub API"):
        cai._api("/passwd", "token")


def test_a_bot_login_normalises_to_its_app_slug():
    """GitHub names the same App two ways; the register holds one row."""
    assert cai._bot_slug("coderabbitai[bot]") == "coderabbitai"
    assert cai._bot_slug("victicnor") == ""
    assert cai._bot_slug("") == ""
