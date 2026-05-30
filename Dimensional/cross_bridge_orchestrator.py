"""
Tranc3 Cross-Bridge Orchestrator
=================================
Coordinated workflows spanning all three bridges (InfinityBridge, Nexus, HIVE)
with saga/compensation pattern for rollback and step execution.

Architecture:
    - BridgeDispatcher: Routes commands to the correct bridge
    - StepExecutor: Executes individual workflow steps with retry
    - CompensationManager: Rolls back compensatable steps on failure
    - CrossBridgeOrchestrator: Top-level orchestrator for cross-bridge workflows
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class BridgeTarget(str, Enum):
    """Target bridge for a workflow step."""

    INFINITY = "infinity"
    NEXUS = "nexus"
    HIVE = "hive"


class StepStatus(str, Enum):
    """Status of a workflow step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"
    COMPENSATING = "compensating"


class WorkflowStatus(str, Enum):
    """Status of an orchestration workflow."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────


class OrchestrationStep(BaseModel):
    """A single step in a cross-bridge orchestration workflow."""

    step_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    bridge: BridgeTarget
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    compensation_action: Optional[str] = None
    compensation_payload: Dict[str, Any] = Field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 3
    timeout_seconds: float = 30.0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None


class OrchestrationWorkflow(BaseModel):
    """A cross-bridge orchestration workflow with ordered steps."""

    workflow_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str
    steps: List[OrchestrationStep] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────
# Bridge Dispatcher
# ──────────────────────────────────────────────


class BridgeDispatcher:
    """Dispatches commands to the appropriate bridge."""

    def __init__(self) -> None:
        self._handlers: Dict[BridgeTarget, Callable] = {}

    def register_handler(self, bridge: BridgeTarget, handler: Callable) -> None:
        """Register a handler function for a bridge target."""
        self._handlers[bridge] = handler

    def unregister_handler(self, bridge: BridgeTarget) -> None:
        """Remove a handler for a bridge target."""
        self._handlers.pop(bridge, None)

    async def dispatch(
        self, bridge: BridgeTarget, action: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch a command to the appropriate bridge handler."""
        handler = self._handlers.get(bridge)
        if handler is None:
            # Simulated response when no handler registered
            return {
                "bridge": bridge.value,
                "action": action,
                "status": "simulated",
                "simulated": True,
                "payload": payload,
            }
        if asyncio.iscoroutinefunction(handler):
            return await handler(action, payload)
        return handler(action, payload)

    def has_handler(self, bridge: BridgeTarget) -> bool:
        """Check if a handler is registered for a bridge."""
        return bridge in self._handlers

    def get_registered_bridges(self) -> List[BridgeTarget]:
        """Get list of bridges with registered handlers."""
        return list(self._handlers.keys())


# ──────────────────────────────────────────────
# Step Executor
# ──────────────────────────────────────────────


class StepExecutor:
    """Executes individual workflow steps with retry logic."""

    def __init__(self, dispatcher: BridgeDispatcher) -> None:
        self._dispatcher = dispatcher

    async def execute(self, step: OrchestrationStep) -> OrchestrationStep:
        """Execute a single workflow step with retry logic."""
        step.status = StepStatus.RUNNING
        last_error = None

        for attempt in range(step.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._dispatcher.dispatch(step.bridge, step.action, step.payload),
                    timeout=step.timeout_seconds,
                )
                # If simulated dispatch with error, still treat as success
                # (the bridge simulated the response)
                if result.get("error") and not result.get("simulated"):
                    raise RuntimeError(result["error"])

                step.status = StepStatus.COMPLETED
                step.result = result
                step.retries = attempt
                step.completed_at = datetime.now(timezone.utc).isoformat()
                return step

            except asyncio.TimeoutError:
                last_error = f"Step {step.name} timed out after {step.timeout_seconds}s"
                logger.warning(last_error)
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Step {step.name} attempt {attempt + 1} failed: {last_error}")

        step.status = StepStatus.FAILED
        step.error = last_error
        step.retries = step.max_retries
        return step


# ──────────────────────────────────────────────
# Compensation Manager
# ──────────────────────────────────────────────


