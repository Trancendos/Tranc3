"""Chaos Party → The Observatory forwarding, with local regression detection.

THE GAP THIS CLOSES

The Chaos Party recorded every test run into its own SQLite and stopped there.
Nothing forwarded them, so the pipeline downstream — Observatory trend analysis,
Basement evidence, Library article promotion, Think Tank study — had no input at
all. The design was sound and the first leg was missing, which meant every test
result the platform produced was discarded at the point of collection.

Observatory→Basement is already wired (`src/observability/observatory.py` calls
`get_basement().ingest_observatory_event`), so connecting this one leg makes the
whole chain carry data end to end.

SELF-CONTAINED BY NECESSITY

This worker's compose `build.context` is `./workers/chaos-party`, so `src/` is
not in the image and `from src.mesh...` would ImportError at container start.
The circuit breaker below is therefore a local implementation rather than an
import of `src/mesh/circuit_breaker.py` — same states and thresholds, duplicated
deliberately because the alternative is a worker that cannot boot.

FAIL-OPEN, ALWAYS

Forwarding must never fail a test run. If the Observatory is down, the run is
still recorded locally and the forward is dropped with a logged warning. A
testing platform that goes offline because its telemetry sink is unreachable is
worse than one with a gap in its trend data — it stops finding bugs.

WHY THE TREND IS COMPUTED HERE, NOT THERE

Chaos Party already holds the run history, so it can classify a result against
that history for the cost of one indexed query. Forwarding a bare pass/fail
makes the Observatory reconstruct context it does not have; forwarding
`{status, pass_rate, trend, regression}` lets it act on the first event rather
than after enough have accumulated to infer a baseline. The signal travels with
the observation.

The detection is deliberately simple statistics, not a model: a Wilson-style
comparison of the recent window against the prior baseline. It is explainable,
needs no training data, and cannot silently drift — properties that matter more
than sensitivity for something that gates human attention. `predicted_next_fail`
is a probability estimate from the recent window, not a claim about the future;
it is there to rank what a human looks at first.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("chaos-party.observatory-bridge")

OBSERVATORY_URL = os.getenv("AUDIT_SERVICE_URL", "http://audit-service:8025").rstrip("/")
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")
FORWARD_ENABLED = os.getenv("OBSERVATORY_FORWARD_ENABLED", "true").lower() in ("1", "true", "yes")
FORWARD_TIMEOUT = float(os.getenv("OBSERVATORY_FORWARD_TIMEOUT", "5"))

# Trend window sizes. 10/30 is small enough to react within a working day of
# runs and large enough that a single flake does not read as a regression.
RECENT_WINDOW = int(os.getenv("CHAOS_TREND_RECENT_WINDOW", "10"))
BASELINE_WINDOW = int(os.getenv("CHAOS_TREND_BASELINE_WINDOW", "30"))
# A drop this large between baseline and recent pass-rate is a regression.
REGRESSION_DROP = float(os.getenv("CHAOS_TREND_REGRESSION_DROP", "0.20"))


class _CircuitBreaker:
    """Closed → open → half-open, mirroring src/mesh/circuit_breaker.py.

    Duplicated rather than imported — see the module docstring on build context.
    Without it, an Observatory outage costs every single run an HTTP timeout,
    turning a telemetry problem into a throughput problem.
    """

    def __init__(self, threshold: int = 5, reset_after: float = 60.0) -> None:
        self._threshold = threshold
        self._reset_after = reset_after
        self._failures = 0
        self._opened_at: float | None = None

    def can_execute(self) -> bool:
        if self._opened_at is None:
            return True
        if time.time() - self._opened_at >= self._reset_after:
            return True  # half-open: allow one probe
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold and self._opened_at is None:
            self._opened_at = time.time()
            logger.warning(
                "Observatory forwarding circuit opened after %d failures; "
                "runs are still recorded locally",
                self._failures,
            )

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        return "half_open" if time.time() - self._opened_at >= self._reset_after else "open"


_breaker = _CircuitBreaker()


def _wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    """Lower bound of the 95% CI on a pass rate.

    Used instead of the raw rate so a small sample cannot look confident: 1/1
    passing is a raw rate of 1.0 but a lower bound near 0.21, which correctly
    refuses to claim health from one observation.
    """
    if total == 0:
        return 0.0
    phat = successes / total
    denom = 1 + z * z / total
    centre = phat + z * z / (2 * total)
    margin = z * ((phat * (1 - phat) / total + z * z / (4 * total * total)) ** 0.5)
    return max(0.0, (centre - margin) / denom)


def analyse_trend(conn: sqlite3.Connection, test_name: str) -> dict[str, Any]:
    """Classify a test's recent history against its own baseline.

    Returns a dict that always has the same keys, so downstream consumers never
    branch on presence. `trend` is one of: insufficient_data, stable,
    regression, recovering, chronic.
    """
    out: dict[str, Any] = {
        "trend": "insufficient_data",
        "recent_pass_rate": None,
        "baseline_pass_rate": None,
        "confidence_floor": None,
        "predicted_next_fail": None,
        "regression": False,
        "sample_size": 0,
    }
    try:
        rows = conn.execute(
            "SELECT status FROM test_runs WHERE name = ? ORDER BY id DESC LIMIT ?",
            (test_name, BASELINE_WINDOW + RECENT_WINDOW),
        ).fetchall()
    except sqlite3.Error as exc:  # table shape drift must not break recording
        logger.debug("trend query failed for %r: %s", test_name, exc)
        return out

    statuses = [(r[0] or "").lower() for r in rows]
    out["sample_size"] = len(statuses)
    if len(statuses) < RECENT_WINDOW:
        return out

    recent = statuses[:RECENT_WINDOW]
    baseline = statuses[RECENT_WINDOW:]

    # This worker's status vocabulary is pass/fail/skip/error — validated in
    # record_run — not the pytest-style "passed". Matching the wrong literal
    # would score a fully green suite at a 0% pass rate and report every test as
    # a chronic regression. Skips are excluded rather than counted as failures:
    # a skipped test is an absence of evidence, not evidence of a defect.
    def rate(seq: list[str]) -> float | None:
        scored = [s for s in seq if s in ("pass", "fail", "error")]
        return (sum(1 for s in scored if s == "pass") / len(scored)) if scored else None

    r_rate = rate(recent)
    b_rate = rate(baseline)
    out["recent_pass_rate"] = round(r_rate, 4) if r_rate is not None else None
    out["baseline_pass_rate"] = round(b_rate, 4) if b_rate is not None else None
    scored_recent = [s for s in recent if s in ("pass", "fail", "error")]
    out["confidence_floor"] = round(
        _wilson_lower_bound(sum(1 for s in scored_recent if s == "pass"), len(scored_recent)), 4
    )
    # Probability the next run fails, from the recent window only. An estimate
    # for ranking attention, not a forecast.
    out["predicted_next_fail"] = round(1.0 - (r_rate or 0.0), 4)

    if b_rate is None:
        out["trend"] = "stable" if (r_rate or 0) >= 0.9 else "chronic"
        return out

    delta = b_rate - (r_rate or 0.0)
    if delta >= REGRESSION_DROP:
        out["trend"] = "regression"
        out["regression"] = True
    elif delta <= -REGRESSION_DROP:
        out["trend"] = "recovering"
    elif (r_rate or 0.0) < 0.5 and b_rate < 0.5:
        # Never healthy in living memory — a standing defect, not a new one.
        out["trend"] = "chronic"
    else:
        out["trend"] = "stable"
    return out


def build_event(run: dict[str, Any], trend: dict[str, Any], lead_ai: str) -> dict[str, Any]:
    """Shape one run as an audit-service AuditEventIn-compatible entry."""
    status = (run.get("status") or "unknown").lower()
    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "chaos-party",
        "action": f"test.run.{status}",
        "actor": lead_ai,
        "resource": run.get("name") or "unknown",
        "metadata": {
            "pid": "PID-TCP",
            "suite_id": run.get("suite_id"),
            "duration_ms": run.get("duration_ms"),
            "error_msg": run.get("error_msg"),
            "ran_by": run.get("ran_by"),
            **{f"trend_{k}": v for k, v in trend.items()},
        },
    }


def lead_ai_for(run: dict[str, Any]) -> str:
    """Attribute a run to the Lead AI whose discipline it belongs to.

    The Chaos Party carries two: The Mad Hatter runs adversarial work, Alice
    Dream runs deterministic acceptance/regression/smoke. Attribution matters
    downstream — a failing chaos run is information, a failing deterministic run
    is a defect, and the Observatory should not have to guess which it received.
    """
    name = f"{run.get('name', '')} {run.get('ran_by', '')}".lower()
    adversarial = ("chaos", "fault", "inject", "fuzz", "adversar", "penetration", "boundary")
    if any(k in name for k in adversarial):
        return "The Mad Hatter"
    return "Alice Dream"


async def forward_runs(conn: sqlite3.Connection, runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Forward runs to The Observatory. Never raises — fail-open by contract."""
    result = {"forwarded": 0, "skipped": 0, "circuit": _breaker.state, "regressions": []}
    if not FORWARD_ENABLED or not runs:
        result["skipped"] = len(runs)
        return result
    if not _breaker.can_execute():
        result["skipped"] = len(runs)
        return result

    entries = []
    for run in runs:
        trend = analyse_trend(conn, run.get("name") or "")
        if trend.get("regression"):
            result["regressions"].append(
                {
                    "test": run.get("name"),
                    "baseline_pass_rate": trend["baseline_pass_rate"],
                    "recent_pass_rate": trend["recent_pass_rate"],
                }
            )
        entries.append(build_event(run, trend, lead_ai_for(run)))

    try:
        import httpx
    except ImportError:
        logger.warning("httpx unavailable — Observatory forwarding disabled this run")
        result["skipped"] = len(entries)
        return result

    headers = {"X-Internal-Secret": INTERNAL_SECRET, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=FORWARD_TIMEOUT) as client:
            resp = await client.post(
                f"{OBSERVATORY_URL}/audit/batch", json={"entries": entries}, headers=headers
            )
        if resp.status_code in (200, 201):
            _breaker.record_success()
            result["forwarded"] = len(entries)
        else:
            _breaker.record_failure()
            result["skipped"] = len(entries)
            logger.warning("Observatory rejected batch: HTTP %s", resp.status_code)
    except Exception as exc:  # noqa: BLE001 — fail-open is the whole point
        _breaker.record_failure()
        result["skipped"] = len(entries)
        logger.warning("Observatory forwarding failed (%s) — runs recorded locally", exc)

    result["circuit"] = _breaker.state
    return result
