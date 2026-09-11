"""Tests for The Immune System.

These are calibration tests, not coverage tests. Each one plants the defect the
guard exists to catch and proves the guard fires -- and, where it matters, that
it stays quiet on the healthy case. A guard that cries wolf on working code
costs a gate its credibility as fast as a miss does, so both halves are
asserted.

Four of these encode defects that were real, in this code, on its first run.
They are marked REGRESSION and each says what the wrong behaviour looked like,
because the wrong behaviour in every case looked exactly like success.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from src.immune.grade import (
    DebtItem,
    blast_radius,
    grade,
    grade_for,
)
from src.immune.memory import (
    AUTOIMMUNE_THRESHOLD,
    Adjudication,
    apply_memory,
    load_baseline,
    split_by_baseline,
    split_unmeasured,
    write_baseline,
)
from src.immune.sarif import (
    Finding,
    SarifUnreadable,
    _relativise,
    dedupe,
    findings_from_sarif,
    load_sarif,
    merge,
    normalise_level,
)
from src.immune.sensors import Outcome, Sensor, parse_output, probe_sensor, run_sensor

# ── circulation: SARIF normalisation ─────────────────────────────────


def test_tool_severity_vocabularies_all_map_onto_sarif_levels():
    assert normalise_level("CRITICAL") == "error"
    assert normalise_level("High") == "error"
    assert normalise_level("moderate") == "warning"
    assert normalise_level("LOW") == "note"
    assert normalise_level("informational") == "note"
    # An unknown word must not silently become "none" and vanish from grading.
    assert normalise_level("wibble") == "warning"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("./src/a.py", "src/a.py"),
        ("file:///github/workspace/src/b.py", "src/b.py"),
        ("/app/src/c.py", "src/c.py"),
        ("src/d.py", "src/d.py"),
        ("././src/e.py", "src/e.py"),
        # REGRESSION: ruff always reports ABSOLUTE paths. Un-stripped, the
        # checkout prefix goes into the fingerprint, so a baseline written on a
        # laptop under /home/user/Tranc3 matches nothing on a runner under
        # /home/runner/work/Tranc3/Tranc3 and every finding reads as new -- a
        # gate that fails on every pull request for a reason nobody can see.
        # Found by planting a tangled function and reading the failure line.
        ("/home/runner/work/Tranc3/Tranc3/src/f.py", "src/f.py"),
        ("/build/Tranc3/scripts/g.py", "scripts/g.py"),
        # REGRESSION: and NOT by matching the directory name. The first fix cut
        # at the last segment equal to the checkout's own name, so it worked
        # only where the checkout happened to be called "Tranc3"; cubic flagged
        # it and proposed hardcoding that literal, which fails the same way for
        # a fork, a rename, or a vendored copy. Normalisation is now keyed on
        # top-level entries that actually exist in the tree, so these two cases
        # pass with the checkout under ANY name -- including a directory that
        # shares no name with the repository at all.
        (
            "/opt/some-fork-name/workers/storage-service/worker.py",
            "workers/storage-service/worker.py",
        ),
        ("/mnt/workspace/tests/test_immune.py", "tests/test_immune.py"),
    ],
)
def test_paths_from_every_tool_dialect_normalise_to_repo_relative(raw, expected):
    """REGRESSION: bandit reports './src/x.py'; git ls-files says 'src/x.py'.

    Before the converters normalised, findings attached to no graded file. The
    scan reported 13,712 findings AND a per-file distribution of all-A at the
    same time, because the two never met. The totals were right and the grade
    was meaningless, which is the worst of both.
    """
    assert _relativise(raw) == expected


def test_a_rule_level_severity_is_read_when_the_result_omits_one():
    document = {
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "t",
                        "rules": [{"id": "R1", "defaultConfiguration": {"level": "error"}}],
                    }
                },
                "results": [
                    {
                        "ruleId": "R1",
                        "message": {"text": "m"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "a.py"},
                                    "region": {"startLine": 3},
                                }
                            }
                        ],
                    }
                ],
            }
        ]
    }
    (finding,) = findings_from_sarif(document)
    assert finding.level == "error", "rule metadata carried the severity, not the result"


def test_codeql_shaped_sarif_reads_back_at_the_right_severity(tmp_path: Path):
    """CodeQL is the sensor this estate most needs to read and least can.

    Its SARIF is written to `sarif-results/` inside the job, uploaded to the
    Security tab, and discarded. "5 high / 14 medium" was reported on nine
    consecutive commits of one pull request without anyone -- human or agent --
    being able to say WHICH five. codeql.yml now retains the file as an
    artifact so it can be read by anything that reads SARIF.

    This asserts the shape actually round-trips: CodeQL puts severity on the
    RULE, not the result, so a reader that only looks at `result.level`
    silently grades every CodeQL finding at the fallback severity.
    """
    document = {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "CodeQL",
                        "rules": [
                            {
                                "id": "py/path-injection",
                                "defaultConfiguration": {"level": "error"},
                                "properties": {"security-severity": "7.5"},
                            }
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": "py/path-injection",
                        "message": {"text": "This path depends on a user-provided value."},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "src/example.py"},
                                    "region": {"startLine": 42},
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }
    path = tmp_path / "python.sarif"
    path.write_text(json.dumps(document), encoding="utf-8")
    (finding,) = load_sarif(path, tool_hint="codeql")
    assert finding.tool == "CodeQL"
    assert finding.rule_id == "py/path-injection"
    assert finding.level == "error", "severity lives on the rule, not the result"
    assert finding.located == "src/example.py:42"


def test_unreadable_sarif_raises_rather_than_reporting_zero_findings(tmp_path: Path):
    """An unreadable sensor output is not a clean scan.

    This is the whole thesis in one assertion: the failure mode that has to be
    impossible is 'we could not see' being recorded as 'there was nothing'.
    """
    for name, content in [
        ("empty.sarif", ""),
        ("notjson.sarif", "<html>proxy error</html>"),
        ("notsarif.sarif", json.dumps({"results": []})),
    ]:
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        with pytest.raises(SarifUnreadable):
            load_sarif(path)


def test_the_same_finding_from_two_sensors_is_counted_once():
    a = Finding("ruff", "X", "warning", "same", "a.py", 4)
    b = Finding("ruff", "X", "warning", "same", "a.py", 4)
    c = Finding("ruff", "X", "warning", "same", "a.py", 9)
    assert len(dedupe([a, b, c])) == 2, "same rule twice in one file is two findings"


def test_merged_sarif_keeps_one_run_per_tool_so_attribution_survives():
    report = merge(
        [
            ("ruff", [Finding("ruff", "F841", "warning", "m", "a.py", 1)]),
            ("bandit", [Finding("bandit", "B602", "error", "m", "b.py", 2)]),
        ]
    )
    document = report.to_sarif()
    names = {run["tool"]["driver"]["name"] for run in document["runs"]}
    assert names == {"ruff", "bandit"}
    assert document["version"] == "2.1.0"


# ── innate: sensors that report whether they could see ───────────────


def _liar(**overrides) -> Sensor:
    """A sensor that always reports clean, with a probe it cannot pass.

    This is the exact shape of `npm audit` against a soft registry failure:
    well-formed output, zero findings, exit 0, nothing anywhere saying the
    scan did not happen.
    """
    base = dict(
        name="liar",
        kind="innate",
        senses="nothing, dishonestly",
        command=["python3", "-c", "print('[]')"],
        fmt="ruff-json",
        binary="python3",
        required=True,
        probe={
            "file": "probe.py",
            "content": "def f():\n    x = 1\n    return 2\n",
            "expect_rule": "F841",
            "command": ["python3", "-c", "print('[]')"],
        },
    )
    base.update(overrides)
    return Sensor(**base)


def test_a_sensor_that_reports_clean_and_fails_its_probe_is_blind():
    result = run_sensor(_liar(), cwd=Path("."))
    assert result.outcome is Outcome.BLIND
    assert result.blocking, "a required sensor that cannot see must stop the run"


def test_without_a_probe_the_same_liar_is_indistinguishable_from_healthy():
    """The control case, and the reason probes exist at all.

    Identical command, identical output, identical exit code. Only the probed
    sensor is caught. Every commercial scanner this estate deleted was in this
    second state permanently.
    """
    result = run_sensor(_liar(probe={}), cwd=Path("."))
    assert result.outcome is Outcome.OK


def test_a_missing_tool_is_a_gap_not_a_clean_bill_of_health():
    sensor = Sensor(
        name="ghost",
        kind="innate",
        senses="x",
        command=["definitely-not-installed-anywhere"],
        binary="definitely-not-installed-anywhere",
        required=True,
    )
    result = run_sensor(sensor, cwd=Path("."))
    assert result.outcome is Outcome.ABSENT and result.blocking


def test_output_that_does_not_parse_is_a_failure_not_zero_findings():
    sensor = Sensor(
        name="garbage",
        kind="innate",
        senses="x",
        command=["python3", "-c", "print('not json')"],
        fmt="ruff-json",
        binary="python3",
        required=True,
    )
    result = run_sensor(sensor, cwd=Path("."))
    assert result.outcome is Outcome.UNREADABLE and result.blocking


def test_an_optional_sensor_that_cannot_see_is_recorded_but_does_not_block():
    result = run_sensor(_liar(required=False), cwd=Path("."))
    assert result.outcome is Outcome.BLIND
    assert not result.blocking, "'we have no scanner for this' is a written decision"


def _seeing_sensor(findings_json: str, expect_rule: str = "F841") -> Sensor:
    """A sensor whose probe genuinely fires, built from python3 alone.

    The first version of these two tests invoked `ruff`. They passed here and
    failed in CI with "[Errno 2] No such file or directory: 'ruff'", because
    the Pytest job does not install it. That is this engagement's own defect
    class turning up in its own test suite: a check that depended on an
    environment fact it never declared, and whose failure said nothing about
    the property under test.

    The property is "a probe that fires proves the sensor can see". It does not
    need a real linter to state, and stating it with one made the assertion
    hostage to which tools a runner happens to carry. python3 is the one binary
    a Python test suite can assume.
    """
    return Sensor(
        name="seeing",
        kind="innate",
        senses="a planted defect",
        command=["python3", "-c", f"print({findings_json!r})"],
        fmt="ruff-json",
        binary="python3",
        probe={
            "file": "probe.py",
            "content": "def f():\n    unused_local = 1\n    return 2\n",
            "expect_rule": expect_rule,
            "command": ["python3", "-c", f"print({findings_json!r})"],
        },
    )


_ONE_F841 = json.dumps(
    [
        {
            "code": "F841",
            "filename": "probe.py",
            "message": "local variable assigned but never used",
            "location": {"row": 2},
            "end_location": {"row": 2},
        }
    ]
)


def test_a_sensor_whose_probe_fires_is_not_reported_as_blind():
    """The false-positive half, and it matters as much as the other.

    A probe that fails on a healthy sensor is worse than no probe: it teaches
    everyone to pass --no-probe, and then nothing is probed at all.
    """
    saw, detail = probe_sensor(_seeing_sensor(_ONE_F841))
    assert saw, detail
    assert "1 finding" in detail


def test_a_probe_that_fires_on_the_wrong_rule_does_not_count_as_seeing():
    """Finding *something* is not evidence of finding the planted thing.

    A sensor that flags an unrelated rule on the probe file has demonstrated it
    can produce output, not that it can detect the defect class it is claimed
    to cover.
    """
    saw, detail = probe_sensor(_seeing_sensor(_ONE_F841, expect_rule="B602"))
    assert not saw
    assert "B602" in detail and "F841" in detail


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not installed here")
def test_the_shipped_ruff_probe_fires_against_the_real_tool():
    """The integration half, skipped rather than faked when ruff is absent.

    The synthetic tests above hold the property; this one holds the claim that
    the manifest's *actual* ruff probe -- its content, its expect_rule, its
    command -- still matches what ruff does today. A rule renamed upstream
    would break this and nothing else.

    Skipped, not silently passed. A skip is visible in the pytest summary; a
    test that quietly does nothing is the anergy this whole subsystem exists to
    make impossible.
    """
    from src.immune.sensors import load_manifest

    ruff = next(s for s in load_manifest(Path("config/immune/sensors.yaml")) if s.name == "ruff")
    saw, detail = probe_sensor(ruff)
    assert saw, detail


def test_every_converter_normalises_its_paths():
    """REGRESSION: only the SARIF reader normalised paths at first."""
    cases = [
        (
            "ruff-json",
            json.dumps(
                [
                    {
                        "code": "F",
                        "filename": "./a.py",
                        "message": "m",
                        "location": {"row": 1},
                        "end_location": {"row": 1},
                    }
                ]
            ),
        ),
        (
            "bandit-json",
            json.dumps(
                {
                    "results": [
                        {
                            "test_id": "B1",
                            "filename": "./a.py",
                            "line_number": 1,
                            "issue_text": "m",
                            "issue_severity": "HIGH",
                        }
                    ]
                }
            ),
        ),
        (
            "gitleaks-json",
            json.dumps([{"RuleID": "g", "File": "./a.py", "StartLine": 1, "Description": "m"}]),
        ),
    ]
    for fmt, payload in cases:
        (finding,) = parse_output(payload, fmt, "t")
        assert finding.path == "a.py", f"{fmt} left its path un-normalised"


def test_a_leaked_credential_is_always_an_error_level_finding():
    """gitleaks has no severity field. Defaulting it to 'warning' would let a
    live key sit under a grading threshold."""
    payload = json.dumps(
        [{"RuleID": "aws-key", "File": "a.py", "StartLine": 1, "Description": "AWS key"}]
    )
    (finding,) = parse_output(payload, "gitleaks-json", "gitleaks")
    assert finding.level == "error"


# ── vitals: the grade, and what it must refuse to claim ──────────────


def test_grade_thresholds_are_monotonic():
    assert grade_for(0.0) == "A"
    assert grade_for(2.0) == "A"
    assert grade_for(2.1) == "B"
    assert grade_for(10.0) == "C"
    assert grade_for(50.0) == "F"


def test_a_grade_computed_with_a_blind_sensor_cannot_be_an_A(tmp_path: Path):
    """REGRESSION: the cap was keyed on `blind` alone, so a required sensor
    that FAILED still printed 'grade A'. Measured for real: bandit exited 2
    without scanning a file and the report read A (PROVISIONAL)."""
    source = tmp_path / "m.py"
    source.write_text("x = 1\n" * 100, encoding="utf-8")
    clean = grade([], tracked=["m.py"], repo_root=tmp_path)
    assert clean.grade == "A" and not clean.provisional

    for reason in ("bandit (blind)", "bandit (failed)", "bandit (absent)", "bandit (unreadable)"):
        capped = grade([], tracked=["m.py"], repo_root=tmp_path, unseeing=[reason])
        assert capped.grade == "C", f"{reason} must cap the grade"
        assert capped.provisional
        assert reason in capped.explain()


def test_findings_outside_the_graded_population_still_count():
    """Otherwise a change could be graded clean by touching only files the
    population happened to exclude."""
    report = grade(
        [Finding("t", "R", "error", "m", "not/in/population.py", 1)],
        tracked=[],
        repo_root=Path("."),
    )
    assert report.findings == 1 and report.weighted == 10.0


def test_tiny_files_are_graded_on_findings_not_density(tmp_path: Path):
    small = tmp_path / "tiny.py"
    small.write_text("x = 1\n", encoding="utf-8")
    report = grade(
        [Finding("t", "R", "note", "m", "tiny.py", 1)],
        tracked=["tiny.py"],
        repo_root=tmp_path,
    )
    # 1 note over 1 line would be 1000/KLOC and an instant F.
    assert report.files["tiny.py"].grade == "A"


def test_blast_radius_searches_the_whole_tree_not_only_the_ranked_files(tmp_path: Path):
    """REGRESSION: rank_debt passed only the files with findings, so nothing
    imported anything and the third factor of the priority formula was always
    zero. Every debt row read 'x 0 importers'."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "user.py").write_text("from pkg.target import VALUE\n", encoding="utf-8")
    ranked = ["pkg/target.py"]
    whole_tree = ["pkg/target.py", "pkg/user.py"]
    assert blast_radius(ranked, tmp_path)["pkg/target.py"] == 0
    assert blast_radius(ranked, tmp_path, searched=whole_tree)["pkg/target.py"] == 1


