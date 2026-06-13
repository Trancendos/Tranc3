# src/workflow/routes.py
# The Digital Grid — HTTP API for workflow management and execution.
#
# Routes:
#   GET  /grid/workflows          — list registered workflow definitions
#   GET  /grid/workflows/{id}     — get workflow definition
#   POST /grid/workflows          — register a new workflow (JSON body)
#   POST /grid/workflows/{id}/run — trigger execution
#   GET  /grid/executions/{id}    — execution status
#   POST /grid/executions/{id}/cancel — cancel a running execution
#   GET  /grid/status             — executor + event bus stats

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, Path
from fastapi.responses import JSONResponse

from Dimensional.error_handlers import safe_error_detail

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/grid", tags=["digital-grid"])

# ── In-process workflow registry ──────────────────────────────────────────────
_workflow_registry: Dict[str, Any] = {}  # id → WorkflowDefinition
_executor_singleton = None


def _get_executor():
    global _executor_singleton
    if _executor_singleton is None:
        from src.workflow.executor import WorkflowExecutor

        _executor_singleton = WorkflowExecutor()
    return _executor_singleton


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/status")
async def grid_status():
    """High-level status: registered workflows, active executions."""
    executor = _get_executor()
    active = {
        eid: {
            "workflow_id": state.workflow_id,
            "status": state.status,
            "elapsed_ms": round(state.elapsed_ms, 1),
        }
        for eid, state in executor._executions.items()
        if state.status in ("pending", "running")
    }
    return {
        "registered_workflows": len(_workflow_registry),
        "workflow_ids": list(_workflow_registry.keys()),
        "active_executions": len(active),
        "executions": active,
    }


@router.get("/workflows")
async def list_workflows():
    return [wf.to_dict() for wf in _workflow_registry.values()]


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str = Path(...)):
    wf = _workflow_registry.get(workflow_id)
    if not wf:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return wf.to_dict()


@router.post("/workflows")
async def register_workflow(body: Dict[str, Any] = Body(...)):
    """Register a workflow from a JSON definition dict."""
    try:
        from src.workflow.builder import WorkflowDefinition

        wf = WorkflowDefinition.from_dict(body)
    except Exception:
        return JSONResponse({"error": "Invalid workflow definition"}, status_code=400)
    _workflow_registry[wf.id] = wf
    logger.info("grid: registered workflow id=%s name=%s", wf.id, wf.name)
    try:
        from src.observability.observatory import EventCategory, observe

        observe(
            "workflow.registered",
            target=f"workflow:{wf.id}",
            category=EventCategory.WORKFLOW,
            service="grid",
            metadata={"name": wf.name, "nodes": len(wf.nodes)},
        )
    except Exception:
        pass  # nosec B110 — graceful degradation; error logged upstream

    return {"registered": wf.id, "name": wf.name}


@router.post("/workflows/{workflow_id}/run")
async def run_workflow(
    workflow_id: str = Path(...),
    inputs: Dict[str, Any] = Body(default_factory=dict),
):
    wf = _workflow_registry.get(workflow_id)
    if not wf:
        return JSONResponse({"error": "Workflow not found"}, status_code=404)
    import asyncio

    executor = _get_executor()
    try:
        state = await asyncio.wait_for(executor.execute(wf, inputs), timeout=300.0)
    except asyncio.TimeoutError:
        return JSONResponse({"error": "Workflow execution timed out"}, status_code=504)
    except Exception as exc:
        logger.error("grid: execution error workflow=%s: %s", workflow_id, exc)
        return JSONResponse({"error": safe_error_detail(exc, 500)}, status_code=500)
    return {
        "execution_id": state.execution_id,
        "workflow_id": workflow_id,
        "status": state.status,
        "elapsed_ms": round(state.elapsed_ms, 1),
        "outputs": state.node_outputs,
        "error": state.error,
    }


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str = Path(...)):
    executor = _get_executor()
    state = await executor.get_status(execution_id)
    if not state:
        return JSONResponse({"error": "Execution not found"}, status_code=404)
    return {
        "execution_id": state.execution_id,
        "workflow_id": state.workflow_id,
        "status": state.status,
        "elapsed_ms": round(state.elapsed_ms, 1),
        "node_statuses": state.node_statuses,
        "error": state.error,
    }


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str = Path(...)):
    executor = _get_executor()
    cancelled = await executor.cancel(execution_id)
    if not cancelled:
        return JSONResponse({"error": "Execution not found or already complete"}, status_code=404)
    return {"cancelled": execution_id}
