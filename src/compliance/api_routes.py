"""
Compliance API Routes — Tranc3 / Trancendos Platform

FastAPI router exposing /compliance/* endpoints.

Routes:
    GET /compliance/status          -- live compliance status JSON
    GET /compliance/report          -- full compliance report JSON
    GET /compliance/matrix          -- traceability matrix JSON
    GET /compliance/export/markdown -- download Markdown report
    GET /compliance/export/html     -- download HTML report
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse

from src.compliance.checker import REGISTER_PATH, load_and_check
from src.compliance.report_generator import generate_html, generate_markdown
from src.compliance.traceability import build_matrix

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["compliance"])


def _get_report():
    """Load and return the compliance report, raising 503 on failure."""
    try:
        return load_and_check(REGISTER_PATH)
    except FileNotFoundError as e:
        logger.error("Compliance register not found: %s", e)
        raise HTTPException(status_code=503, detail=f"Compliance register not available: {e}")
    except Exception as e:
        logger.error("Compliance checker error: %s", e)
        raise HTTPException(status_code=500, detail=f"Compliance check failed: {e}")


@router.get("/status", summary="Live compliance status")
async def get_compliance_status() -> dict[str, Any]:
    """
    Returns a compact compliance status summary.

    Suitable for health dashboards and monitoring tools.
    """
    report = _get_report()
    counts = report.status_counts
    return {
        "platform": report.platform,
        "classification": report.classification,
        "overall_score": report.overall_score,
        "generated_at": report.generated_at,
        "ci_pass": report.overall_score >= 70.0,
        "status_counts": counts,
        "areas": {
            area_code: {
                "standard": a.standard,
                "total": a.total,
                "compliant": a.compliant,
                "partial": a.partial,
                "planned": a.planned,
                "score_pct": a.score_pct,
            }
            for area_code, a in sorted(report.areas.items())
        },
    }


@router.get("/report", summary="Full compliance report")
async def get_compliance_report() -> dict[str, Any]:
    """Returns the full compliance report including all requirements and evidence."""
    report = _get_report()
    return JSONResponse(content=report.to_dict())


@router.get("/matrix", summary="Traceability matrix")
async def get_traceability_matrix() -> dict[str, Any]:
    """
    Returns the full requirements -> code -> test traceability matrix.

    Also reports orphaned requirements (no evidence) and orphaned tests
    (test files with no requirement mapping).
    """
    report = _get_report()
    return build_matrix(report)


@router.get(
    "/export/markdown",
    summary="Download Markdown compliance report",
    response_class=PlainTextResponse,
)
async def export_markdown() -> PlainTextResponse:
    """Downloads the compliance report as a Markdown document."""
    report = _get_report()
    md = generate_markdown(report)
    return PlainTextResponse(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=compliance_report.md"},
    )


@router.get("/export/html", summary="Download HTML compliance report", response_class=HTMLResponse)
async def export_html() -> HTMLResponse:
    """Downloads a self-contained HTML compliance report (no external deps)."""
    report = _get_report()
    html = generate_html(report)
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": "attachment; filename=compliance_report.html"},
    )