def test_debt_priority_never_collapses_to_zero_for_a_quiet_file():
    """A never-touched file nothing imports, with a live secret in it, is still
    a problem. The +1s in the formula are what keep it on the list."""
    item = DebtItem(path="a.py", grade="F", weighted=10.0, changes=0, importers=0)
    assert item.priority == 10.0


def test_distribution_and_worst_agree_with_the_per_file_grades(tmp_path: Path):
    (tmp_path / "good.py").write_text("x = 1\n" * 200, encoding="utf-8")
    (tmp_path / "bad.py").write_text("x = 1\n" * 100, encoding="utf-8")
    findings = [Finding("t", "R", "error", "m", "bad.py", n) for n in range(1, 6)]
    report = grade(findings, tracked=["good.py", "bad.py"], repo_root=tmp_path)
    assert report.distribution()["A"] == 1
    assert report.worst(1)[0].path == "bad.py"


# ── memory ───────────────────────────────────────────────────────────


def test_an_empty_baseline_makes_everything_known_not_everything_new():
    """Otherwise the first pull request to run would be blamed for the whole
    pre-existing backlog."""
    findings = [Finding("t", "R", "warning", "m", f"{i}.py", 1) for i in range(5)]
    new, known = split_by_baseline(findings, set())
    assert new == [] and len(known) == 5


