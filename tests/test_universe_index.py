"""The Universe Index is derived, so the tests check the derivation.

It reports three owner rules (span, tier ceiling, three modes) without gating
on them -- those are Tier 0 decisions. What it must never do is go stale or
report Lead AI drift between registry.yaml and platform.py that nobody fixed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from build_universe_index import build  # noqa: E402


def test_index_is_current():
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_universe_index.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_lead_ai_drift_between_registers():
    """registry.yaml said Norman Hawkins led The Spark a month after the fix."""
    drift = build()["registry_drift"]
    assert drift == [], drift


def test_counts_cover_the_whole_estate():
    summary = build()["summary"]
    assert summary["locations"] == 43
    assert summary["named_ais"] >= 43


def test_span_breach_is_measured_not_hidden():
    """Every Location carries 2 Agents + 4 Bots today; the index must say so."""
    index = build()
    for loc in index["locations"]:
        span = loc["span"]
        assert span["conforms"] == (
            span["agents"] <= span["agents_allowed"] and span["bots"] <= span["bots_allowed"]
        )
