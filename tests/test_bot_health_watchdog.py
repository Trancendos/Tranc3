# tests/test_bot_health_watchdog.py
# Nothing previously detected a CI review-bot integration silently failing —
# Kilo Code Review's billing lapse this session is the concrete example: a
# dangling "action_required" status with a "could not run — out of credits"
# message on every PR, and nothing distinguished it from a one-off flake.
# These tests cover the pure detection logic in scripts/bot_health_watchdog.py
# (no network — fetch_recent_pr_check_runs is exercised separately, if at all,
# since it requires live GitHub API access).

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "bot_health_watchdog", Path(__file__).parent.parent / "scripts" / "bot_health_watchdog.py"
)
watchdog = importlib.util.module_from_spec(_SPEC)
sys.modules["bot_health_watchdog"] = watchdog
_SPEC.loader.exec_module(watchdog)

CheckRunResult = watchdog.CheckRunResult


def _kilo(pr_number: int, degraded: bool) -> CheckRunResult:
    if degraded:
        return CheckRunResult(
            pr_number=pr_number,
            name="Kilo Code Review",
            conclusion="action_required",
            summary_text="Kilo Code Review could not run — your account is out of credits",
        )
    return CheckRunResult(
        pr_number=pr_number,
        name="Kilo Code Review",
        conclusion="success",
        summary_text="No issues found",
    )


class TestIsDegradedForBot:
    def test_healthy_conclusion_is_never_degraded_even_with_matching_text(self):
        result = CheckRunResult(
            pr_number=1,
            name="Kilo Code Review",
            conclusion="success",
            summary_text="mentions credits and billing in passing",
        )
        assert watchdog._is_degraded_for_bot("Kilo Code Review", result) is False

    def test_action_required_with_known_phrase_is_degraded(self):
        result = _kilo(1, degraded=True)
        assert watchdog._is_degraded_for_bot("Kilo Code Review", result) is True

    def test_action_required_without_known_phrase_is_not_degraded(self):
        """A generic action_required (e.g. a real review comment needing a
        response) must not be confused with a broken integration."""
        result = CheckRunResult(
            pr_number=1,
            name="Kilo Code Review",
            conclusion="action_required",
            summary_text="3 suggestions require your attention",
        )
        assert watchdog._is_degraded_for_bot("Kilo Code Review", result) is False

    def test_case_insensitive_phrase_match(self):
        result = CheckRunResult(
            pr_number=1,
            name="Kilo Code Review",
            conclusion="failure",
            summary_text="OUT OF CREDITS — upgrade your plan",
        )
        assert watchdog._is_degraded_for_bot("Kilo Code Review", result) is True


class TestDetectDegradedBots:
    def test_below_threshold_streak_is_not_flagged(self):
        results_by_pr = [[_kilo(3, degraded=True)], [_kilo(2, degraded=True)]]
        findings = watchdog.detect_degraded_bots(results_by_pr, threshold=3)
        assert findings == []

    def test_at_threshold_consecutive_streak_is_flagged(self):
        results_by_pr = [
            [_kilo(5, degraded=True)],
            [_kilo(4, degraded=True)],
            [_kilo(3, degraded=True)],
        ]
        findings = watchdog.detect_degraded_bots(results_by_pr, threshold=3)
        assert len(findings) == 1
        assert findings[0].bot_name == "Kilo Code Review"
        assert findings[0].consecutive_degraded_prs == [5, 4, 3]

    def test_a_healthy_pr_in_the_middle_breaks_the_streak(self):
        """The core 'persistent, not just frequent' semantic: a recovery
        anywhere in the window resets the count, even if the bot was
        degraded before and after it."""
        results_by_pr = [
            [_kilo(5, degraded=True)],
            [_kilo(4, degraded=True)],
            [_kilo(3, degraded=False)],  # recovered here
            [_kilo(2, degraded=True)],
            [_kilo(1, degraded=True)],
        ]
        findings = watchdog.detect_degraded_bots(results_by_pr, threshold=3)
        assert findings == []

    def test_bot_absent_from_a_pr_does_not_break_the_streak(self):
        """A bot that simply didn't run on some PR (e.g. draft PR, path
        filter) is not evidence of health OR degradation — it should be
        skipped, not treated as a recovery."""
        results_by_pr = [
            [_kilo(4, degraded=True)],
            [],  # Kilo didn't run on PR #3 at all
            [_kilo(2, degraded=True)],
            [_kilo(1, degraded=True)],
        ]
        findings = watchdog.detect_degraded_bots(results_by_pr, threshold=3)
        assert len(findings) == 1
        assert findings[0].consecutive_degraded_prs == [4, 2, 1]

    def test_no_data_yields_no_findings(self):
        assert watchdog.detect_degraded_bots([], threshold=3) == []

    def test_healthy_bot_never_flagged(self):
        results_by_pr = [[_kilo(n, degraded=False)] for n in (5, 4, 3, 2, 1)]
        assert watchdog.detect_degraded_bots(results_by_pr, threshold=3) == []
