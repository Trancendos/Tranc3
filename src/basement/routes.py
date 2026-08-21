# src/basement/routes.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from auth import get_current_user
from src.basement.archive import ArchiveSource, get_basement
from src.basement.promotion import promote as promote_patterns

router = APIRouter(prefix="/basement", tags=["basement"])


@router.get("/stats")
async def basement_stats():
    return get_basement().stats()


@router.get("/records")
async def list_records(
    limit: int = Query(50, ge=1, le=500),
    source: Optional[str] = Query(None),
):
    bm = get_basement()
    if source:
        try:
            src = ArchiveSource(source)
        except ValueError:
            return JSONResponse({"error": f"Unknown source: {source}"}, status_code=400)
        records = bm.by_source(src, limit=limit)
    else:
        records = bm.recent(limit=limit)
    return [r.to_dict() for r in records]


@router.get("/search")
async def search_archive(q: str = Query(..., min_length=1), top_k: int = Query(10, ge=1, le=50)):
    results = get_basement().search(q, top_k=top_k)
    return [{"record": r.to_dict(), "score": round(score, 4)} for r, score in results]


@router.get("/records/{record_id}")
async def get_record(record_id: str):
    r = get_basement().get(record_id)
    if not r:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {**r.to_dict(), "content": r.content}


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Promotion writes into The Library, so it is an admin action.

    Matching the guard on `/admin-os`: a read of the evidence store is open to
    any authenticated caller, but authoring knowledge from it is not.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


@router.post("/promote", dependencies=[Depends(_require_admin)])
def run_promotion(
    limit: int = Query(default=500, ge=1, le=5000),
    dry_run: bool = Query(default=False),
):
    """Scan Basement evidence and raise a Library draft per confirmed pattern.

    `src/basement/promotion.py` has implemented this whole path -- clustering,
    regression detection, article rendering -- since it was written, and until
    now nothing called it. The module's own docstring describes closing "the
    fourth leg" of Chaos Party -> Observatory -> Basement -> Library; the leg
    was built and left with no entry point, so evidence accumulated in the
    store and reached nobody.

    `dry_run=true` reports the patterns it would raise without writing, which is
    the mode to use when tuning thresholds against real evidence.
    """
    return promote_patterns(limit=limit, dry_run=dry_run)
