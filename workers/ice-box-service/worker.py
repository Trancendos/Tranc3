"""
The Ice Box — Threat Isolation & Static Analysis Service
=========================================================
Port 8046.  Lead AI: Neonach.

Exposes:
  POST /scan            — analyse content, return verdict + findings
  POST /quarantine      — explicitly quarantine content
  GET  /quarantine      — list active quarantine records
  GET  /quarantine/{id} — get a single record
  POST /quarantine/{id}/release — release a quarantined item
  GET  /stats           — quarantine + signature stats
  GET  /health
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # noqa: E402

from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from src.security.ice_box.analyser import ThreatAnalyser, ThreatVerdict  # noqa: E402
from src.security.ice_box.quarantine import QuarantineStore  # noqa: E402
from src.security.ice_box.signatures import get_library  # noqa: E402
from src.security.warp_tunnel.tunnel import TunnelConfig, WarpTunnel  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.getenv("ICE_BOX_PORT", "8046"))
QUARANTINE_DB = os.getenv("ICE_BOX_QUARANTINE_DB", "data/ice_box_quarantine.db")
STRICT_MODE = os.getenv("ICE_BOX_STRICT_MODE", "false").lower() == "true"
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")


def _require_internal_auth(x_internal_secret: str = Header(default="")) -> None:
    """Gate the quarantine-release write behind INTERNAL_SECRET when configured.

    No-op (open) if INTERNAL_SECRET is unset, matching the platform's other
    optional-auth workers (e.g. storage-service) — operators must set the
    env var to actually enforce this.
    """
    if INTERNAL_SECRET and x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


app = FastAPI(
    title="The Ice Box",
    description="Threat Isolation & Static Analysis Engine — Neonach",
    version="1.0.0",
)

# OpenTelemetry instrumentation
try:
    from src.observability.worker_setup import instrument_worker

    instrument_worker(app, service_name="tranc3.ice-box-service")
except Exception:
    pass  # OTel is optional — never block startup

_tunnel = WarpTunnel(TunnelConfig(quarantine_db=QUARANTINE_DB, strict_mode=STRICT_MODE))
_analyser = ThreatAnalyser()
_quarantine = QuarantineStore(QUARANTINE_DB)
_start_time = time.time()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    content: str
    source: str = ""
    auto_quarantine: bool = True


class ScanResponse(BaseModel):
    content_hash: str
    verdict: str
    allow: bool
    findings_count: int
    critical_count: int
    high_count: int
    entropy: float
    analysis_ms: float
    quarantine_id: Optional[str] = None
    findings: list[dict[str, Any]] = []


class ReleaseRequest(BaseModel):
    reason: str
    reviewed_by: str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.post("/scan", response_model=ScanResponse, dependencies=[Depends(_require_internal_auth)])
def scan(req: ScanRequest):
    if req.auto_quarantine:
        result = _tunnel.scan(req.content, source=req.source)
        report = _analyser.analyse(req.content, source=req.source)
        return ScanResponse(
            content_hash=report.content_hash,
            verdict=result.verdict.value,
            allow=result.allow,
            findings_count=result.findings_count,
            critical_count=report.critical_count,
            high_count=report.high_count,
            entropy=report.entropy,
            analysis_ms=result.analysis_ms,
            quarantine_id=result.quarantine_id,
            findings=[
                {
                    "signature_id": f.signature_id,
                    "category": f.category.value,
                    "severity": f.severity,
                    "description": f.description,
                }
                for f in report.findings
            ],
        )
    else:
        report = _analyser.analyse(req.content, source=req.source)
        return ScanResponse(
            content_hash=report.content_hash,
            verdict=report.verdict.value,
            allow=report.verdict not in (ThreatVerdict.MALICIOUS, ThreatVerdict.QUARANTINED),
            findings_count=len(report.findings),
            critical_count=report.critical_count,
            high_count=report.high_count,
            entropy=report.entropy,
            analysis_ms=report.analysis_ms,
            quarantine_id=None,
            findings=[
                {
                    "signature_id": f.signature_id,
                    "category": f.category.value,
                    "severity": f.severity,
                    "description": f.description,
                }
                for f in report.findings
            ],
        )


@app.get("/quarantine")
def list_quarantine(limit: int = 50):
    records = _quarantine.list_active(limit=limit)
    return {
        "records": [
            {
                "quarantine_id": r.quarantine_id,
                "content_hash": r.content_hash,
                "source": r.source,
                "verdict": r.verdict,
                "quarantined_at": r.quarantined_at,
                "content_length": r.content_length,
            }
            for r in records
        ],
        "total": len(records),
    }


@app.get("/quarantine/{quarantine_id}")
def get_quarantine(quarantine_id: str):
    record = _quarantine.get(quarantine_id)
    if not record:
        raise HTTPException(status_code=404, detail="Quarantine record not found")
    return {
        "quarantine_id": record.quarantine_id,
        "content_hash": record.content_hash,
        "source": record.source,
        "verdict": record.verdict,
        "findings": record.findings_json,
        "entropy": record.entropy,
        "content_length": record.content_length,
        "quarantined_at": record.quarantined_at,
        "released_at": record.released_at,
        "release_reason": record.release_reason,
        "reviewed_by": record.reviewed_by,
    }


@app.post("/quarantine/{quarantine_id}/release", dependencies=[Depends(_require_internal_auth)])
def release_quarantine(quarantine_id: str, req: ReleaseRequest):
    ok = _quarantine.release(quarantine_id, reason=req.reason, reviewed_by=req.reviewed_by)
    if not ok:
        raise HTTPException(status_code=404, detail="Record not found or already released")
    return {"released": True, "quarantine_id": quarantine_id}


@app.get("/stats")
def stats():
    q_stats = _quarantine.stats()
    lib = get_library()
    return {
        "quarantine": q_stats,
        "signatures": {"total": len(lib)},
        "strict_mode": STRICT_MODE,
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@app.get("/health")
def health():
    lib = get_library()
    return {
        "status": "healthy",
        "service": "ice-box-service",
        "lead_ai": "Neonach",
        "port": PORT,
        "signatures_loaded": len(lib),
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("worker:app", host="0.0.0.0", port=PORT, reload=False)  # nosec B104 — containerised service
