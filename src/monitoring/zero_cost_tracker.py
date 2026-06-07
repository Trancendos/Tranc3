"""
Zero-Cost Usage Tracker — Free-Tier Consumption Monitor
========================================================
Tracks usage against free-tier limits for all platform dependencies
to prevent unexpected cost overruns.

Inspired by: the-observatory zeroCostOptimization.ts
Zero-cost: SQLite backend, no external dependencies.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.database.encrypted_sqlite import connect as sqlite3_connect

# ── Free-tier limit definitions ────────────────────────────────────────────────

FREE_TIER_LIMITS: dict[str, dict[str, float]] = {
    "fly_io": {
        "monthly_bandwidth_gb": 160.0,
        "shared_cpu_vms": 3.0,
        "volume_gb": 3.0,
    },
    "cloudflare_workers": {
        "daily_requests": 100_000.0,
        "cpu_ms_per_request": 10.0,
    },
    "upstash_redis": {
        "daily_commands": 10_000.0,
        "max_data_size_mb": 256.0,
    },
    "supabase": {
        "monthly_egress_gb": 5.0,
        "db_size_mb": 500.0,
        "monthly_api_calls": 500_000.0,
    },
    "github_actions": {
        "monthly_minutes": 2000.0,
    },
    "pinecone": {
        "vectors": 100_000.0,
        "namespaces": 1.0,
    },
}


# ── Data structures ────────────────────────────────────────────────────────────


@dataclass
class UsageRecord:
    service: str
    metric: str
    current_usage: float
    limit: float
    percentage_used: float
    reset_period: str  # e.g. "daily", "monthly", "none"
    last_updated: str


# ── Helpers ───────────────────────────────────────────────────────────────────

_RESET_PERIOD: dict[str, dict[str, str]] = {
    "fly_io": {
        "monthly_bandwidth_gb": "monthly",
        "shared_cpu_vms": "none",
        "volume_gb": "none",
    },
    "cloudflare_workers": {
        "daily_requests": "daily",
        "cpu_ms_per_request": "daily",
    },
    "upstash_redis": {
        "daily_commands": "daily",
        "max_data_size_mb": "none",
    },
    "supabase": {
        "monthly_egress_gb": "monthly",
        "db_size_mb": "none",
        "monthly_api_calls": "monthly",
    },
    "github_actions": {
        "monthly_minutes": "monthly",
    },
    "pinecone": {
        "vectors": "none",
        "namespaces": "none",
    },
}


def _ensure_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3_connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usage (
            service TEXT NOT NULL,
            metric  TEXT NOT NULL,
            value   REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (service, metric)
        )
        """
    )
    conn.commit()
    return conn


# ── Tracker ───────────────────────────────────────────────────────────────────


class ZeroCostTracker:
    """Tracks free-tier usage with SQLite persistence.

    Usage::

        tracker.record_usage("upstash_redis", "daily_commands", 1)
        alerts = tracker.check_alerts(threshold_pct=80.0)
    """

    def __init__(self, db_path: str = "data/zero_cost_usage.db") -> None:
        self._db = _ensure_db(Path(db_path))

    def record_usage(self, service: str, metric: str, value: float) -> None:
        """Add *value* to the current usage counter for (service, metric)."""
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """
            INSERT INTO usage (service, metric, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(service, metric) DO UPDATE SET
                value = value + excluded.value,
                updated_at = excluded.updated_at
            """,
            (service, metric, value, now),
        )
        self._db.commit()

    def set_usage(self, service: str, metric: str, value: float) -> None:
        """Set the absolute usage for (service, metric) — overwrite."""
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """
            INSERT INTO usage (service, metric, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(service, metric) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (service, metric, value, now),
        )
        self._db.commit()

    def _build_record(
        self, service: str, metric: str, current: float, updated_at: str
    ) -> UsageRecord:
        limit = FREE_TIER_LIMITS.get(service, {}).get(metric, 0.0)
        pct = (current / limit * 100) if limit > 0 else 0.0
        reset_period = _RESET_PERIOD.get(service, {}).get(metric, "unknown")
        return UsageRecord(
            service=service,
            metric=metric,
            current_usage=current,
            limit=limit,
            percentage_used=round(pct, 2),
            reset_period=reset_period,
            last_updated=updated_at,
        )

    def get_usage(self, service: str) -> list[UsageRecord]:
        """Return all tracked metrics for *service*."""
        rows = self._db.execute(
            "SELECT metric, value, updated_at FROM usage WHERE service = ?",
            (service,),
        ).fetchall()
        records = {row[0]: (row[1], row[2]) for row in rows}

        result: list[UsageRecord] = []
        for metric, _limit in FREE_TIER_LIMITS.get(service, {}).items():
            current, updated_at = records.get(metric, (0.0, "never"))
            result.append(self._build_record(service, metric, current, updated_at))
        return result

    def get_all_usage(self) -> dict[str, list[UsageRecord]]:
        """Return usage records for all tracked services."""
        return {svc: self.get_usage(svc) for svc in FREE_TIER_LIMITS}

    def check_alerts(self, threshold_pct: float = 80.0) -> list[str]:
        """Return alert messages for any metric that exceeds *threshold_pct*."""
        alerts: list[str] = []
        for service, metrics in self.get_all_usage().items():
            for rec in metrics:
                if rec.percentage_used >= threshold_pct:
                    alerts.append(
                        f"ALERT [{service}.{rec.metric}] "
                        f"{rec.current_usage:.1f}/{rec.limit:.1f} "
                        f"({rec.percentage_used:.1f}% — limit {threshold_pct}%)"
                    )
        return alerts

    def get_summary(self) -> dict:
        """Aggregate summary suitable for a dashboard."""
        all_usage = self.get_all_usage()
        services_summary: dict[str, dict] = {}
        for service, records in all_usage.items():
            services_summary[service] = {
                rec.metric: {
                    "current": rec.current_usage,
                    "limit": rec.limit,
                    "pct": rec.percentage_used,
                    "reset": rec.reset_period,
                }
                for rec in records
            }
        alerts = self.check_alerts()
        return {
            "services": services_summary,
            "alert_count": len(alerts),
            "alerts": alerts,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ── Module-level singleton ─────────────────────────────────────────────────────

tracker = ZeroCostTracker()

__all__ = [
    "FREE_TIER_LIMITS",
    "UsageRecord",
    "ZeroCostTracker",
    "tracker",
]
