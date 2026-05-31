"""GBrain ingestion pipeline — fire-and-forget SQLite capture of interactions.

The pipeline records every agent interaction (prompt/response pair plus
provenance) into a local SQLite database. Writes run in a thread executor so
the async request path is never blocked, and **all** errors are swallowed:
ingestion is best-effort telemetry feeding The Library (Zimik) and must never
break a user-facing request.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("tranc3.gbrain.pipeline")

# DB path is env-configurable; defaults to the production volume mount. Tests
# override GBRAIN_DB_PATH (see conftest.py) to a writable temp location.
_DB_PATH = os.environ.get("GBRAIN_DB_PATH", "/data/gbrain.db")


@dataclass
class AgentInteraction:
    """A single captured agent interaction."""

    prompt: str
    response: str
    source: str = "unknown"
    user_id: str = ""
    session_id: str = ""
    interaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)


class GBrainPipeline:
    """Best-effort, fire-and-forget interaction recorder.

    The database is initialised lazily on first successful connection. If the
    configured path is not writable the pipeline degrades to a silent no-op.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DB_PATH
        self._initialised = False
        self._disabled = False

    # ── Internal (runs in a worker thread) ────────────────────────────────
    def _connect(self) -> sqlite3.Connection | None:
        if self._disabled:
            return None
        try:
            parent = Path(self._db_path).parent
            parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._db_path, timeout=5, check_same_thread=False)
            if not self._initialised:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interactions (
                        interaction_id TEXT PRIMARY KEY,
                        prompt         TEXT NOT NULL,
                        response       TEXT NOT NULL,
                        source         TEXT DEFAULT 'unknown',
                        user_id        TEXT DEFAULT '',
                        session_id     TEXT DEFAULT '',
                        created_at     REAL NOT NULL
                    )
                    """
                )
                conn.commit()
                self._initialised = True
            return conn
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.debug("GBrain pipeline disabled (cannot open %s): %s", self._db_path, exc)
            self._disabled = True
            return None

    def _write(self, interaction: AgentInteraction) -> None:
        conn = self._connect()
        if conn is None:
            return
        try:
            conn.execute(
                "INSERT OR REPLACE INTO interactions "
                "(interaction_id, prompt, response, source, user_id, session_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    interaction.interaction_id,
                    interaction.prompt,
                    interaction.response,
                    interaction.source,
                    interaction.user_id,
                    interaction.session_id,
                    interaction.created_at,
                ),
            )
            conn.commit()
        except Exception as exc:  # pragma: no cover - best-effort
            logger.debug("GBrain ingest write failed: %s", exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ── Public API ────────────────────────────────────────────────────────
    async def ingest(self, interaction: AgentInteraction) -> None:
        """Record an interaction without blocking the event loop.

        Safe to schedule via ``asyncio.create_task`` — never raises.
        """
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._write, interaction)
        except Exception as exc:  # pragma: no cover - fire-and-forget guard
            logger.debug("GBrain ingest failed: %s", exc)

    def count(self) -> int:
        """Return the number of recorded interactions (0 if unavailable)."""
        conn = self._connect()
        if conn is None:
            return 0
        try:
            cur = conn.execute("SELECT COUNT(*) FROM interactions")
            return int(cur.fetchone()[0])
        except Exception:
            return 0
        finally:
            try:
                conn.close()
            except Exception:
                pass


_pipeline: GBrainPipeline | None = None


def get_pipeline() -> GBrainPipeline:
    """Return the process-wide GBrain pipeline singleton."""
    global _pipeline
    if _pipeline is None:
        _pipeline = GBrainPipeline()
    return _pipeline
