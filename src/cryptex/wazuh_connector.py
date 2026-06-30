# src/cryptex/wazuh_connector.py
# Cryptex — Wazuh SIEM connector.
#
# Connects to a self-hosted Wazuh Manager REST API to send/receive security
# alerts. Wazuh is free and open-source (GPL-2.0): https://wazuh.com/
#
# Degraded mode: when Wazuh is unavailable, alerts are buffered in a local
# SQLite database (/tmp/wazuh_buffer.db) and replayed automatically once the
# connection is restored.
#
# Rate limits: 100 req/min hard stop (tracked in-process).
# All public methods return empty/False on error — never raise.

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_WAZUH_URL = os.getenv("WAZUH_URL", "http://localhost:55000")
_WAZUH_USER = os.getenv("WAZUH_USER", "wazuh")
_WAZUH_PASSWORD = os.getenv("WAZUH_PASSWORD", "")
_BUFFER_DB = os.getenv("WAZUH_BUFFER_DB", "/data/wazuh_buffer.db")

_RATE_LIMIT_PER_MIN = 100  # hard stop
_TOKEN_TTL = 900  # Wazuh JWT expires after 15 minutes by default


# ---------------------------------------------------------------------------
# SQLite buffer helpers
# ---------------------------------------------------------------------------


def _init_buffer_db(db_path: str) -> sqlite3.Connection:
    """Create (or open) the offline alert buffer database."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_buffer (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            queued_at   REAL    NOT NULL,
            rule_id     INTEGER NOT NULL,
            description TEXT    NOT NULL,
            level       INTEGER NOT NULL,
            agent_name  TEXT    NOT NULL,
            data        TEXT    NOT NULL
        )
        """
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Main connector
# ---------------------------------------------------------------------------


