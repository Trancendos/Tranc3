# src/library/routes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Path, Query
from fastapi.responses import JSONResponse

from auth import get_current_user
from src.library.knowledge_base import Article, ArticleStatus, DataClassification, get_library

router = APIRouter(prefix="/library", tags=["library"])

_RESTRICTED_CLASSIFICATIONS = frozenset(
    {DataClassification.RESTRICTED, DataClassification.TOP_SECRET}
)


def _can_read(article: Article, current_user: dict) -> bool:
    """PUBLIC/INTERNAL/CONFIDENTIAL articles are readable by any authenticated
    caller (the platform-wide auth gate already covers those). RESTRICTED and
    TOP_SECRET additionally require the caller to be an admin or the article's
    own author."""
    if article.classification not in _RESTRICTED_CLASSIFICATIONS:
        return True
    if current_user.get("role") == "admin":
        return True
    caller_id = current_user.get("id") or current_user.get("sub")
    return caller_id == article.author


@router.get("/stats")
async def library_stats():
    return get_library().stats()


@router.get("/articles")
async def list_articles(
    limit: int = Query(20, ge=1, le=200),
    tag: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    lib = get_library()
    # Overfetch to the full candidate pool before filtering by visibility, so
    # restricted articles the caller can't see don't crowd authorized ones
    # out of the truncated `limit` window.
    total = lib.count()
    if tag:
        candidates = lib.by_tag(tag, limit=total)
    else:
        st = ArticleStatus(status) if status else ArticleStatus.PUBLISHED
        candidates = lib.recent(limit=total, status=st)
    visible = [a for a in candidates if _can_read(a, current_user)]
    return [a.to_dict() for a in visible[:limit]]


@router.get("/articles/search")
async def search_articles(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    lib = get_library()
    total = lib.count()
    candidates = lib.search(q, limit=total)
    visible = [a for a in candidates if _can_read(a, current_user)]
    return [a.to_dict() for a in visible[:limit]]


@router.get("/articles/{article_id}")
async def get_article(
    article_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
):
    art = get_library().get(article_id)
    if not art:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _can_read(art, current_user):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    return {**art.to_dict(), "body": art.body}


@router.post("/articles")
async def create_article(
    title: str = Body(...),
    body: str = Body(...),
    tags: Optional[List[str]] = Body(None),
    author: Optional[str] = Body(
        None,
        description="Only honored for admin callers; other callers always author as themselves.",
    ),
    classification: str = Body("internal"),
    retention_days: Optional[int] = Body(None, ge=0),
    current_user: dict = Depends(get_current_user),
):
    try:
        classification_enum = DataClassification(classification)
    except ValueError:
        valid = [c.value for c in DataClassification]
        return JSONResponse({"error": f"Unknown classification. Valid: {valid}"}, status_code=400)
    caller_id = current_user.get("id") or current_user.get("sub") or "system"
    resolved_author = (
        author if author is not None and current_user.get("role") == "admin" else caller_id
    )
    art = get_library().create(
        title=title,
        body=body,
        tags=tags,
        author=resolved_author,
        classification=classification_enum,
        retention_days=retention_days,
    )
    return art.to_dict()


@router.delete("/articles/{article_id}")
async def delete_article(
    article_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
):
    art = get_library().get(article_id)
    if not art:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _can_read(art, current_user):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    get_library().delete(article_id)
    return {"deleted": article_id}


@router.post("/retention/apply")
async def apply_retention(current_user: dict = Depends(get_current_user)):
    removed = get_library().apply_retention()
    return {"articles_removed": removed}
