# src/relations/routes.py
"""HTTP routes for the AI-to-AI Relationship Matrix, Activity Feed, and
Location Brochure.

Read routes (feed, relationship lookups, brochure, insights) are
unauthenticated, matching the Role Assignment Registry's convention.
`POST /relations/events` requires an authenticated caller (any role) — it's
meant to be called by the platform's own orchestration/agent layer (or an
operator), not the public, since it's the one route that mutates state.

Handlers are plain `def`, not `async def` — see src/roles/routes.py for why
(FastAPI threadpools sync handlers instead of blocking the event loop on
the underlying synchronous SQLite calls).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user
from src.relations.registry import (
    ActivityEvent,
    LocationBrochure,
    RelationshipScore,
    get_relations_registry,
)

router = APIRouter(prefix="/relations", tags=["relations"])

_VALID_EVENT_TYPES = ("location_tag", "ai_interaction", "action", "system")
_VALID_SENTIMENTS = ("positive", "neutral", "negative")


class RecordEventRequest(BaseModel):
    actor_ai: str
    event_type: str = Field(..., description="location_tag | ai_interaction | action | system")
    location: Optional[str] = None
    target_ai: Optional[str] = None
    sentiment: str = "neutral"
    summary: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


def _serialize_score(rel: RelationshipScore) -> Dict[str, Any]:
    return {
        "ai_a": rel.ai_a,
        "ai_b": rel.ai_b,
        "score": round(rel.score, 2),
        "baseline": rel.baseline,
        "tier": rel.tier,
        "interactions_count": rel.interactions_count,
        "last_interaction_at": rel.last_interaction_at,
    }


def _serialize_event(evt: ActivityEvent) -> Dict[str, Any]:
    return {
        "id": evt.id,
        "ts": evt.ts,
        "actor_ai": evt.actor_ai,
        "event_type": evt.event_type,
        "location": evt.location,
        "target_ai": evt.target_ai,
        "sentiment": evt.sentiment,
        "summary": evt.summary,
        "details": evt.details,
    }


def _serialize_brochure(brochure: LocationBrochure) -> Dict[str, Any]:
    return {
        "location": brochure.location,
        "pillar": brochure.pillar,
        "primary_function": brochure.primary_function,
        "job_description": brochure.job_description,
        "current_resident": brochure.current_resident,
        "total_events": brochure.total_events,
        "unique_visitors": brochure.unique_visitors,
        "sentiment_counts": brochure.sentiment_counts,
        "top_visitors": brochure.top_visitors,
        "recent_highlights": [_serialize_event(e) for e in brochure.recent_highlights],
        "flavor_text": brochure.flavor_text,
    }


@router.post("/events")
def record_event(
    body: RecordEventRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    if body.event_type not in _VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"event_type must be one of {_VALID_EVENT_TYPES}",
        )
    if body.sentiment not in _VALID_SENTIMENTS:
        raise HTTPException(
            status_code=422,
            detail=f"sentiment must be one of {_VALID_SENTIMENTS}",
        )
    event = get_relations_registry().record_event(
        actor_ai=body.actor_ai,
        event_type=body.event_type,
        location=body.location,
        target_ai=body.target_ai,
        sentiment=body.sentiment,
        summary=body.summary,
        details=body.details,
    )
    return _serialize_event(event)


@router.get("/feed")
def get_feed(
    ai: Optional[str] = None,
    location: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> List[Dict[str, Any]]:
    events = get_relations_registry().get_feed(ai=ai, location=location, limit=limit)
    return [_serialize_event(e) for e in events]


@router.get("/insights")
def get_insights(
    window_days: float = Query(default=7.0, ge=0.1, le=90.0),
    limit: int = Query(default=10, ge=1, le=50),
) -> List[Dict[str, Any]]:
    insights = get_relations_registry().get_insights(window_days=window_days, limit=limit)
    return [{"kind": i.kind, "summary": i.summary, "data": i.data} for i in insights]


@router.get("/locations/{location:path}/brochure")
def get_location_brochure(location: str) -> Dict[str, Any]:
    try:
        brochure = get_relations_registry().get_location_brochure(location)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from None
    return _serialize_brochure(brochure)


@router.get("/{ai_a}/{ai_b}")
def get_pairwise_relationship(ai_a: str, ai_b: str) -> Dict[str, Any]:
    return _serialize_score(get_relations_registry().get_relationship(ai_a, ai_b))


@router.get("/{ai}")
def get_ai_relationships(ai: str) -> List[Dict[str, Any]]:
    return [_serialize_score(r) for r in get_relations_registry().list_relationships(ai)]
