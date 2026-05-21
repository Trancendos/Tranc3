# src/research/routes.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.research.section7 import ReportType, get_section7

router = APIRouter(prefix="/section7", tags=["section7"])


@router.get("/stats")
async def section7_stats():
    return get_section7().stats()


@router.get("/reports")
async def list_reports(
    limit: int = Query(10, ge=1, le=50),
    report_type: Optional[str] = Query(None),
):
    rt = None
    if report_type:
        try:
            rt = ReportType(report_type)
        except ValueError:
            return JSONResponse({"error": f"Unknown report type: {report_type}"}, status_code=400)
    reports = get_section7().recent(limit=limit, report_type=rt)
    return [r.to_dict() for r in reports]


@router.get("/reports/{report_id}")
async def get_report(report_id: str):
    r = get_section7().get(report_id)
    if not r:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return r.to_dict()


@router.post("/reports/platform-health")
async def run_platform_health():
    """Generate a live platform health report across all active services."""
    report = get_section7().generate_platform_health_report()
    return report.to_dict()


@router.post("/reports/security")
async def run_security_report():
    """Generate a security intelligence report from Cryptex + Observatory."""
    report = get_section7().generate_security_report()
    return report.to_dict()