def test_baseline_round_trips_and_only_new_findings_are_new(tmp_path: Path):
    old = [Finding("t", "R", "warning", "m", "a.py", 1)]
    fresh = Finding("t", "R2", "error", "m2", "b.py", 1)
    path = tmp_path / "baseline.json"
    write_baseline(old, path, commit="deadbeef", sensors=["t"])
    baseline = load_baseline(path)
    new, known = split_by_baseline(old + [fresh], baseline)
    assert [f.rule_id for f in new] == ["R2"]
    assert [f.rule_id for f in known] == ["R"]


def test_a_finding_appearing_more_often_than_the_baseline_records_is_new(tmp_path: Path):
    """The fingerprint excludes the line number so findings survive code moving.

    That stability has a cost: three instances of one rule in one file collapse
    to a single baseline entry, and a fourth would not read as new. Counting
    occurrences keeps the stability and closes the hole.
    """
    once = [Finding("t", "R", "warning", "m", "a.py", 10)]
    path = tmp_path / "baseline.json"
    write_baseline(once, path, sensors=["t"])
    baseline = load_baseline(path)
    assert baseline[once[0].fingerprint] == 1

    twice = once + [Finding("t", "R", "warning", "m", "a.py", 99)]
    new, known = split_by_baseline(twice, baseline)
    assert len(new) == 1 and len(known) == 1

    # And the same single finding, moved down the file, is still not new.
    moved = [Finding("t", "R", "warning", "m", "a.py", 400)]
    new, known = split_by_baseline(moved, baseline)
    assert new == [] and len(known) == 1


