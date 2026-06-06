"""
Monitoring API Routes — Zero-Cost Usage Endpoints
==================================================
FastAPI router exposing zero-cost usage tracking endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.monitoring.zero_cost_tracker import tracker

router = APIRouter(prefix="/monitoring")


class RecordUsageRequest(BaseModel):
    service: str
    metric: str
    value: float


@router.get("/zero-cost", summary="Zero-cost usage summary")
def get_zero_cost_summary() -> dict:
    """Return aggregate summary of free-tier usage across all services."""
    return tracker.get_summary()


@router.get("/zero-cost/alerts", summary="Services near free-tier limit")
def get_zero_cost_alerts(threshold: float = 80.0) -> dict:
    """Return services that have exceeded the usage threshold percentage."""
    alerts = tracker.check_alerts(threshold_pct=threshold)
    return {"threshold_pct": threshold, "alert_count": len(alerts), "alerts": alerts}


@router.get("/zero-cost/{service}", summary="Per-service usage")
def get_service_usage(service: str) -> list:
    """Return all tracked metrics for a specific service."""
    from src.monitoring.zero_cost_tracker import FREE_TIER_LIMITS

    if service not in FREE_TIER_LIMITS:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{service}' not tracked. Known services: {list(FREE_TIER_LIMITS)}",
        )
    records = tracker.get_usage(service)
    return [
        {
            "metric": r.metric,
            "current_usage": r.current_usage,
            "limit": r.limit,
            "percentage_used": r.percentage_used,
            "reset_period": r.reset_period,
            "last_updated": r.last_updated,
        }
        for r in records
    ]


@router.post("/zero-cost/record", summary="Record a usage event")
def record_usage_event(req: RecordUsageRequest) -> dict:
    """Record a usage increment for the given service and metric."""
    from src.monitoring.zero_cost_tracker import FREE_TIER_LIMITS

    if req.service not in FREE_TIER_LIMITS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown service '{req.service}'",
        )
    if req.metric not in FREE_TIER_LIMITS.get(req.service, {}):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown metric '{req.metric}' for service '{req.service}'",
        )
    tracker.record_usage(req.service, req.metric, req.value)
    return {"ok": True, "service": req.service, "metric": req.metric, "added": req.value}


__all__ = ["router"]
