# src/compliance/cab_gate.py
# CAB (Change Advisory Board) governance gate — MC-RULE-007
# Provides change request registration, approval tracking, and ASGI middleware.

from __future__ import annotations

import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

logger = logging.getLogger("tranc3.compliance.cab_gate")

CAB_GATE_ENABLED = os.getenv("CAB_GATE_ENABLED", "false").lower() == "true"

_DB_PATH = Path("./data/cab_changes.db")

# Mutating methods that trigger the CAB check
_MUTATING_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

# Path prefixes where CAB approval is enforced
_PROTECTED_PREFIXES = ("/admin/", "/config/", "/deploy/", "/workers/")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cab_changes (
            change_id    TEXT PRIMARY KEY,
            change_type  TEXT NOT NULL,
            description  TEXT NOT NULL,
            requestor    TEXT NOT NULL,
            risk         TEXT NOT NULL DEFAULT 'low',
            status       TEXT NOT NULL DEFAULT 'pending',
            approver     TEXT,
            created_at   REAL NOT NULL,
            approved_at  REAL
        )
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# CABGate
# ---------------------------------------------------------------------------


class CABGate:
    """
    Change Advisory Board governance gate for MC-RULE-007.

    The gate loads the Town Hall frameworks config to determine which change
    types require CAB approval, then persists all change records to SQLite.
    """

    def __init__(self, config_path: str = "config/townhall/frameworks.yaml") -> None:
        self._config: dict[str, Any] = {}
        self._load_config(config_path)

        with _get_conn() as conn:
            _init_db(conn)

        logger.info(
            "CABGate initialised | config=%s | enabled=%s",
            config_path,
            CAB_GATE_ENABLED,
        )

    def _load_config(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("CABGate config not found at %s — operating with empty config", path)
        except Exception as exc:
            logger.error("CABGate config load error: %s", exc)

    # ── Public API ─────────────────────────────────────────────────────────────

    def check_change(self, change_type: str, change_id: str, requestor: str) -> dict[str, Any]:
        """
        Return whether a registered change has CAB approval.

        When the change record does not exist the gate treats it as unapproved
        rather than raising — callers must register before checking.
        """
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT status, risk FROM cab_changes WHERE change_id = ?",
                (change_id,),
            ).fetchone()

        if row is None:
            return {
                "approved": False,
                "reason": f"Change record '{change_id}' not found",
                "cab_required": True,
            }

        cab_required = self._cab_required_for(change_type, row["risk"])
        approved = row["status"] == "approved"

        return {
            "approved": approved if cab_required else True,
            "reason": "approved" if approved else "pending CAB approval",
            "cab_required": cab_required,
        }

    def register_change(
        self,
        change_type: str,
        description: str,
        requestor: str,
        risk: str = "low",
    ) -> str:
        """Register a change request and return its generated change_id."""
        change_id = f"CAB-{uuid.uuid4().hex[:8].upper()}"
        now = time.time()

        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO cab_changes
                    (change_id, change_type, description, requestor, risk, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (change_id, change_type, description, requestor, risk, now),
            )
            conn.commit()

        logger.info(
            "CAB change registered | change_id=%s | type=%s | risk=%s | requestor=%s",
            change_id,
            change_type,
            risk,
            requestor,
        )
        return change_id

    def approve_change(self, change_id: str, approver: str) -> bool:
        """Approve a change request. Returns True on success, False if not found."""
        now = time.time()
        with _get_conn() as conn:
            cur = conn.execute(
                """
                UPDATE cab_changes
                SET status = 'approved', approver = ?, approved_at = ?
                WHERE change_id = ? AND status = 'pending'
                """,
                (approver, now, change_id),
            )
            conn.commit()
            updated = cur.rowcount > 0

        if updated:
            logger.info(
                "CAB change approved | change_id=%s | approver=%s",
                change_id,
                approver,
            )
        else:
            logger.warning(
                "CAB approve failed — not found or already approved | change_id=%s",
                change_id,
            )
        return updated

    # ── Internal ───────────────────────────────────────────────────────────────

    def _cab_required_for(self, change_type: str, risk: str) -> bool:
        # High-risk changes always need CAB regardless of config
        if risk in ("high", "critical"):
            return True

        # Governance domain from frameworks.yaml lists change types that need CAB
        governance = self._config.get("domains", {}).get("governance", [])
        cab_types = {entry.get("id", "") for entry in governance if entry.get("status") == "active"}
        return change_type in cab_types or risk == "medium"


# ---------------------------------------------------------------------------
# CABMiddleware
# ---------------------------------------------------------------------------


class CABMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that enforces CAB approval on mutating requests to
    protected paths when CAB_GATE_ENABLED=true.

    Expects callers to set the `X-Change-ID` header; missing or unapproved
    change IDs result in a 403 response.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._gate = cab_gate
        self._enabled = CAB_GATE_ENABLED
        if self._enabled:
            logger.info("CABMiddleware ACTIVE — MC-RULE-007 enforcement wired")
        else:
            logger.debug("CABMiddleware loaded but CAB_GATE_ENABLED=false")

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._enabled:
            return await call_next(request)

        method = request.method.upper()
        path = request.url.path

        if method not in _MUTATING_METHODS:
            return await call_next(request)

        if not any(path.startswith(prefix) for prefix in _PROTECTED_PREFIXES):
            return await call_next(request)

        change_id = request.headers.get("X-Change-ID")
        requestor = getattr(request.state, "user_id", None) or request.headers.get(
            "X-Requestor", "unknown"
        )

        if not change_id:
            logger.warning(
                "CAB gate blocked — missing X-Change-ID | method=%s path=%s requestor=%s",
                method,
                path,
                requestor,
            )
            return JSONResponse(
                {"error": "CAB approval required", "change_id": None},
                status_code=403,
            )

        # Derive change_type from path for the check call
        change_type = path.strip("/").split("/")[0]
        result = self._gate.check_change(change_type, change_id, requestor)

        if not result["approved"]:
            logger.warning(
                "CAB gate blocked | change_id=%s reason=%s method=%s path=%s",
                change_id,
                result["reason"],
                method,
                path,
            )
            return JSONResponse(
                {"error": "CAB approval required", "change_id": change_id},
                status_code=403,
            )

        # Attach approval status for downstream Magna Carta rules
        request.state.cab_approved = True
        request.state.change_record_id = change_id

        logger.info(
            "CAB gate passed | change_id=%s method=%s path=%s",
            change_id,
            method,
            path,
        )
        return await call_next(request)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

cab_gate = CABGate()