def test_a_list_shaped_baseline_from_an_older_run_still_gates(tmp_path: Path):
    """Reading it as empty would turn the gate off without saying so."""
    path = tmp_path / "baseline.json"
    finding = Finding("t", "R", "warning", "m", "a.py", 1)
    path.write_text(json.dumps({"fingerprints": [finding.fingerprint]}), encoding="utf-8")
    baseline = load_baseline(path)
    assert baseline == {finding.fingerprint: 1}


def test_findings_from_a_sensor_the_baseline_never_ran_are_not_gated():
    """A newly installed scanner's first findings are a first measurement, not
    a regression. Gating on them blames the next pull request for whatever the
    new instrument happens to notice."""
    known_sensor = Finding("ruff", "F841", "warning", "m", "a.py", 1, sensor="ruff")
    new_sensor = Finding("Trivy", "CVE-1", "error", "m", "b.py", 1, sensor="trivy-fs")
    measured, unmeasured = split_unmeasured([known_sensor, new_sensor], {"ruff"})
    assert measured == [known_sensor]
    assert unmeasured == [new_sensor]


def test_with_no_recorded_sensor_list_everything_is_treated_as_measured():
    findings = [Finding("t", "R", "warning", "m", "a.py", 1)]
    measured, unmeasured = split_unmeasured(findings, set())
    assert measured == findings and unmeasured == []


