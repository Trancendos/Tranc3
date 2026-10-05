"""A reviewer that did not review must not read as one that found nothing.

Every assertion here is against text or structure measured on this repository.
The tests marked REGRESSION pin behaviour the first version of this module got
wrong -- it called a greeting a review, and called a quoted banner blindness.
"""

from __future__ import annotations

from pathlib import Path

from src.immune.reviewers import (
    BLINDNESS_PHRASES,
    DEFAULT_MANIFEST,
    UNPUBLISHED_PHRASES,
    Remark,
    ReviewCoverage,
    Sight,
    assess,
    classify,
    load_manifest,
)

HEAD = "f2408ad889015aa705f596d7eddd85ca7867e201"
OLDER = "ba7258b90af61a807edc73d5c7fffa476afa67fe"

# Verbatim from comments measured on this repository, 2026-10-05.
CODERABBIT_LIMIT = "> [!WARNING]\n> ## Review limit reached\n> You've used all free OSS reviews."
DEVLO_CREDITS = 'Unable to trigger custom agent "Code Reviewer". You have run out of credits'
QODO_SUB = "Qodo reviews are paused because the subscription is no longer active."
ECC_UNPUBLISHED = "Security evidence gate passed. Check publication was denied or unavailable."
SOURCERY_GREETING = "🧙 Sourcery is reviewing your pull request!"
SOURCERY_REAL = "Hey - I've found 1 security issue, and 6 other issues"

DEPENDS = ("sourcery-ai[bot]", "coderabbitai[bot]")


def _review(who: str, body: str = SOURCERY_REAL, commit: str | None = HEAD) -> Remark:
    return Remark(who, body, "review", commit)


# --- Sight requires affirmative evidence -------------------------------------


def test_REGRESSION_a_progress_notice_is_not_a_review():
    """Sourcery's own greeting made a pull request read covered AND trustworthy.

    `classify` returned REVIEWED for any comment lacking a blindness phrase, so
    "Sourcery is reviewing your pull request!" counted as coverage -- the exact
    false-clean this module exists to prevent, inside the module.
    """
    verdict = classify("sourcery-ai[bot]", [Remark("sourcery-ai[bot]", SOURCERY_GREETING)], HEAD)
    assert verdict.sight is Sight.UNPROVEN
    assert not verdict.trustworthy


def test_REGRESSION_quoting_another_bots_banner_is_not_blindness():
    """A genuine review of THIS FILE quotes "review limit reached".

    Matching every phrase against every author classified that as BLIND.
    """
    body = 'I found a bug: the string "review limit reached" is matched too broadly'
    verdict = classify("sourcery-ai[bot]", [_review("sourcery-ai[bot]", body)], HEAD)
    assert verdict.sight is Sight.REVIEWED


def test_an_issue_comment_alone_never_proves_a_review():
    verdict = classify("sourcery-ai[bot]", [Remark("sourcery-ai[bot]", SOURCERY_REAL)], HEAD)
    assert verdict.sight is Sight.UNPROVEN, "an unanchored comment is not diff evidence"


def test_a_submitted_review_with_no_body_still_counts():
    """A reviewer can approve without commenting; that was recorded SILENT."""
    verdict = classify(
        "sourcery-ai[bot]", [Remark("sourcery-ai[bot]", "", "review", HEAD, "APPROVED")], HEAD
    )
    assert verdict.sight is Sight.REVIEWED


def test_an_inline_review_comment_counts_as_evidence():
    verdict = classify(
        "sourcery-ai[bot]", [Remark("sourcery-ai[bot]", "nit", "review_comment", HEAD)], HEAD
    )
    assert verdict.sight is Sight.REVIEWED


# --- Evidence is tied to the head it reviewed --------------------------------


def test_a_review_of_an_earlier_commit_is_stale_not_coverage():
    """Measured on #1372: codex reviewed ba7258b9, the head was f2408ad8."""
    verdict = classify("chatgpt-codex-connector[bot]", [_review("x", commit=OLDER)], HEAD)
    assert verdict.sight is Sight.STALE
    assert OLDER[:8] in verdict.evidence
    assert not verdict.trustworthy


def test_with_no_head_to_compare_review_evidence_is_not_called_stale():
    """Saying "stale" without knowing the head would be inventing a fact."""
    assert classify("x", [_review("x", commit=OLDER)], None).sight is Sight.REVIEWED


# --- Blindness binds to the reviewer that emits it ---------------------------


def test_the_three_measured_banners_read_blind_for_their_own_authors():
    for name, body in (
        ("coderabbitai[bot]", CODERABBIT_LIMIT),
        ("devloai[bot]", DEVLO_CREDITS),
        ("qodo-code-review[bot]", QODO_SUB),
    ):
        verdict = classify(name, [Remark(name, body)], HEAD)
        assert verdict.sight is Sight.BLIND, name
        assert verdict.evidence, "a blind verdict must name the phrase that decided it"


def test_a_banner_bound_to_another_reviewer_does_not_apply():
    verdict = classify("sourcery-ai[bot]", [Remark("sourcery-ai[bot]", CODERABBIT_LIMIT)], HEAD)
    assert verdict.sight is not Sight.BLIND


def test_a_later_successful_review_supersedes_an_earlier_quota_failure():
    """The verdict describes the current state, not the first thing that happened."""
    verdict = classify(
        "coderabbitai[bot]",
        [Remark("coderabbitai[bot]", CODERABBIT_LIMIT), _review("coderabbitai[bot]")],
        HEAD,
    )
    assert verdict.sight is Sight.REVIEWED


def test_findings_that_never_became_a_check_are_not_trustworthy():
    verdict = classify("ecc-tools[bot]", [Remark("ecc-tools[bot]", ECC_UNPUBLISHED)], HEAD)
    assert verdict.sight is Sight.UNPUBLISHED
    assert not verdict.trustworthy