class WazuhConnector:
    """
    Wazuh SIEM connector for the Cryptex security engine.

    Connects to a self-hosted Wazuh Manager REST API (default port 55000).
    Authenticates via username/password to obtain a short-lived JWT, which is
    refreshed automatically before expiry.

    When the Wazuh API is unreachable, all ``send_alert`` calls are persisted
    to a local SQLite buffer and replayed once connectivity is restored.  The
    background flush loop runs as a daemon thread and checks every 30 seconds.

    All public methods catch all exceptions and return safe defaults
    (``False`` / ``[]`` / ``{}`` / ``None``) — they never raise.

    Environment variables
    ---------------------
    WAZUH_URL       Self-hosted Wazuh Manager URL (default: http://localhost:55000)
    WAZUH_USER      Wazuh API username             (default: wazuh)
    WAZUH_PASSWORD  Wazuh API password             (default: "")
    WAZUH_BUFFER_DB SQLite path for offline buffer  (default: /tmp/wazuh_buffer.db)
    """

    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        buffer_db: Optional[str] = None,
    ) -> None:
        self._url = (url or _WAZUH_URL).rstrip("/")
        self._username = username or _WAZUH_USER
        self._password = password or _WAZUH_PASSWORD
        self._buffer_db_path = buffer_db or _BUFFER_DB

        # JWT state
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._token_lock = threading.Lock()

        # Rate-limit state (sliding window per minute)
        self._req_timestamps: list[float] = []
        self._rate_lock = threading.Lock()

        # SQLite buffer for offline queueing
        self._buffer_conn: Optional[sqlite3.Connection] = None
        self._buffer_lock = threading.Lock()
        self._init_buffer()

        # Degraded-mode flag
        self._degraded = False

        # Background flush thread
        self._flush_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="wazuh-flush"
        )
        self._flush_thread.start()

    # ── Buffer initialisation ─────────────────────────────────────────────

    def _init_buffer(self) -> None:
        try:
            self._buffer_conn = _init_buffer_db(self._buffer_db_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("wazuh: cannot open buffer db %s: %s", self._buffer_db_path, exc)
            self._buffer_conn = None

    # ── Rate limiting ─────────────────────────────────────────────────────

    def _check_rate_limit(self) -> bool:
        """Return True if request is allowed; False if rate limit exceeded."""
        now = time.monotonic()
        with self._rate_lock:
            self._req_timestamps = [t for t in self._req_timestamps if now - t < 60]
            if len(self._req_timestamps) >= _RATE_LIMIT_PER_MIN:
                logger.warning("wazuh: rate limit reached (%d/min)", _RATE_LIMIT_PER_MIN)
                return False
            self._req_timestamps.append(now)
        return True

    # ── Authentication / token management ────────────────────────────────

    def _get_token(self) -> Optional[str]:
        """Return a valid JWT, refreshing if necessary."""
        with self._token_lock:
            if self._token and time.time() < self._token_expires_at - 30:
                return self._token
            return self._refresh_token()

    def _refresh_token(self) -> Optional[str]:
        """Authenticate against the Wazuh API and cache the JWT."""
        try:
            import base64

            credentials = base64.b64encode(f"{self._username}:{self._password}".encode()).decode()
            req = Request(
                f"{self._url}/security/user/authenticate",
                method="GET",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/json",
                },
            )
            with urlopen(req, timeout=10) as resp:  # nosec B310
                data = json.loads(resp.read().decode())
            token = data.get("data", {}).get("token")
            if not token:
                logger.warning("wazuh: auth response missing token")
                return None
            self._token = token
            self._token_expires_at = time.time() + _TOKEN_TTL
            self._degraded = False
            logger.debug("wazuh: token refreshed (expires in %ds)", _TOKEN_TTL)
            return self._token
        except Exception as exc:  # noqa: BLE001
            logger.warning("wazuh: authentication failed: %s", exc)
            self._degraded = True
            return None

    # ── Low-level HTTP helpers ────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Perform an authenticated request; return parsed JSON or None."""
        if not self._check_rate_limit():
            return None
        token = self._get_token()
        if not token:
            return None
        url = f"{self._url}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urlencode(params)}"
        body = json.dumps(payload).encode() if payload else None
        req = Request(
            url,
            method=method,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=15) as resp:  # nosec B310
                return json.loads(resp.read().decode())
        except URLError as exc:
            logger.warning("wazuh: network error [%s %s]: %s", method, path, exc)
            self._degraded = True
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("wazuh: request error [%s %s]: %s", method, path, exc)
            return None

    # ── Buffer helpers ────────────────────────────────────────────────────

    def _buffer_alert(
        self,
        rule_id: int,
        description: str,
        level: int,
        agent_name: str,
        data: Dict[str, Any],
    ) -> None:
        """Persist an alert to the SQLite offline buffer."""
        if not self._buffer_conn:
            return
        try:
            with self._buffer_lock:
                self._buffer_conn.execute(
                    """
                    INSERT INTO alert_buffer
                        (queued_at, rule_id, description, level, agent_name, data)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        time.time(),
                        rule_id,
                        description,
                        level,
                        agent_name,
                        json.dumps(data),
                    ),
                )
                self._buffer_conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("wazuh: buffer write failed: %s", exc)

    def _flush_buffer(self) -> int:
        """Replay buffered alerts; return count flushed."""
        if not self._buffer_conn:
            return 0
        flushed = 0
        try:
            with self._buffer_lock:
                rows = self._buffer_conn.execute(
                    "SELECT id, rule_id, description, level, agent_name, data "
                    "FROM alert_buffer ORDER BY queued_at LIMIT 50"
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            logger.warning("wazuh: buffer read failed: %s", exc)
            return 0

        ids_to_delete: list[int] = []
        for row in rows:
            row_id, rule_id, description, level, agent_name, data_json = row
            try:
                data = json.loads(data_json)
            except Exception:  # noqa: BLE001
                data = {}
            ok = self._send_alert_now(rule_id, description, level, agent_name, data)
            if ok:
                ids_to_delete.append(row_id)
                flushed += 1
            else:
                break  # still degraded; stop trying

        if ids_to_delete:
            try:
                with self._buffer_lock:
                    for row_id in ids_to_delete:
                        self._buffer_conn.execute(
                            "DELETE FROM alert_buffer WHERE id = ?",
                            (row_id,),
                        )
                    self._buffer_conn.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("wazuh: buffer cleanup failed: %s", exc)

        if flushed:
            logger.info("wazuh: flushed %d buffered alert(s)", flushed)
        return flushed

    def _flush_loop(self) -> None:
        """Background thread: check every 30 s, flush when connection restored."""
        while True:
            try:
                time.sleep(30)
                if self._degraded:
                    self._flush_buffer()
            except Exception:  # noqa: BLE001
                pass

    # ── Public API ────────────────────────────────────────────────────────

    def send_alert(
        self,
        rule_id: int,
        description: str,
        level: int,
        agent_name: str = "tranc3",
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Send a security alert to Wazuh.

        Parameters
        ----------
        rule_id:      Wazuh rule identifier (integer).
        description:  Human-readable description of the alert.
        level:        Wazuh severity level (1–15, 15 = most severe).
        agent_name:   Name of the reporting agent (default: "tranc3").
        data:         Optional extra key/value metadata dict.

        Returns
        -------
        True on success; False on failure (alert buffered for later replay).
        """
        try:
            if data is None:
                data = {}
            ok = self._send_alert_now(rule_id, description, level, agent_name, data)
            if not ok:
                self._buffer_alert(rule_id, description, level, agent_name, data)
            return ok
        except Exception as exc:  # noqa: BLE001
            logger.error("wazuh: send_alert unexpected error: %s", exc)
            return False

    def _send_alert_now(
        self,
        rule_id: int,
        description: str,
        level: int,
        agent_name: str,
        data: Dict[str, Any],
    ) -> bool:
        """Internal: attempt immediate delivery; return True on success."""
        payload = {
            "rule": {
                "id": str(rule_id),
                "description": description,
                "level": level,
            },
            "agent": {"name": agent_name},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        # Wazuh does not expose a generic alert injection endpoint on the
        # Manager REST API for external events; we use the /events endpoint
        # (available on Wazuh >= 4.x with the correct permissions).
        resp = self._request("POST", "/events", payload={"events": [payload]})
        if resp is None:
            return False
        error_code = resp.get("error", 1)
        return error_code == 0

    def get_alerts(
        self,
        limit: int = 50,
        severity_min: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve recent alerts from Wazuh.

        Parameters
        ----------
        limit:        Maximum number of alerts to return (default: 50).
        severity_min: Minimum Wazuh rule level to include (default: 3).

        Returns
        -------
        List of alert dicts; empty list on error or degraded mode.
        """
        try:
            resp = self._request(
                "GET",
                "/alerts",
                params={
                    "limit": min(limit, 500),
                    "sort": "-timestamp",
                    "q": f"rule.level>={severity_min}",
                },
            )
            if not resp:
                return []
            items = resp.get("data", {}).get("affected_items", [])
            return items[:limit]
        except Exception as exc:  # noqa: BLE001
            logger.error("wazuh: get_alerts error: %s", exc)
            return []

    def register_agent(self, name: str, ip: str) -> Optional[str]:
        """
        Register a new Wazuh agent (or return existing agent ID).

        Parameters
        ----------
        name: Agent name (e.g. "tranc3-backend").
        ip:   Agent IP address.

        Returns
        -------
        Agent ID string on success; None on failure.
        """
        try:
            payload = {"name": name, "ip": ip}
            resp = self._request("POST", "/agents", payload=payload)
            if not resp:
                return None
            if resp.get("error", 1) != 0:
                logger.warning("wazuh: register_agent error: %s", resp.get("message"))
                return None
            agent_id: Optional[str] = resp.get("data", {}).get("id") or resp.get("data", {}).get(
                "agent_id"
            )
            if agent_id:
                logger.info("wazuh: registered agent '%s' → id=%s", name, agent_id)
            return agent_id
        except Exception as exc:  # noqa: BLE001
            logger.error("wazuh: register_agent error: %s", exc)
            return None

    def get_agent_status(self) -> Dict[str, Any]:
        """
        Check the health/status of the Wazuh Manager and registered agents.

        Returns
        -------
        Dict with 'connected', 'total_agents', 'active', 'disconnected',
        and 'degraded' keys.  Empty dict on unrecoverable error.
        """
        try:
            resp = self._request("GET", "/agents/summary/status")
            if not resp:
                return {
                    "connected": False,
                    "degraded": True,
                    "total_agents": 0,
                    "active": 0,
                    "disconnected": 0,
                }
            summary = resp.get("data", {})
            return {
                "connected": resp.get("error", 1) == 0,
                "degraded": self._degraded,
                "total_agents": summary.get("connection", {}).get("total", 0),
                "active": summary.get("connection", {}).get("active", 0),
                "disconnected": summary.get("connection", {}).get("disconnected", 0),
                "pending": summary.get("connection", {}).get("pending", 0),
                "never_connected": summary.get("connection", {}).get("never_connected", 0),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("wazuh: get_agent_status error: %s", exc)
            return {}

    # ── Diagnostics ───────────────────────────────────────────────────────

    @property
    def degraded(self) -> bool:
        """True when Wazuh is currently unreachable."""
        return self._degraded

    def buffered_count(self) -> int:
        """Return the number of alerts currently waiting in the offline buffer."""
        if not self._buffer_conn:
            return 0
        try:
            with self._buffer_lock:
                row = self._buffer_conn.execute("SELECT COUNT(*) FROM alert_buffer").fetchone()
            return row[0] if row else 0
        except Exception:  # noqa: BLE001
            return 0


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_connector: Optional[WazuhConnector] = None


def get_wazuh() -> WazuhConnector:
    """Return (and lazily create) the module-level WazuhConnector singleton."""
    global _connector
    if _connector is None:
        _connector = WazuhConnector()
    return _connector