def test_renaming_a_tool_does_not_orphan_its_baseline_entries():
    """`sensor` is excluded from the fingerprint on purpose: a vendor renaming
    its SARIF driver must not make a whole sensor's findings look newly found."""
    before = Finding("semgrep", "R", "warning", "m", "a.py", 1, sensor="semgrep")
    after = Finding("semgrep", "R", "warning", "m", "a.py", 1, sensor="semgrep-oss")
    assert before.fingerprint == after.fingerprint


def test_a_fingerprint_survives_the_code_moving_down_the_file():
    """Memory keyed on the line number is memory that forgets on every unrelated
    edit above the finding."""
    a = Finding("t", "R", "warning", "m", "a.py", 10)
    b = Finding("t", "R", "warning", "m", "a.py", 340)
    assert a.fingerprint == b.fingerprint


def test_an_adjudication_with_no_review_date_is_reported_as_expired():
    adj = Adjudication(rule_id="R", reason="r", decided_by="me")
    assert adj.expired()
    assert "no review_by date -- suppresses forever" in " ".join(adj.defects())


def test_an_adjudication_missing_provenance_is_reported_as_malformed():
    bare = Adjudication(rule_id="R")
    problems = bare.defects()
    assert "no written reason" in problems
    assert "nobody named as deciding it" in problems


