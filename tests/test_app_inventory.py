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


# ---------------------------------------------------------------------------
# Fixes from review. The first is the one that matters: five independent
# reviewers found that --measure could print PASSED while partially blind,
# which is the single outcome this script exists to make impossible.
# ---------------------------------------------------------------------------


def test_a_partial_measurement_is_unknown_not_complete(monkeypatch, capsys):
    """REGRESSION. Every per-PR fetch used to swallow `URLError` and continue.
    `HTTPError` SUBCLASSES `URLError`, so a 403 or 429 dropped that PR's Apps,
    `unregistered` came back empty, and main printed PASSED -- a sensor that
    could not see, reporting clean."""
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setattr(cai, "observed_apps", lambda *a, **k: None)

    failures, unknown = cai._measure_against_github("o/r", [])
    assert unknown is True and failures == []
    assert "UNKNOWN" in capsys.readouterr().out

    # And the part that decides the build. Asserting only on the helper left
    # `main` free to compute `unknown_measure` and then ignore it: deleting its
    # `if unknown_measure: return 1` branch would keep this test green while
    # the script printed PASSED and exited 0 over a blind measurement -- the
    # one outcome it exists to prevent. Raised by cubic on #1403.
    code = cai.main(["--measure"])
    out = capsys.readouterr().out
    assert code == 1, "an UNKNOWN measurement must fail the build, not merely be printed"
    assert "UNKNOWN" in out
    assert "PASSED" not in out, "nothing may read as passing when the sensor could not see"


def test_a_rate_limited_fetch_makes_the_whole_observation_none(monkeypatch):
    """The propagation half: a 429 anywhere must reach `observed_apps`' caller
    as None rather than a smaller set."""
    import urllib.error

    def rate_limited(path, token):
        if "/pulls?" in path:
            return [{"number": 1, "user": {"login": "x"}, "head": {"sha": "abc"}}]
        raise urllib.error.HTTPError(path, 429, "rate limited", {}, None)

    monkeypatch.setattr(cai, "_api", rate_limited)
    assert cai.observed_apps("o/r", "token") is None


def test_review_only_apps_are_sampled_too(monkeypatch):
    """An App that posts ONLY inline review comments was invisible: the loop
    read `/issues/{n}/comments` and never `/pulls/{n}/comments`, which are
    separate GitHub resources. That omission fell exactly on the review bots
    this register exists to inventory."""
    seen_paths = []

    def fake(path, token):
        seen_paths.append(path)
        if "/pulls?" in path:
            return [{"number": 7, "user": {"login": "human"}, "head": {"sha": "s"}}]
        if "/pulls/7/comments" in path:
            return [{"user": {"login": "reviewonly[bot]"}}]
        if "/issues/7/comments" in path:
            return []
        return {"check_runs": []}

    monkeypatch.setattr(cai, "_api", fake)
    assert cai.observed_apps("o/r", "t") == {"reviewonly"}
    assert any("/pulls/7/comments" in p for p in seen_paths)


def test_a_non_mapping_row_is_reported_not_filtered_away(tmp_path, capsys):
    """A bare `- gitguardian` used to vanish from validation while the checker
    printed PASSED, and `--measure` then called that App unregistered."""
    p = tmp_path / "r.yaml"
    p.write_text(yaml.safe_dump({"apps": [GOOD_ROW, "gitguardian", None]}), encoding="utf-8")
    assert cai.main(["--register", str(p)]) == 1
    out = capsys.readouterr().out
    assert "not a mapping" in out


def test_duplicate_keys_in_a_row_are_refused(tmp_path, capsys):
    """PyYAML keeps the LAST value for a repeated key, so a row with two
    `publishes_checks:` entries validated against whichever came second --
    the field that decides whether an App can gate a merge, silently
    discarded."""
    p = tmp_path / "r.yaml"
    p.write_text(
        "apps:\n"
        "  - slug: x\n"
        "    does: a thing\n"
        "    publishes_checks: true\n"
        "    publishes_checks: false\n"
        "    opens_prs: false\n"
        "    decision: keep\n"
        "    reason: a written reason that is not the slug\n"
        '    reviewed_on: "2026-10-16"\n',
        encoding="utf-8",
    )
    assert cai.main(["--register", str(p)]) == 1
    assert "duplicate key" in capsys.readouterr().out


@pytest.mark.parametrize("field", ["slug", "does", "reason"])
def test_a_yaml_scalar_does_not_satisfy_a_text_field(field):
    """`does: true` stringifies to "True" -- a non-empty value that read as a
    written description."""
    assert any(field in d for d in cai.row_defects(_row(**{field: True})))
    assert any(field in d for d in cai.row_defects(_row(**{field: 42})))


