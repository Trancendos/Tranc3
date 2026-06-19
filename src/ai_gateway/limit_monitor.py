"""
Persistent AI provider limit monitor with hard stops and adaptive rotation.

Survives process restarts by persisting usage counters to SQLite.
Exposes a health/dashboard endpoint for The Observatory.

Zero-cost mandate: when ALL free providers hit their daily hard stops,
the system enters OFFLINE mode (deterministic stub) rather than paying.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Dict, Generator, Optional

logger = logging.getLogger("tranc3.ai_gateway.limit_monitor")

_DB_PATH = Path(os.getenv("AI_GATEWAY_DB", "/tmp/ai_gateway_limits.db"))
_lock = Lock()


@contextmanager
def _db() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS provider_usage (
                provider TEXT PRIMARY KEY,
                daily_req INTEGER DEFAULT 0,
                hourly_req INTEGER DEFAULT 0,
                daily_tokens INTEGER DEFAULT 0,
                day_start REAL DEFAULT 0,
                hour_start REAL DEFAULT 0,
                consecutive_errors INTEGER DEFAULT 0,
                cooldown_until REAL DEFAULT 0,
                last_updated REAL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                provider TEXT,
                event TEXT,
                tokens INTEGER DEFAULT 0,
                detail TEXT DEFAULT ''
            )
        """)


_init_db()


@dataclass
class ProviderStatus:
    name: str
    daily_req: int
    daily_req_limit: int
    hourly_req: int
    hourly_req_limit: int
    daily_tokens: int
    daily_token_limit: int
    consecutive_errors: int
    available: bool
    should_rotate: bool
    utilisation_pct: float
    status: str  # "ok" | "rotating" | "hard_stop" | "cooling_down" | "unlimited"