class CompensationManager:
    """Manages saga compensation for failed workflows."""

    def __init__(self, dispatcher: BridgeDispatcher) -> None:
        self._dispatcher = dispatcher

    async def compensate(self, workflow: OrchestrationWorkflow) -> OrchestrationWorkflow:
        """Execute compensation actions for completed steps in reverse order."""
        workflow.status = WorkflowStatus.COMPENSATING

        # Find completed steps with compensation actions, in reverse order
        compensatable_steps = [
            step
            for step in reversed(workflow.steps)
            if step.status == StepStatus.COMPLETED and step.compensation_action
        ]

        if not compensatable_steps:
            # No compensatable steps — return workflow unchanged
            return workflow

        all_compensated = True
        for step in compensatable_steps:
            step.status = StepStatus.COMPENSATING
            try:
                result = await self._dispatcher.dispatch(
                    step.bridge,
                    step.compensation_action,
                    step.compensation_payload,
                )
                step.status = StepStatus.COMPENSATED
                step.result = result
                logger.info(f"Compensated step {step.name}")
            except Exception as e:
                logger.error(f"Compensation failed for step {step.name}: {e}")
                all_compensated = False

        if all_compensated:
            workflow.status = WorkflowStatus.COMPENSATED
        else:
            workflow.status = WorkflowStatus.FAILED

        return workflow


# ──────────────────────────────────────────────
# Cross-Bridge Orchestrator
# ──────────────────────────────────────────────


class CrossBridgeOrchestrator:
    """Top-level orchestrator for cross-bridge workflows."""

    def __init__(self) -> None:
        self._dispatcher = BridgeDispatcher()
        self._executor = StepExecutor(self._dispatcher)
        self._compensation = CompensationManager(self._dispatcher)
        self._workflows: Dict[str, OrchestrationWorkflow] = {}
        self._running = False

    def register_handler(self, bridge: BridgeTarget, handler: Callable) -> None:
        """Register a handler for a bridge target."""
        self._dispatcher.register_handler(bridge, handler)

    def unregister_handler(self, bridge: BridgeTarget) -> None:
        """Unregister a handler for a bridge target."""
        self._dispatcher.unregister_handler(bridge)

    async def execute(self, workflow: OrchestrationWorkflow) -> OrchestrationWorkflow:
        """Execute a workflow sequentially, with compensation on failure."""
        self._workflows[workflow.workflow_id] = workflow
        workflow.status = WorkflowStatus.RUNNING

        for step in workflow.steps:
            step = await self._executor.execute(step)

            if step.status == StepStatus.FAILED:
                workflow.error = step.error
                workflow = await self._compensation.compensate(workflow)
                workflow.completed_at = datetime.now(timezone.utc).isoformat()
                return workflow

        workflow.status = WorkflowStatus.COMPLETED
        workflow.completed_at = datetime.now(timezone.utc).isoformat()
        return workflow

    async def execute_parallel(self, workflow: OrchestrationWorkflow) -> OrchestrationWorkflow:
        """Execute all workflow steps in parallel."""
        self._workflows[workflow.workflow_id] = workflow
        workflow.status = WorkflowStatus.RUNNING

        tasks = [self._executor.execute(step) for step in workflow.steps]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        failed = False
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                workflow.steps[i].status = StepStatus.FAILED
                workflow.steps[i].error = str(result)
                failed = True
            else:
                workflow.steps[i] = result
                if workflow.steps[i].status == StepStatus.FAILED:
                    failed = True

        if failed:
            workflow = await self._compensation.compensate(workflow)
        else:
            workflow.status = WorkflowStatus.COMPLETED

        workflow.completed_at = datetime.now(timezone.utc).isoformat()
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[OrchestrationWorkflow]:
        """Get a workflow by ID."""
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> List[OrchestrationWorkflow]:
        """List all workflows."""
        return list(self._workflows.values())

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status."""
        return {
            "running": self._running,
            "total_workflows": len(self._workflows),
            "registered_bridges": [b.value for b in self._dispatcher.get_registered_bridges()],
        }

    async def start(self) -> None:
        """Start the orchestrator."""
        self._running = True

    async def stop(self) -> None:
        """Stop the orchestrator."""
        self._running = False


# ──────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────

_orchestrator: Optional[CrossBridgeOrchestrator] = None


def get_orchestrator() -> CrossBridgeOrchestrator:
    """Get or create the global CrossBridgeOrchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = CrossBridgeOrchestrator()
    return _orchestrator