def test_a_well_formed_adjudication_is_silent():
    good = Adjudication(
        rule_id="R",
        path="a.py",
        reason="checked, benign",
        decided_by="owner",
        decided_on="2026-09-10",
        review_by="2099-01-01",
    )
    assert good.defects() == []
    assert not good.expired(date(2026, 9, 10))


def test_an_adjudication_pointing_at_a_deleted_file_is_reported_as_rotted(tmp_path: Path):
    """This is the .security_learning/suppress.json failure, generalised: that
    store carries entries keyed on /tmp/pytest-of-root/... directories that
    existed for one test run in May and can never exist again."""
    adj = Adjudication(
        rule_id="R",
        path="gone/forever.py",
        reason="r",
        decided_by="me",
        decided_on="2026-01-01",
        review_by="2099-01-01",
    )
    _, report = apply_memory([], [adj], repo_root=tmp_path)
    assert any("no longer exists" in why for _, why in report.rotted)


def test_a_rule_adjudicated_false_across_many_files_is_reported_as_autoimmune():
    """The lesson bandit taught on the first real run: 12,770 of 13,712 findings
    were B101 objecting to `assert` inside the test suite. Suppressing each
    instance treats the symptom; the rule is what is wrong."""
    adjudications = [
        Adjudication(
            rule_id="NOISY",
            path=f"f{i}.py",
            reason="r",
            decided_by="me",
            decided_on="2026-01-01",
            review_by="2099-01-01",
        )
        for i in range(AUTOIMMUNE_THRESHOLD)
    ]
    _, report = apply_memory([], adjudications, repo_root=Path("."))
    assert "NOISY" in report.autoimmune
    assert len(report.autoimmune["NOISY"]) == AUTOIMMUNE_THRESHOLD


