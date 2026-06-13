# src/basement/routes.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.basement.archive import ArchiveSource, get_basement

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