class LimitMonitor:
    """Persistent, thread-safe usage tracker for all AI providers."""

    # Provider limits: (daily_req, hourly_req, daily_tokens)  — -1 = unlimited
    LIMITS: Dict[str, tuple] = {
        "ollama": (-1, -1, -1),
        "groq": (14400, 250, 500000),
        "gemini": (1500, 60, -1),
        "cerebras": (1440, 30, 1000000),
        "sambanova": (500, 60, -1),
        "openrouter": (200, 50, -1),
        "huggingface": (1000, 100, -1),
        "together": (500, 60, 100000),
        "deepseek": (500, 60, -1),
        "cloudflare_ai": (10000, 500, -1),
        "offline": (-1, -1, -1),
    }

    ROTATE_THRESHOLD = 0.80
    HARD_STOP_THRESHOLD = 0.95

    def _get_row(self, provider: str) -> dict:
        with _db() as conn:
            row = conn.execute(
                "SELECT * FROM provider_usage WHERE provider = ?", (provider,)
            ).fetchone()
            if not row:
                now = time.time()
                conn.execute(
                    """INSERT INTO provider_usage
                       (provider, daily_req, hourly_req, daily_tokens,
                        day_start, hour_start, consecutive_errors, cooldown_until, last_updated)
                       VALUES (?, 0, 0, 0, ?, ?, 0, 0, ?)""",
                    (provider, now, now, now),
                )
                return {
                    "provider": provider, "daily_req": 0, "hourly_req": 0,
                    "daily_tokens": 0, "day_start": now, "hour_start": now,
                    "consecutive_errors": 0, "cooldown_until": 0, "last_updated": now,
                }
            return dict(row)

    def _reset_if_needed(self, provider: str, row: dict) -> dict:
        now = time.time()
        updates = {}
        if now - row["day_start"] >= 86400:
            updates.update(daily_req=0, daily_tokens=0, day_start=now)
        if now - row["hour_start"] >= 3600:
            updates.update(hourly_req=0, hour_start=now)
        if updates:
            updates["last_updated"] = now
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            with _db() as conn:
                conn.execute(
                    f"UPDATE provider_usage SET {set_clause} WHERE provider = ?",
                    (*updates.values(), provider),
                )
            row = {**row, **updates}
        return row

    def record_request(self, provider: str, tokens: int = 0) -> None:
        with _lock:
            now = time.time()
            with _db() as conn:
                conn.execute(
                    """UPDATE provider_usage SET
                       daily_req = daily_req + 1,
                       hourly_req = hourly_req + 1,
                       daily_tokens = daily_tokens + ?,
                       consecutive_errors = 0,
                       last_updated = ?
                       WHERE provider = ?""",
                    (tokens, now, provider),
                )
                conn.execute(
                    "INSERT INTO usage_events (ts, provider, event, tokens) VALUES (?, ?, 'request', ?)",
                    (now, provider, tokens),
                )
            logger.debug("provider=%s request recorded tokens=%d", provider, tokens)

    def record_error(self, provider: str, detail: str = "") -> None:
        with _lock:
            now = time.time()
            with _db() as conn:
                conn.execute(
                    """UPDATE provider_usage SET
                       consecutive_errors = consecutive_errors + 1,
                       last_updated = ?
                       WHERE provider = ?""",
                    (now, provider),
                )
                row = self._get_row(provider)
                if row["consecutive_errors"] >= 5:
                    cooldown_until = now + 300  # 5-min cooldown
                    conn.execute(
                        "UPDATE provider_usage SET cooldown_until = ? WHERE provider = ?",
                        (cooldown_until, provider),
                    )
                conn.execute(
                    "INSERT INTO usage_events (ts, provider, event, detail) VALUES (?, ?, 'error', ?)",
                    (now, provider, detail[:500]),
                )

    def get_status(self, provider: str) -> ProviderStatus:
        row = self._get_row(provider)
        row = self._reset_if_needed(provider, row)
        limits = self.LIMITS.get(provider, (-1, -1, -1))
        daily_limit, hourly_limit, token_limit = limits

        now = time.time()
        in_cooldown = row["consecutive_errors"] >= 5 and now < row["cooldown_until"]

        def _over(count: int, limit: int, threshold: float) -> bool:
            return limit != -1 and count >= int(limit * threshold)

        hard_stopped = (
            _over(row["daily_req"], daily_limit, self.HARD_STOP_THRESHOLD)
            or _over(row["hourly_req"], hourly_limit, self.HARD_STOP_THRESHOLD)
            or _over(row["daily_tokens"], token_limit, self.HARD_STOP_THRESHOLD)
        )
        should_rotate = (
            _over(row["daily_req"], daily_limit, self.ROTATE_THRESHOLD)
            or _over(row["hourly_req"], hourly_limit, self.ROTATE_THRESHOLD)
        )

        available = not hard_stopped and not in_cooldown
        if provider == "ollama" or provider == "offline":
            available = True
            should_rotate = False

        # Compute worst utilisation
        utilisation = 0.0
        if daily_limit != -1 and daily_limit > 0:
            utilisation = max(utilisation, row["daily_req"] / daily_limit)
        if hourly_limit != -1 and hourly_limit > 0:
            utilisation = max(utilisation, row["hourly_req"] / hourly_limit)

        if in_cooldown:
            status = "cooling_down"
        elif hard_stopped:
            status = "hard_stop"
        elif should_rotate:
            status = "rotating"
        elif daily_limit == -1:
            status = "unlimited"
        else:
            status = "ok"

        return ProviderStatus(
            name=provider,
            daily_req=row["daily_req"],
            daily_req_limit=daily_limit,
            hourly_req=row["hourly_req"],
            hourly_req_limit=hourly_limit,
            daily_tokens=row["daily_tokens"],
            daily_token_limit=token_limit,
            consecutive_errors=row["consecutive_errors"],
            available=available,
            should_rotate=should_rotate,
            utilisation_pct=round(utilisation * 100, 1),
            status=status,
        )

    def get_dashboard(self) -> dict:
        statuses = {p: self.get_status(p) for p in self.LIMITS}
        available = [p for p, s in statuses.items() if s.available]
        at_capacity = [p for p, s in statuses.items() if s.status == "hard_stop"]
        rotating = [p for p, s in statuses.items() if s.should_rotate]

        # Pick active provider (highest priority available not rotating)
        priority_order = [
            "ollama", "groq", "gemini", "cerebras", "sambanova",
            "openrouter", "huggingface", "together", "deepseek",
            "cloudflare_ai", "offline",
        ]
        active = next(
            (p for p in priority_order if statuses.get(p) and statuses[p].available and not statuses[p].should_rotate),
            next((p for p in priority_order if statuses.get(p) and statuses[p].available), "offline"),
        )

        return {
            "active_provider": active,
            "available_providers": available,
            "rotating_providers": rotating,
            "hard_stopped_providers": at_capacity,
            "zero_cost_operational": len(available) > 1 or "ollama" in available,
            "providers": {
                p: {
                    "status": s.status,
                    "available": s.available,
                    "utilisation_pct": s.utilisation_pct,
                    "daily_req": f"{s.daily_req}/{s.daily_req_limit if s.daily_req_limit != -1 else '∞'}",
                    "hourly_req": f"{s.hourly_req}/{s.hourly_req_limit if s.hourly_req_limit != -1 else '∞'}",
                    "consecutive_errors": s.consecutive_errors,
                }
                for p, s in statuses.items()
            },
        }

    def get_optimal_provider(self) -> Optional[str]:
        priority_order = [
            "ollama", "groq", "gemini", "cerebras", "sambanova",
            "openrouter", "huggingface", "together", "deepseek",
            "cloudflare_ai", "offline",
        ]
        # First: available and not rotating
        for p in priority_order:
            s = self.get_status(p)
            if s.available and not s.should_rotate:
                return p
        # Fallback: available even at rotation threshold
        for p in priority_order:
            s = self.get_status(p)
            if s.available:
                logger.warning("All providers at rotation threshold — using %s", p)
                return p
        logger.error("ALL providers hard-stopped — entering offline mode")
        return "offline"

    def reset_provider(self, provider: str) -> None:
        """Manual reset (admin use only)."""
        now = time.time()
        with _db() as conn:
            conn.execute(
                """UPDATE provider_usage SET
                   daily_req = 0, hourly_req = 0, daily_tokens = 0,
                   consecutive_errors = 0, cooldown_until = 0,
                   day_start = ?, hour_start = ?, last_updated = ?
                   WHERE provider = ?""",
                (now, now, now, provider),
            )


# Singleton
monitor = LimitMonitor()

__all__ = ["LimitMonitor", "ProviderStatus", "monitor"]