def test_below_the_threshold_a_rule_is_not_called_autoimmune():
    adjudications = [
        Adjudication(
            rule_id="QUIET",
            path=f"f{i}.py",
            reason="r",
            decided_by="me",
            decided_on="2026-01-01",
            review_by="2099-01-01",
        )
        for i in range(AUTOIMMUNE_THRESHOLD - 1)
    ]
    _, report = apply_memory([], adjudications, repo_root=Path("."))
    assert report.autoimmune == {}


def test_an_adjudication_suppresses_only_what_it_names(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    adj = Adjudication(
        rule_id="R",
        path="a.py",
        reason="r",
        decided_by="me",
        decided_on="2026-01-01",
        review_by="2099-01-01",
    )
    findings = [
        Finding("t", "R", "warning", "m", "a.py", 1),  # suppressed
        Finding("t", "R", "warning", "m", "b.py", 1),  # different file
        Finding("t", "OTHER", "error", "m", "a.py", 1),  # different rule
    ]
    remaining, report = apply_memory(findings, [adj], repo_root=tmp_path)
    assert {f.rule_id for f in remaining} == {"R", "OTHER"}
    assert len(remaining) == 2 and len(report.suppressed) == 1


def test_a_rule_wide_adjudication_needs_no_path_but_still_needs_a_rule():
    """An adjudication with neither is a blanket suppression of everything."""
    assert not Adjudication(rule_id="").matches(Finding("t", "R", "warning", "m", "a.py", 1))
    assert Adjudication(rule_id="R").matches(Finding("t", "R", "warning", "m", "anywhere.py", 1))


def test_the_report_is_healthy_only_when_memory_itself_is_clean(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    good = Adjudication(
        rule_id="R",
        path="a.py",
        reason="r",
        decided_by="me",
        decided_on="2026-01-01",
        review_by="2099-01-01",
    )
    _, healthy = apply_memory(
        [Finding("t", "R", "warning", "m", "a.py", 1)], [good], repo_root=tmp_path
    )
    assert healthy.healthy
    _, sick = apply_memory([], [Adjudication(rule_id="R")], repo_root=tmp_path)
    assert not sick.healthy


# ── the manifest this estate actually ships ──────────────────────────


def test_the_shipped_manifest_parses_and_every_sensor_says_what_it_senses():
    from src.immune.sensors import load_manifest

    sensors = load_manifest(Path("config/immune/sensors.yaml"))
    assert sensors, "the manifest is the whole innate layer; an empty one is a hole"
    for sensor in sensors:
        assert sensor.senses.strip(), f"{sensor.name} does not say what it detects"
        assert sensor.command, f"{sensor.name} has no command"
        assert sensor.location.strip(), f"{sensor.name} names no owning Location"


def test_every_required_sensor_declares_a_probe_or_says_why_not():
    """A required sensor with no probe and no written reason is a control this
    estate trusts without evidence -- the defect class this work exists to close.
    """
    from src.immune.sensors import load_manifest

    raw = Path("config/immune/sensors.yaml").read_text(encoding="utf-8")
    for sensor in load_manifest(Path("config/immune/sensors.yaml")):
        if not sensor.required or sensor.probe:
            continue
        pytest.fail(f"{sensor.name} is required but declares no probe")
    # Optional sensors without probes must at least be explained in the file.
    assert "No probe:" in raw or "probe:" in raw
