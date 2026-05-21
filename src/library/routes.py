# src/library/routes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body, Path, Query
from fastapi.responses import JSONResponse

from src.library.knowledge_base import ArticleStatus, get_library

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/stats")
async def library_stats():
    return get_library().stats()


@router.get("/articles")
async def list_articles(
    limit: int = Query(20, ge=1, le=200),
    tag: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    lib = get_library()
    if tag:
        articles = lib.by_tag(tag, limit=limit)
    else:
        st = ArticleStatus(status) if status else ArticleStatus.PUBLISHED
        articles = lib.recent(limit=limit, status=st)
    return [a.to_dict() for a in articles]


@router.get("/articles/search")
async def search_articles(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)):
    return [a.to_dict() for a in get_library().search(q, limit=limit)]


@router.get("/articles/{article_id}")
async def get_article(article_id: str = Path(...)):
    art = get_library().get(article_id)
    if not art:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {**art.to_dict(), "body": art.body}


@router.post("/articles")
async def create_article(
    title: str = Body(...),
    body: str = Body(...),
    tags: Optional[List[str]] = Body(None),
    author: str = Body("system"),
):
    art = get_library().create(title=title, body=body, tags=tags, author=author)
    return art.to_dict()


@router.delete("/articles/{article_id}")
async def delete_article(article_id: str = Path(...)):
    if get_library().delete(article_id):
        return {"deleted": article_id}
    return JSONResponse({"error": "Not found"}, status_code=404)