def test_the_strict_loader_really_is_a_safe_loader():
    """The suppression on `yaml.load` claims this, so it must be checkable.
    B506 exists to stop arbitrary object instantiation; subclassing SafeLoader
    is what keeps that property while adding duplicate-key detection."""
    assert issubclass(cai._StrictLoader, yaml.SafeLoader)


# ---------------------------------------------------------------------------
# Reported by cubic on #1403. Replacing SafeLoader's mapping constructor
# dropped two things it does, and the error handler that boasted about
# catching HTTPError did not catch a response of the wrong shape.
# ---------------------------------------------------------------------------


def _load(document: str):
    import yaml

    # A bandit suppression rather than a ruff one: ruff does not select the S
    # family, so a ruff directive for S506 here silenced nothing and the
    # inert-suppression ratchet removed it -- which then surfaced the same rule
    # in CodeFactor, where it IS live. (Spelling that directive out in prose is
    # also how a file becomes its own subject: ruff parses it.) The rule is
    # a false positive either way: `_StrictLoader` subclasses `yaml.SafeLoader`
    # and refuses duplicate keys ON TOP of SafeLoader's behaviour rather than
    # relaxing anything. Same suppression, same reason, as the call in
    # scripts/check_app_inventory.py that this exercises.
    return yaml.load(  # nosec B506 - _StrictLoader subclasses yaml.SafeLoader
        document, Loader=cai._StrictLoader
    )


def test_a_merge_key_expands_and_an_explicit_value_wins():
    """`<<: *defaults` is legal YAML, and was being rejected as invalid.

    A checker refusing a legitimate register is worse than one too lenient: it
    blocks the fix. `flatten_mapping` prepends the merged pairs, so the
    explicit assignment lands last and overrides, exactly as YAML specifies --
    and overriding a default is the point of the construct, not a row with two
    answers.
    """
    loaded = _load(
        "defaults: &d\n  decision: keep\n  does: default\nrow:\n  <<: *d\n  does: mine\n"
    )
    assert loaded["row"] == {"decision": "keep", "does": "mine"}


def test_a_duplicate_key_the_row_actually_wrote_is_still_refused():
    """The control: merge support must not weaken the duplicate check."""
    import yaml

    with pytest.raises(yaml.constructor.ConstructorError, match="duplicate key"):
        _load("row:\n  slug: a\n  slug: b\n")


def test_an_unhashable_key_is_an_invalid_register_not_a_traceback():
    """`? [a, b]` is legal YAML and an illegal dict key.

    Membership-testing it raised a bare `TypeError` and ended the checker in a
    traceback, so a malformed register read as broken tooling.
    """
    import yaml

    with pytest.raises(yaml.constructor.ConstructorError, match="unhashable key"):
        _load("? [a, b]\n: value\n")


@pytest.mark.parametrize(
    "payload",
    [
        ["not-an-object"],
        [{"user": {"login": "x[bot]"}, "number": 1, "head": "deadbeef"}],
        [{"user": "x[bot]", "number": 1, "head": {"sha": "abc"}}],
    ],
    ids=["list-of-strings", "head-as-scalar", "user-as-scalar"],
)
def test_a_payload_of_the_wrong_shape_reports_unknown(monkeypatch, payload):
    """A decodable response that is not the documented shape is still a failure.

    It reached `.get` on a `str` and raised `AttributeError`, which escaped the
    handler. Same defect as the swallowed `HTTPError` wearing a different coat:
    the sample is incomplete, so the caller must hear UNKNOWN.
    """
    monkeypatch.setattr(cai, "_api", lambda path, token, **k: payload if "/pulls?" in path else [])
    assert cai.observed_apps("o/r", "tok", pulls=1) is None


def test_a_truncated_read_reports_unknown(monkeypatch):
    """`IncompleteRead` is an `HTTPException`, not a `URLError`."""
    import http.client

    def truncated(path, token, **kwargs):
        if "/pulls?" in path:
            return [{"number": 1, "user": {"login": "x[bot]"}, "head": {"sha": "abc"}}]
        raise http.client.IncompleteRead(b"partial")

    monkeypatch.setattr(cai, "_api", truncated)
    assert cai.observed_apps("o/r", "tok", pulls=1) is None


def test_a_well_formed_sample_still_observes_its_apps(monkeypatch):
    """The control. None of the above may turn a good sample into UNKNOWN."""
    monkeypatch.setattr(
        cai,
        "_api",
        lambda path, token, **k: (
            [{"user": {"login": "renovate[bot]"}, "number": 1, "head": {"sha": "abc"}}]
            if "/pulls?" in path
            else []
        ),
    )
    assert cai.observed_apps("o/r", "tok", pulls=1) == {"renovate"}