def test_a_reviewer_that_posted_nothing_is_silent():
    assert classify("absent[bot]", [], HEAD).sight is Sight.SILENT


# --- Coverage is judged against a written decision ---------------------------


def test_all_reviewers_blind_is_uncovered_not_clean():
    coverage = assess(
        "#1372",
        [
            Remark("coderabbitai[bot]", CODERABBIT_LIMIT),
            Remark("devloai[bot]", DEVLO_CREDITS),
        ],
        expected=("coderabbitai[bot]", "devloai[bot]"),
        head=HEAD,
    )
    assert not coverage.covered
    assert "UNREVIEWED" in coverage.summary
    assert len(coverage.blind) == 2


def test_one_depended_on_reviewer_reviewing_the_head_is_enough():
    coverage = assess(
        "#1372",
        [Remark("coderabbitai[bot]", CODERABBIT_LIMIT), _review("sourcery-ai[bot]")],
        expected=DEPENDS,
        head=HEAD,
    )
    assert coverage.covered
    assert [v.reviewer for v in coverage.reviewed] == ["sourcery-ai[bot]"]


def test_a_merge_queue_checkbox_does_not_make_a_pull_request_reviewed():
    """The flaw the first live run exposed: mergify counted as review coverage."""
    coverage = assess(
        "#1372",
        [Remark("mergify[bot]", "Tick the box to add this pull request to the merge queue.")],
        expected=DEPENDS,
        head=HEAD,
        not_a_reviewer=("mergify[bot]",),
    )
    assert not coverage.covered
    assert not any(v.reviewer == "mergify[bot]" for v in coverage.verdicts), (
        "a declared non-reviewer should be absent from the verdicts, not merely "
        "absent from the arithmetic"
    )


def test_the_authors_own_replies_do_not_make_a_pull_request_reviewed():
    remarks = [Remark("Trancendos", "Confirmed and fixed.", "review_comment", HEAD)]
    assert not assess("#1372", remarks, expected=DEPENDS, head=HEAD, author="Trancendos").covered


def test_no_declared_reviewers_reads_undetermined():
    coverage = assess("#1372", [_review("sourcery-ai[bot]")], head=HEAD)
    assert not coverage.coverage_known
    assert not coverage.covered
    assert "UNDETERMINED" in coverage.summary


def test_uncollectable_evidence_reads_unknown_not_clean_and_not_unreviewed():
    """Rule one of this subsystem, applied to its own inputs."""
    coverage = assess("#1372", [], expected=DEPENDS, head=HEAD, collected=False)
    assert not coverage.coverage_known
    assert not coverage.covered
    assert "UNKNOWN" in coverage.summary


def test_an_empty_pull_request_is_uncovered():
    assert not ReviewCoverage(pr="#0").covered


# --- The manifest ------------------------------------------------------------


def test_the_default_manifest_path_does_not_depend_on_the_working_directory():
    assert DEFAULT_MANIFEST.is_absolute()
    assert DEFAULT_MANIFEST.is_file(), DEFAULT_MANIFEST


def test_the_shipped_manifest_declares_reviewers_and_separates_non_reviewers():
    depends_on, not_a_reviewer = load_manifest()
    assert "sourcery-ai[bot]" in depends_on
    assert "mergify[bot]" in not_a_reviewer
    assert not set(depends_on) & set(not_a_reviewer), "a bot cannot be both"


def test_a_missing_manifest_returns_nothing_rather_than_inventing_names():
    assert load_manifest(Path("config/immune/does-not-exist.yaml")) == ((), ())


def test_every_phrase_is_lowercase_so_matching_cannot_silently_miss():
    for phrase, source in BLINDNESS_PHRASES + UNPUBLISHED_PHRASES:
        assert phrase == phrase.lower(), phrase
        assert phrase.strip() == phrase, phrase
        assert source, "every phrase must name the reviewer that emits it, or 'generic'"


def test_the_manifests_stated_count_matches_its_own_list():
    """A number stated beside a list is the drift this estate guards against.

    This file said "of the five `depends_on` reviewers" against eight entries on
    the day it was written -- caught by `cubic-dev-ai` and `codeant-ai` on
    #1373, not by anything in the repository. Measured across CLAUDE.md the same
    afternoon: every count with a guard was right, every count without one had
    drifted. So this one gets a guard rather than a correction.
    """
    import re

    text = DEFAULT_MANIFEST.read_text()
    match = re.search(r"of the (\d+) `depends_on` reviewers", text)
    assert match, "the manifest must state how many reviewers it depends on"
    depends_on, _ = load_manifest()
    assert int(match.group(1)) == len(depends_on), (
        f"the manifest says {match.group(1)} depended-on reviewers but lists {len(depends_on)}"
    )


def test_on_request_reviewers_are_not_depended_on():
    """A reviewer whose declared default is "no review" cannot be one whose
    silence means something.

    Raised by `llamapreview[bot]` on #1373. Two entries annotated "Review on
    request" sat in `depends_on`, which guaranteed they would read SILENT or
    UNPROVEN on every pull request nobody summoned them to -- reported as a
    coverage gap that is not one.
    """
    import yaml

    data = yaml.safe_load(DEFAULT_MANIFEST.read_text())
    depends_on = set(data.get("depends_on") or ())
    on_request = set(data.get("on_request") or ())
    not_a_reviewer = set(data.get("not_a_reviewer") or ())
    assert on_request, "the on-request group should not be empty while such bots are installed"
    assert not depends_on & on_request, "a reviewer cannot be both depended on and on-request"
    assert not depends_on & not_a_reviewer
    assert not on_request & not_a_reviewer
