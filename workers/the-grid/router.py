"""The Digital Grid — FastAPI routes"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from models import EngineType, WorkflowDefinition
from service import WorkflowEngineRouter

import config
from database import GridDatabase


def _make_router(db: GridDatabase, engine_router: WorkflowEngineRouter) -> APIRouter:
    async def _auth(
        x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
    ) -> None:
        if not config.INTERNAL_SECRET:
            return
        if x_internal_secret != config.INTERNAL_SECRET:
            raise HTTPException(401, "Invalid or missing X-Internal-Secret header")

    router = APIRouter(dependencies=[Depends(_auth)])

    # ── Engine status ─────────────────────────────────────────────────────────

    @router.get("/engines")
    async def list_engine_statuses():
        """Return health, pheromone, and threshold info for all 8 engines."""
        return {"engines": [s.model_dump() for s in engine_router.engine_statuses()]}

    # ── Workflow Definitions ──────────────────────────────────────────────────

    @router.post("/workflows")
    def create_workflow(wf: WorkflowDefinition):
        saved = db.save_definition(wf)
        return {"ok": True, "workflow_id": saved.workflow_id}

    @router.get("/workflows")
    def list_workflows(limit: int = 50, offset: int = 0):
        return {"workflows": db.list_definitions(limit=limit, offset=offset)}

    @router.get("/workflows/{workflow_id}")
    def get_workflow(workflow_id: str):
        wf = db.get_definition(workflow_id)
        if not wf:
            raise HTTPException(404, f"Workflow not found: {workflow_id}")
        return wf

    @router.delete("/workflows/{workflow_id}")
    def delete_workflow(workflow_id: str):
        if not db.delete_definition(workflow_id):
            raise HTTPException(404, f"Workflow not found: {workflow_id}")
        return {"ok": True, "deleted": workflow_id}

    # ── Workflow Executions ───────────────────────────────────────────────────

    @router.post("/workflows/{workflow_id}/execute")
    async def execute_workflow(
        workflow_id: str,
        input_data: Optional[Dict[str, Any]] = None,
        engine: Optional[EngineType] = None,
    ):
        """Execute a workflow via the 8-tier adaptive engine router."""
        row = db.get_definition(workflow_id)
        if not row:
            raise HTTPException(404, f"Workflow not found: {workflow_id}")

        import json

        from models import WorkflowStep

        steps = [WorkflowStep(**s) for s in json.loads(row["steps"] or "[]")]
        metadata = json.loads(row["metadata"] or "{}")
        wf_def = WorkflowDefinition(
            workflow_id=row["workflow_id"],
            name=row["name"],
            description=row.get("description", ""),
            steps=steps,
            metadata=metadata,
            version=row.get("version", 1),
            preferred_engine=engine,
        )

        execution = await engine_router.execute(wf_def, input_data or {})
        return {
            "ok": True,
            "execution_id": execution.execution_id,
            "status": execution.status.value,
            "engine_used": execution.engine_used,
        }

    @router.get("/executions")
    def list_executions(
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ):
        return {
            "executions": db.list_executions(
                workflow_id=workflow_id, status=status, limit=limit, offset=offset
            )
        }

    @router.get("/executions/{execution_id}")
    def get_execution(execution_id: str):
        ex = db.get_execution(execution_id)
        if not ex:
            raise HTTPException(404, f"Execution not found: {execution_id}")
        return ex

    return router
