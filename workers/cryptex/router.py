"""Cryptex / The Ice Box — FastAPI routes"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from models import ScanRequest, ThreatIndicator
from service import SecurityEngineRouter

import config
from database import CryptexDatabase


def _make_router(db: CryptexDatabase, engine_router: SecurityEngineRouter) -> APIRouter:
    async def _auth(
        x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
    ) -> None:
        if not config.INTERNAL_SECRET:
            return
        if x_internal_secret != config.INTERNAL_SECRET:
            raise HTTPException(401, "Invalid or missing X-Internal-Secret header")

    router = APIRouter(dependencies=[Depends(_auth)])

    # ── Engine status ──────────────────────────────────────────────────────────

    @router.get("/engines")
    def list_engine_statuses():
        return {"engines": [s.model_dump() for s in engine_router.engine_statuses()]}

    # ── Scans ──────────────────────────────────────────────────────────────────

    @router.post("/scan")
    async def submit_scan(req: ScanRequest):
        """Submit a security scan via the 8-tier adaptive engine router."""
        result = await engine_router.scan(req)
        return {
            "ok": True,
            "scan_id": result.scan_id,
            "status": result.status.value,
            "engine_used": result.engine_used,
            "threat_found": result.threat_found,
            "severity": result.severity.value,
        }

    @router.get("/scans")
    def list_scans(limit: int = 50, offset: int = 0):
        return {"scans": db.list_results(limit=limit, offset=offset)}

    @router.get("/scans/{scan_id}")
    def get_scan(scan_id: str):
        result = db.get_result(scan_id)
        if not result:
            raise HTTPException(404, f"Scan not found: {scan_id}")
        return result

    # ── Threat Intelligence ────────────────────────────────────────────────────

    @router.post("/intel/ingest")
    def ingest_indicator(ioc: ThreatIndicator):
        """Ingest a threat indicator into the local IOC database."""
        saved = db.save_indicator(ioc)
        return {"ok": True, "indicator_id": saved.indicator_id}

    @router.get("/intel")
    def list_indicators(
        ioc_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ):
        return {"indicators": db.list_indicators(ioc_type=ioc_type, limit=limit, offset=offset)}

    @router.get("/intel/lookup")
    def lookup_indicator(value: str):
        match = db.lookup_indicator(value)
        return {"found": match is not None, "indicator": match}

    return router
