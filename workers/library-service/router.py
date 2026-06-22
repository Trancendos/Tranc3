"""The Library — FastAPI router"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from models import (
    DocumentCreate,
    DocumentResponse,
    LibraryStatus,
    SearchRequest,
    SearchResponse,
)
from service import LibraryRouter

import config
from database import LibraryDatabase


def _auth(x_internal_secret: Optional[str] = Header(None)) -> None:
    if not config.INTERNAL_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="INTERNAL_SECRET not configured"
        )
    if x_internal_secret != config.INTERNAL_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal secret"
        )


def _make_library_router(db: LibraryDatabase, router_svc: LibraryRouter) -> APIRouter:
    api = APIRouter(prefix="/library", tags=["library"])

    @api.post(
        "/documents",
        response_model=DocumentResponse,
        status_code=201,
        dependencies=[Depends(_auth)],
    )
    async def create_document(doc: DocumentCreate):
        return await router_svc.create_document(doc)

    @api.get("/documents/{doc_id}", response_model=DocumentResponse, dependencies=[Depends(_auth)])
    async def get_document(doc_id: str):
        result = await router_svc.get_document(doc_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return result

    @api.post("/search", response_model=SearchResponse, dependencies=[Depends(_auth)])
    async def search(req: SearchRequest):
        return await router_svc.search(req.query, req.collection, req.limit)

    @api.get("/status", response_model=LibraryStatus)
    async def get_status():
        return router_svc.status()

    return api
