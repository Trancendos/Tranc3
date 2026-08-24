"""The Lab — FastAPI routes"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from service import LabRouter

import config
from database import LabDatabase
from Dimensional.service_auth_fastapi import guard_internal_secret
from models import CodeRequest, CodeResponse, LabStatus

logger = logging.getLogger(config.WORKER_NAME)


def _auth(x_internal_secret: Optional[str] = Header(default=None)) -> None:
    guard_internal_secret(
        x_internal_secret, config.INTERNAL_SECRET, mismatch_status=403, detail="Forbidden"
    )


def _make_lab_router(db: LabDatabase, lab: LabRouter) -> APIRouter:
    router = APIRouter(prefix="/lab", tags=["lab"])

    @router.post("/generate", response_model=CodeResponse)
    async def generate(req: CodeRequest, _: None = Depends(_auth)):
        response = await lab.generate(req)
        db.save_request(
            {
                "request_id": response.request_id,
                "prompt": req.prompt,
                "language": req.language,
                "task_type": response.task_type.value,
                "backend": response.backend.value,
                "result": response.result,
                "tokens_used": response.tokens_used,
                "latency_ms": response.latency_ms,
                "metadata": req.metadata,
            }
        )
        db.record_event(response.backend.value, True)
        return response

    @router.get("/status", response_model=LabStatus)
    async def status(_: None = Depends(_auth)):
        return lab.status()

    @router.get("/history", response_model=List[dict])
    async def history(
        backend: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        _: None = Depends(_auth),
    ):
        return db.list_requests(backend=backend, limit=limit, offset=offset)

    @router.get("/request/{request_id}", response_model=dict)
    async def get_request(request_id: str, _: None = Depends(_auth)):
        record = db.get_request(request_id)
        if not record:
            raise HTTPException(status_code=404, detail="Request not found")
        return record

    return router
