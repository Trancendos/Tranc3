"""A reviewer out of credits must not read as a reviewer with nothing to say."""

from __future__ import annotations

from src.immune.reviewers import (
    BLINDNESS_PHRASES,
    UNPUBLISHED_PHRASES,
    ReviewCoverage,
    Sight,
    assess,
    classify,
)

# Verbatim from comments measured on this repository, 2026-10-05.
CODERABBIT_LIMIT = (
    "> [!WARNING]\n> ## Review limit reached\n> You've used all free OSS reviews for now."
)
DEVLO_CREDITS = 'Unable to trigger custom agent "Code Reviewer". You have run out of credits'
QODO_SUB = "Qodo reviews are paused because the subscription is no longer active."
ECC_UNPUBLISHED = (
    "**Security evidence gate passed** (success)\n\n"
    "Check publication was denied or unavailable. An app owner must enable Checks."
)
SOURCERY_REAL = "Hey - I've found 1 security issue, and 6 other issues"


def test_the_three_measured_banners_all_read_as_blind():
    for name, body in (
        ("coderabbitai[bot]", CODERABBIT_LIMIT),
        ("devloai[bot]", DEVLO_CREDITS),
        ("qodo-code-review[bot]", QODO_SUB),
    ):
        verdict = classify(name, [body])
        assert verdict.sight is Sight.BLIND, name
        assert verdict.evidence, "a blind verdict must name the phrase that decided it"
        assert not verdict.trustworthy


def test_a_real_review_reads_as_reviewed():
    verdict = classify("sourcery-ai[bot]", [SOURCERY_REAL])
    assert verdict.sight is Sight.REVIEWED
    assert verdict.trustworthy


def test_findings_that_never_became_a_check_are_not_trustworthy():
    """ecc-tools reaches findings and cannot publish them. Nothing enforces those."""
    verdict = classify("ecc-tools[bot]", [ECC_UNPUBLISHED])
    assert verdict.sight is Sight.UNPUBLISHED
    assert not verdict.trustworthy


def test_blindness_anywhere_beats_a_cheerful_template():
    """The measured bots post a greeting and a banner in the same breath.

    Scoring on the first comment would call them reviewed.
    """
    verdict = classify("coderabbitai[bot]", ["Thanks for using CodeRabbit!", CODERABBIT_LIMIT])
    assert verdict.sight is Sight.BLIND


def test_a_reviewer_that_posted_nothing_is_silent_not_reviewed():
    assert classify("absent[bot]", []).sight is Sight.SILENT
    assert not classify("absent[bot]", []).trustworthy


def test_an_expected_reviewer_that_never_posted_is_still_recorded():
    """Absence from the pull request is the hardest blindness to spot: no comment to read."""
    coverage = assess("#1", [("other[bot]", SOURCERY_REAL)], expected=["sourcery-ai[bot]"])
    silent = {v.reviewer for v in coverage.silent}
    assert "sourcery-ai[bot]" in silent


def test_all_reviewers_blind_is_uncovered_not_clean():
    """The defect this module exists for: this page looks exactly like a clean one."""
    coverage = assess(
        "#1372",
        [
            ("coderabbitai[bot]", CODERABBIT_LIMIT),
            ("devloai[bot]", DEVLO_CREDITS),
            ("qodo-code-review[bot]", QODO_SUB),
        ],
        expected=("coderabbitai[bot]", "devloai[bot]", "qodo-code-review[bot]"),
    )
    assert not coverage.covered
    assert "UNREVIEWED" in coverage.summary
    assert len(coverage.blind) == 3


def test_one_real_reviewer_covers_a_pull_request_the_others_were_blind_on():
    """Measured #1372: three bots blind, sourcery found five real defects."""
    coverage = assess(
        "#1372",
        [
            ("coderabbitai[bot]", CODERABBIT_LIMIT),
            ("devloai[bot]", DEVLO_CREDITS),
            ("qodo-code-review[bot]", QODO_SUB),
            ("sourcery-ai[bot]", SOURCERY_REAL),
        ],
        expected=(
            "coderabbitai[bot]",
            "devloai[bot]",
            "qodo-code-review[bot]",
            "sourcery-ai[bot]",
        ),
    )
    assert coverage.covered
    assert [v.reviewer for v in coverage.reviewed] == ["sourcery-ai[bot]"]
    assert len(coverage.blind) == 3


def test_an_empty_pull_request_is_uncovered_not_covered():
    assert not ReviewCoverage(pr="#0").covered


def test_every_phrase_is_lowercase_so_matching_cannot_silently_miss():
    """classify() lowercases the body; an uppercase pattern would match nothing."""
    for phrase, _source in BLINDNESS_PHRASES + UNPUBLISHED_PHRASES:
        assert phrase == phrase.lower(), phrase
        assert phrase.strip() == phrase, phrase


# --- Coverage is judged against a written decision, not against who commented ---

MERGIFY = "Tick the box to add this pull request to the merge queue."
DEPENDS_ON = ("sourcery-ai[bot]", "coderabbitai[bot]")


def test_a_merge_queue_checkbox_does_not_make_a_pull_request_reviewed():
    """The flaw the first live run exposed: mergify counted as review coverage."""
    coverage = assess(
        "#1372",
        [("mergify[bot]", MERGIFY), ("coderabbitai[bot]", CODERABBIT_LIMIT)],
        expected=DEPENDS_ON,
    )
    assert not coverage.covered
    assert "UNREVIEWED" in coverage.summary


def test_the_authors_own_replies_do_not_make_a_pull_request_reviewed():
    """Replying to review threads on your own PR is not review coverage."""
    comments = [("Trancendos", "Confirmed and fixed in eb6ebcf7.")]
    assert not assess("#1372", comments, expected=DEPENDS_ON, author="Trancendos").covered
    # And without the exclusion the same data would have read as covered, which
    # is why `author` exists rather than being inferred.
    assert assess("#1372", comments, expected=("Trancendos",)).covered


def test_no_declared_reviewers_reads_undetermined_not_clean_and_not_broken():
    coverage = assess("#1372", [("sourcery-ai[bot]", SOURCERY_REAL)])
    assert not coverage.coverage_known
    assert not coverage.covered
    assert "UNDETERMINED" in coverage.summary


def test_one_depended_on_reviewer_reviewing_is_enough():
    coverage = assess(
        "#1372",
        [("coderabbitai[bot]", CODERABBIT_LIMIT), ("sourcery-ai[bot]", SOURCERY_REAL)],
        expected=DEPENDS_ON,
    )
    assert coverage.covered
    assert [v.reviewer for v in coverage.blind] == ["coderabbitai[bot]"]


def test_the_shipped_manifest_declares_reviewers_and_separates_non_reviewers():
    """A manifest that declared nothing would make every verdict UNDETERMINED."""
    from pathlib import Path

    from src.immune.reviewers import load_manifest

    depends_on, not_a_reviewer = load_manifest(Path("config/immune/reviewers.yaml"))
    assert "sourcery-ai[bot]" in depends_on
    assert "mergify[bot]" in not_a_reviewer
    assert not set(depends_on) & set(not_a_reviewer), "a bot cannot be both"


def test_a_missing_manifest_returns_nothing_rather_than_inventing_names():
    from pathlib import Path

    from src.immune.reviewers import load_manifest

    assert load_manifest(Path("config/immune/does-not-exist.yaml")) == ((), ())
