"""
src/gbrain/pipeline.py — GBrain knowledge-ingestion pipeline.

Provides a fire-and-forget interface for logging chat interactions to
The Library (Zimik) knowledge store. Uses SQLite for zero-cost, zero-dependency
persistence; falls back gracefully when unavailable.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from src.database.encrypted_sqlite import connect as sqlite3_connect
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_DB_PATH = Path("data/gbrain_interactions.db")
_PIPELINE: Optional["GBrainPipeline"] = None


@dataclass
class AgentInteraction:
    prompt: str
    response: str
    source: str = "unknown"
    user_id: str = ""
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)


class GBrainPipeline:
    """
    Lightweight SQLite-backed pipeline for ingesting agent interactions.

    The pipeline runs asynchronously and never raises — failures are
    logged as warnings so the caller is never blocked.
    """

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._db_path = db_path
        self._ready = False
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3_connect(str(self._db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interactions (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts        REAL    NOT NULL,
                    source    TEXT    NOT NULL,
                    user_id   TEXT,
                    session_id TEXT,
                    prompt    TEXT    NOT NULL,
                    response  TEXT    NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON interactions(ts)")
            conn.commit()
            conn.close()
            self._ready = True
        except Exception as exc:
            log.warning("GBrainPipeline: DB init failed — pipeline disabled: %s", exc)

    async def ingest(self, interaction: AgentInteraction) -> None:
        if not self._ready:
            return
        try:
            # Offload blocking IO to thread pool
            await asyncio.get_event_loop().run_in_executor(None, self._write_sync, interaction)
        except Exception as exc:
            log.warning("GBrainPipeline.ingest: %s", exc)

    def _write_sync(self, i: AgentInteraction) -> None:
        conn = sqlite3_connect(str(self._db_path))
        conn.execute(
            "INSERT INTO interactions(ts, source, user_id, session_id, prompt, response)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (i.timestamp, i.source, i.user_id, i.session_id, i.prompt, i.response),
        )
        conn.commit()
        conn.close()


def get_pipeline() -> GBrainPipeline:
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = GBrainPipeline()
    return _PIPELINE
