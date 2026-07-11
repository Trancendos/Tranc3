# src/relations/registry.py
"""AI-to-AI Relationship Matrix + Activity Feed + Location Brochure.

Tracks:
  - A pairwise trust/relationship score between every pair of the platform's
    Lead AIs (`-100` fully blocked .. `+100` fully trusted), seeded from
    Job Description / Pillar proximity and nudged by recorded activity.
  - An append-only activity feed — "AI has tagged itself into a location",
    "AI is chatting to AI", "AI raided the bank", "AI helped repair a
    policy" — that both drives relationship nudges and feeds the
    per-Location "brochure" (visit stats, sentiment breakdown, highlights).

Identity scope (v1): the 39 canonical Lead AI names from
`src/entities/platform.py` (the same identity space the Role Assignment
Registry already uses). Agents/Bots aren't globally unique identities today
(e.g. every Location has its own "Agent Alpha") — the schema stores free-text
identity strings, so extending to namespaced Agent/Bot IDs (e.g.
"The Spark:Agent Alpha") later is a data-modelling choice, not a schema
change.

Redemption is structural, not policy: every score decays toward a
per-pair baseline over time when idle, and any positive interaction can
always move a score back up — there is no permanent lock, matching the
"AIs even when fully negative still have the chance to be redeemed" design
goal.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared_core.sanitize import sanitize_for_log
from src.entities.platform import PLATFORM_ENTITIES, get_job_description
from src.relations.personality import get_quirks

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/relations_registry.db")

# Score bounds and tuning
SCORE_MIN = -100.0
SCORE_MAX = 100.0
SAME_PILLAR_BASELINE = 25.0
DIFFERENT_PILLAR_BASELINE = 0.0
DECAY_HALF_LIFE_DAYS = 10.0  # ~10% of the way back to baseline per ~1.5 days
BASE_INTERACTION_DELTA = 5.0
BASE_ACTION_DELTA = 10.0

PERMISSION_TIERS = (
    (60.0, "trusted"),
    (20.0, "friendly"),
    (-20.0, "neutral"),
    (-60.0, "restricted"),
    (float("-inf"), "blocked"),
)

_LEAD_AIS: Dict[str, str] = {e.lead_ai: location for location, e in PLATFORM_ENTITIES.items()}


def permission_tier(score: float) -> str:
    for threshold, tier in PERMISSION_TIERS:
        if score >= threshold:
            return tier
    return "blocked"  # pragma: no cover — PERMISSION_TIERS always bottoms out at -inf


@dataclass
class RelationshipScore:
    ai_a: str
    ai_b: str
    score: float
    baseline: float
    tier: str
    interactions_count: int
    last_interaction_at: Optional[float]


@dataclass
class ActivityEvent:
    id: int
    ts: float
    actor_ai: str
    event_type: str
    location: Optional[str]
    target_ai: Optional[str]
    sentiment: str
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LocationBrochure:
    location: str
    pillar: str
    primary_function: str
    job_description: str
    current_resident: Optional[str]
    total_events: int
    unique_visitors: int
    sentiment_counts: Dict[str, int]
    top_visitors: List[Dict[str, Any]]
    recent_highlights: List[ActivityEvent]
    flavor_text: str


@dataclass
class Insight:
    kind: str
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)


def _pair_key(ai_a: str, ai_b: str) -> tuple[str, str]:
    return (ai_a, ai_b) if ai_a <= ai_b else (ai_b, ai_a)


def _baseline_for_pair(ai_a: str, ai_b: str) -> float:
    loc_a = _LEAD_AIS.get(ai_a)
    loc_b = _LEAD_AIS.get(ai_b)
    if loc_a is None or loc_b is None:
        return DIFFERENT_PILLAR_BASELINE
    entity_a = PLATFORM_ENTITIES.get(loc_a)
    entity_b = PLATFORM_ENTITIES.get(loc_b)
    if entity_a and entity_b and entity_a.pillar == entity_b.pillar:
        return SAME_PILLAR_BASELINE
    return DIFFERENT_PILLAR_BASELINE


def _decay_toward_baseline(stored_score: float, baseline: float, elapsed_days: float) -> float:
    """Exponential decay of `stored_score` toward `baseline` over `elapsed_days`."""
    if elapsed_days <= 0:
        return stored_score
    decay_factor = math.pow(0.5, elapsed_days / DECAY_HALF_LIFE_DAYS)
    return baseline + (stored_score - baseline) * decay_factor


def _clamp_score(score: float) -> float:
    return max(SCORE_MIN, min(SCORE_MAX, score))


class RelationsRegistry:
    """SQLite-backed AI-to-AI relationship matrix + activity feed."""

    def __init__(self, db_path: "str | Path" = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Guards both tables — activity recording can update a relationship
        # row in the same call, and FastAPI's threadpool (sync route
        # handlers) can invoke these concurrently. Reads and writes share
        # one connection (check_same_thread=False), so an unlocked reader
        # could observe an uncommitted write; every method (not just the
        # writers) takes this lock. It's an RLock, not a plain Lock, so
        # methods that call other locked methods internally (record_event ->
        # _apply_nudge -> get_relationship) don't deadlock on themselves.
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_relationships (
                ai_a TEXT NOT NULL,
                ai_b TEXT NOT NULL,
                score REAL NOT NULL,
                updated_at REAL NOT NULL,
                interactions_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (ai_a, ai_b)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                actor_ai TEXT NOT NULL,
                event_type TEXT NOT NULL,
                location TEXT,
                target_ai TEXT,
                sentiment TEXT NOT NULL DEFAULT 'neutral',
                summary TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_location ON activity_events(location)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_actor ON activity_events(actor_ai)"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON activity_events(ts)")
        self._conn.commit()

    # ------------------------------------------------------------------
    # Relationship matrix
    # ------------------------------------------------------------------

    def _row_to_score(self, ai_a: str, ai_b: str, row: Optional[sqlite3.Row]) -> RelationshipScore:
        baseline = _baseline_for_pair(ai_a, ai_b)
        if row is None:
            return RelationshipScore(
                ai_a=ai_a,
                ai_b=ai_b,
                score=baseline,
                baseline=baseline,
                tier=permission_tier(baseline),
                interactions_count=0,
                last_interaction_at=None,
            )
        elapsed_days = (time.time() - row["updated_at"]) / 86400.0
        effective = _clamp_score(_decay_toward_baseline(row["score"], baseline, elapsed_days))
        return RelationshipScore(
            ai_a=ai_a,
            ai_b=ai_b,
            score=effective,
            baseline=baseline,
            tier=permission_tier(effective),
            interactions_count=row["interactions_count"],
            last_interaction_at=row["updated_at"],
        )

    def get_relationship(self, ai_a: str, ai_b: str) -> RelationshipScore:
        key_a, key_b = _pair_key(ai_a, ai_b)
        with self._lock:
            cur = self._conn.execute(
                "SELECT score, updated_at, interactions_count FROM ai_relationships "
                "WHERE ai_a = ? AND ai_b = ?",
                (key_a, key_b),
            )
            row = cur.fetchone()
        return self._row_to_score(key_a, key_b, row)

    def list_relationships(self, ai: str) -> List[RelationshipScore]:
        """Every other known Lead AI's relationship to `ai`, baseline-only
        where no interaction has ever happened."""
        others = [name for name in _LEAD_AIS if name != ai]
        with self._lock:
            return sorted(
                (self.get_relationship(ai, other) for other in others),
                key=lambda r: r.score,
                reverse=True,
            )

    def _apply_nudge(self, ai_a: str, ai_b: str, delta: float, ts: float) -> None:
        """Caller must already hold self._lock."""
        key_a, key_b = _pair_key(ai_a, ai_b)
        current = self.get_relationship(key_a, key_b)
        new_score = _clamp_score(current.score + delta)
        self._conn.execute(
            "INSERT INTO ai_relationships (ai_a, ai_b, score, updated_at, interactions_count) "
            "VALUES (?, ?, ?, ?, 1) "
            "ON CONFLICT(ai_a, ai_b) DO UPDATE SET "
            "score = excluded.score, updated_at = excluded.updated_at, "
            "interactions_count = interactions_count + 1",
            (key_a, key_b, new_score, ts),
        )

    # ------------------------------------------------------------------
    # Activity feed
    # ------------------------------------------------------------------

    def record_event(
        self,
        actor_ai: str,
        event_type: str,
        location: Optional[str] = None,
        target_ai: Optional[str] = None,
        sentiment: str = "neutral",
        summary: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> ActivityEvent:
        """Record one activity-feed entry. If it's an `ai_interaction` with a
        `target_ai`, also nudges that pair's relationship score."""
        if sentiment not in ("positive", "neutral", "negative"):
            raise ValueError(f"invalid sentiment: {sentiment!r}")
        ts = time.time()
        details = details or {}
        # Serialize before mutating anything — if `details` isn't
        # JSON-serializable (a set, a datetime, ...), fail here rather than
        # after the relationship nudge below has already been applied and
        # committed, which would otherwise leave an orphaned score update
        # with no matching activity_events row.
        details_json = json.dumps(details)
        with self._lock:
            if event_type == "ai_interaction" and target_ai:
                if sentiment != "neutral":
                    quirks_a = get_quirks(actor_ai)
                    quirks_b = get_quirks(target_ai)
                    if sentiment == "positive":
                        delta = (
                            BASE_INTERACTION_DELTA
                            * (quirks_a.positivity_multiplier + quirks_b.positivity_multiplier)
                            / 2
                        )
                    else:
                        delta = -(
                            BASE_INTERACTION_DELTA
                            * (quirks_a.negativity_multiplier + quirks_b.negativity_multiplier)
                            / 2
                        )
                    self._apply_nudge(actor_ai, target_ai, delta, ts)

            cur = self._conn.execute(
                "INSERT INTO activity_events "
                "(ts, actor_ai, event_type, location, target_ai, sentiment, summary, details_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ts,
                    actor_ai,
                    event_type,
                    location,
                    target_ai,
                    sentiment,
                    summary,
                    details_json,
                ),
            )
            self._conn.commit()
            event_id = cur.lastrowid

        return ActivityEvent(
            id=event_id,
            ts=ts,
            actor_ai=actor_ai,
            event_type=event_type,
            location=location,
            target_ai=target_ai,
            sentiment=sentiment,
            summary=summary,
            details=details,
        )

    def _row_to_event(self, row: sqlite3.Row) -> ActivityEvent:
        try:
            details = json.loads(row["details_json"])
        except (TypeError, json.JSONDecodeError):
            details = {}
        return ActivityEvent(
            id=row["id"],
            ts=row["ts"],
            actor_ai=row["actor_ai"],
            event_type=row["event_type"],
            location=row["location"],
            target_ai=row["target_ai"],
            sentiment=row["sentiment"],
            summary=row["summary"],
            details=details,
        )

    def get_feed(
        self,
        ai: Optional[str] = None,
        location: Optional[str] = None,
        since_ts: Optional[float] = None,
        limit: int = 50,
    ) -> List[ActivityEvent]:
        # SQLite treats a negative LIMIT as "no limit" — this is a public
        # method on a singleton also called internally by get_insights() and
        # get_location_brochure(), so it must enforce its own positive bound
        # rather than relying on callers (e.g. the HTTP route) to do it.
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit!r}")
        clauses = []
        params: List[Any] = []
        if ai:
            clauses.append("(actor_ai = ? OR target_ai = ?)")
            params.extend([ai, ai])
        if location:
            clauses.append("location = ?")
            params.append(location)
        if since_ts is not None:
            clauses.append("ts >= ?")
            params.append(since_ts)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._lock:
            cur = self._conn.execute(
                f"SELECT * FROM activity_events {where} ORDER BY ts DESC, id DESC LIMIT ?",
                params,
            )
            rows = cur.fetchall()
        return [self._row_to_event(row) for row in rows]

    # ------------------------------------------------------------------
    # Location brochure
    # ------------------------------------------------------------------

    def get_location_brochure(self, location: str) -> LocationBrochure:
        entity = PLATFORM_ENTITIES.get(location)
        if entity is None:
            raise KeyError(location)

        # Aggregate via SQL (COUNT/GROUP BY) rather than loading every event
        # for this Location into Python — activity_events is append-only, so
        # a busy Location's history only grows, and a fixed row cap here
        # would eventually under-report stats while still presenting them
        # as complete.
        sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
        visitor_counts: Dict[str, int] = {}
        with self._lock:
            sentiment_rows = self._conn.execute(
                "SELECT sentiment, COUNT(*) AS n FROM activity_events "
                "WHERE location = ? GROUP BY sentiment",
                (location,),
            ).fetchall()
            visitor_rows = self._conn.execute(
                "SELECT actor_ai, COUNT(*) AS n FROM activity_events "
                "WHERE location = ? GROUP BY actor_ai ORDER BY n DESC",
                (location,),
            ).fetchall()
        for row in sentiment_rows:
            sentiment_counts[row["sentiment"]] = row["n"]
        for row in visitor_rows:
            visitor_counts[row["actor_ai"]] = row["n"]

        top_visitors = [{"ai": row["actor_ai"], "visits": row["n"]} for row in visitor_rows[:5]]
        total_events = sum(sentiment_counts.values())
        recent_highlights = self.get_feed(location=location, limit=10)

        current_resident = None
        try:
            from src.roles.registry import get_registry as get_role_registry

            role = get_role_registry().get_role(location)
            current_resident = role.assigned_ai if role else None
        except ImportError:
            current_resident = None
        except Exception:
            # `location` is already an allowlisted PLATFORM_ENTITIES key by
            # this point (the method raises KeyError above otherwise), but
            # sanitize before logging anyway — defense-in-depth against log
            # injection (CWE-117) and a barrier CodeQL recognizes.
            logger.warning(
                "get_location_brochure: role registry lookup failed for %r",
                sanitize_for_log(location),
                exc_info=True,
            )
            current_resident = None

        job_description = get_job_description(location) or entity.primary_function
        quirks = get_quirks(current_resident) if current_resident else None
        if quirks and quirks.found:
            flavor_text = (
                f"Welcome to {location}, home of {job_description} {current_resident} — "
                f"{quirks.description or entity.primary_function}."
            )
        else:
            flavor_text = f"Welcome to {location}, home of {job_description} " + (
                f"{current_resident}." if current_resident else "— currently unstaffed."
            )

        return LocationBrochure(
            location=location,
            pillar=entity.pillar.value,
            primary_function=entity.primary_function,
            job_description=job_description,
            current_resident=current_resident,
            total_events=total_events,
            unique_visitors=len(visitor_counts),
            sentiment_counts=sentiment_counts,
            top_visitors=top_visitors,
            recent_highlights=recent_highlights,
            flavor_text=flavor_text,
        )

    # ------------------------------------------------------------------
    # Proactive insights
    # ------------------------------------------------------------------

    def get_insights(self, window_days: float = 7.0, limit: int = 10) -> List[Insight]:
        since_ts = time.time() - window_days * 86400.0
        insights: List[Insight] = []

        # Location-level aggregates via SQL GROUP BY — no row cap, so these
        # reflect the entire window regardless of how much activity it
        # contains, rather than an arbitrary "most recent N events" subset.
        with self._lock:
            location_rows = self._conn.execute(
                "SELECT location, COUNT(*) AS n FROM activity_events "
                "WHERE ts >= ? AND location IS NOT NULL GROUP BY location",
                (since_ts,),
            ).fetchall()
            negative_rows = self._conn.execute(
                "SELECT location, COUNT(*) AS n FROM activity_events "
                "WHERE ts >= ? AND location IS NOT NULL AND sentiment = 'negative' "
                "GROUP BY location",
                (since_ts,),
            ).fetchall()
            interaction_rows = self._conn.execute(
                "SELECT actor_ai, target_ai, sentiment FROM activity_events "
                "WHERE ts >= ? AND event_type = 'ai_interaction' AND target_ai IS NOT NULL",
                (since_ts,),
            ).fetchall()

        location_counts: Dict[str, int] = {row["location"]: row["n"] for row in location_rows}
        location_negative: Dict[str, int] = {row["location"]: row["n"] for row in negative_rows}
        pair_deltas: Dict[tuple[str, str], float] = {}
        for row in interaction_rows:
            key = _pair_key(row["actor_ai"], row["target_ai"])
            sign = (
                1
                if row["sentiment"] == "positive"
                else (-1 if row["sentiment"] == "negative" else 0)
            )
            pair_deltas[key] = pair_deltas.get(key, 0.0) + sign

        if location_counts:
            busiest = max(location_counts.items(), key=lambda kv: kv[1])
            insights.append(
                Insight(
                    kind="busiest_location",
                    summary=f"{busiest[0]} was the busiest Location this week ({busiest[1]} events).",
                    data={"location": busiest[0], "events": busiest[1]},
                )
            )

        flagged = [loc for loc, n in location_negative.items() if n >= 3]
        for loc in flagged[:3]:
            insights.append(
                Insight(
                    kind="negative_activity_spike",
                    summary=(
                        f"{loc} has seen {location_negative[loc]} negative-sentiment events "
                        f"this week — worth a look."
                    ),
                    data={"location": loc, "negative_events": location_negative[loc]},
                )
            )

        if pair_deltas:
            best_pair = max(pair_deltas.items(), key=lambda kv: kv[1])
            if best_pair[1] > 0:
                insights.append(
                    Insight(
                        kind="most_improved_relationship",
                        summary=(
                            f"{best_pair[0][0]} and {best_pair[0][1]} have had the most positive "
                            f"interactions this week."
                        ),
                        data={"pair": list(best_pair[0]), "net_positive_events": best_pair[1]},
                    )
                )
            worst_pair = min(pair_deltas.items(), key=lambda kv: kv[1])
            if worst_pair[1] < 0:
                insights.append(
                    Insight(
                        kind="deteriorating_relationship",
                        summary=(
                            f"{worst_pair[0][0]} and {worst_pair[0][1]} have had friction this week "
                            f"— but redemption is always possible."
                        ),
                        data={"pair": list(worst_pair[0]), "net_negative_events": worst_pair[1]},
                    )
                )

        # AIs closest to being blocked from the most locations right now.
        at_risk: List[tuple[str, int]] = []
        for ai in _LEAD_AIS:
            restricted_count = sum(
                1 for rel in self.list_relationships(ai) if rel.tier in ("restricted", "blocked")
            )
            if restricted_count >= 3:
                at_risk.append((ai, restricted_count))
        for ai, count in sorted(at_risk, key=lambda kv: kv[1], reverse=True)[:2]:
            insights.append(
                Insight(
                    kind="ai_at_risk",
                    summary=(
                        f"{ai} is restricted or blocked with {count} other AIs right now — "
                        f"positive interactions would help repair this."
                    ),
                    data={"ai": ai, "restricted_or_blocked_count": count},
                )
            )

        return insights[:limit]

    def close(self) -> None:
        self._conn.close()


_registry: Optional[RelationsRegistry] = None
_registry_lock = threading.Lock()


def get_relations_registry() -> RelationsRegistry:
    """Module-level singleton, matching the `get_<x>()` pattern used across
    this codebase (`get_registry()` for roles, `get_devocity()`, etc.)."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = RelationsRegistry()
    return _registry
