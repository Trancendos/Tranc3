"""
DNF Python SDK — Distributed Nano-Flows
========================================
Python client SDK for defining, registering, and executing
distributed nano-flows. Replaces cloud FaaS with local event loops.

Architecture:
  - FlowBuilder: fluent API for constructing flow DAGs
  - FlowRunner: async execution engine with step handlers
  - FlowRegistry: versioned flow definition storage
  - Integration with NSA for nanoservice discovery
  - Integration with genetic optimizer for adaptive routing

Zero-cost: pure Python asyncio, no cloud dependencies.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set


class FlowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    MERGED = "merged"


class StepStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


StepHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]


@dataclass
class FlowStep:
    """A single step in a flow DAG."""

    id: str
    name: str
    service_name: str = ""
    capability: str = ""
    timeout_ms: int = 30000
    retry_count: int = 0
    retry_delay_ms: int = 1000
    depends_on: List[str] = field(default_factory=list)
    condition: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "service_name": self.service_name,
            "capability": self.capability,
            "timeout_ms": self.timeout_ms,
            "retry_count": self.retry_count,
            "retry_delay_ms": self.retry_delay_ms,
            "depends_on": self.depends_on,
            "condition": self.condition,
            "properties": self.properties,
        }


@dataclass
class StepResult:
    """Result of a step execution."""

    step_id: str
    status: StepStatus = StepStatus.IDLE
    output: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    duration_ms: float = 0.0
    retries: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "retries": self.retries,
        }


@dataclass
class FlowDefinition:
    """Complete flow DAG definition."""

    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    steps: List[FlowStep] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    tier: int = 2
    properties: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Flow must have an ID")
        if not self.steps:
            raise ValueError("Flow must have at least one step")
        step_ids = {s.id for s in self.steps}
        if len(step_ids) != len(self.steps):
            raise ValueError("Duplicate step IDs")
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise ValueError(f"Step {step.id} depends on unknown step {dep}")

    def root_steps(self) -> List[FlowStep]:
        return [s for s in self.steps if not s.depends_on]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "tags": self.tags,
            "tier": self.tier,
            "properties": self.properties,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class FlowExecution:
    """Running instance of a flow."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    flow_id: str = ""
    flow_version: str = ""
    status: FlowStatus = FlowStatus.PENDING
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    input: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str = ""
    parent_flow_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "flow_id": self.flow_id,
            "flow_version": self.flow_version,
            "status": self.status.value,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "input": self.input,
            "output": self.output,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "parent_flow_id": self.parent_flow_id,
        }


class FlowBuilder:
    """Fluent API for constructing flow definitions."""

    def __init__(self, flow_id: str, name: str):
        self._def = FlowDefinition(id=flow_id, name=name)

    def version(self, version: str) -> "FlowBuilder":
        self._def.version = version
        return self

    def description(self, desc: str) -> "FlowBuilder":
        self._def.description = desc
        return self

    def tier(self, tier: int) -> "FlowBuilder":
        self._def.tier = tier
        return self

    def tag(self, *tags: str) -> "FlowBuilder":
        self._def.tags.extend(tags)
        return self

    def step(
        self,
        step_id: str,
        name: str,
        service_name: str = "",
        capability: str = "",
        timeout_ms: int = 30000,
        retry_count: int = 0,
        retry_delay_ms: int = 1000,
        depends_on: Optional[List[str]] = None,
        condition: str = "",
        **properties: Any,
    ) -> "FlowBuilder":
        s = FlowStep(
            id=step_id,
            name=name,
            service_name=service_name,
            capability=capability,
            timeout_ms=timeout_ms,
            retry_count=retry_count,
            retry_delay_ms=retry_delay_ms,
            depends_on=depends_on or [],
            condition=condition,
            properties=properties,
        )
        self._def.steps.append(s)
        return self

    def build(self) -> FlowDefinition:
        self._def.validate()
        return self._def


class FlowRunner:
    """Async execution engine for nano-flows."""

    def __init__(self, max_concurrent: int = 100):
        self._handlers: Dict[str, StepHandler] = {}
        self._executions: Dict[str, FlowExecution] = {}
        self._definitions: Dict[str, FlowDefinition] = {}
        self._event_handlers: List[Callable] = []
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._completed_count = 0
        self._failed_count = 0

    def register_handler(self, step_name: str, handler: StepHandler) -> None:
        self._handlers[step_name] = handler

    def register_flow(self, definition: FlowDefinition) -> None:
        definition.validate()
        self._definitions[definition.id] = definition

    def on_event(self, handler: Callable) -> None:
        self._event_handlers.append(handler)

    async def execute(
        self,
        flow_id: str,
        input_data: Optional[Dict[str, Any]] = None,
    ) -> FlowExecution:
        definition = self._definitions.get(flow_id)
        if not definition:
            raise ValueError(f"Flow not found: {flow_id}")

        execution = FlowExecution(
            flow_id=flow_id,
            flow_version=definition.version,
            input=input_data or {},
            started_at=time.time(),
        )
        self._executions[execution.id] = execution

        await self._emit("started", execution)

        try:
            execution.status = FlowStatus.RUNNING
            await self._emit("running", execution)
            await self._run_flow(definition, execution)

            if execution.status == FlowStatus.RUNNING:
                execution.status = FlowStatus.COMPLETED
                self._completed_count += 1
                await self._emit("completed", execution)

        except Exception as e:
            execution.status = FlowStatus.FAILED
            execution.error = str(e)
            self._failed_count += 1
            await self._emit("failed", execution)

        execution.completed_at = time.time()
        return execution

    async def get_execution(self, exec_id: str) -> Optional[FlowExecution]:
        return self._executions.get(exec_id)

    async def list_executions(self) -> List[FlowExecution]:
        return list(self._executions.values())

    async def pause(self, exec_id: str) -> None:
        exec_obj = self._executions.get(exec_id)
        if exec_obj and exec_obj.status == FlowStatus.RUNNING:
            exec_obj.status = FlowStatus.PAUSED
            await self._emit("paused", exec_obj)

    async def cancel(self, exec_id: str) -> None:
        exec_obj = self._executions.get(exec_id)
        if exec_obj:
            exec_obj.status = FlowStatus.CANCELLED
            exec_obj.completed_at = time.time()
            await self._emit("cancelled", exec_obj)

    def stats(self) -> Dict[str, Any]:
        status_counts: Dict[str, int] = {}
        for e in self._executions.values():
            s = e.status.value
            status_counts[s] = status_counts.get(s, 0) + 1
        return {
            "total_executions": len(self._executions),
            "by_status": status_counts,
            "completed": self._completed_count,
            "failed": self._failed_count,
            "registered_flows": len(self._definitions),
            "registered_handlers": len(self._handlers),
        }

    async def _run_flow(self, definition: FlowDefinition, execution: FlowExecution) -> None:
        completed: Set[str] = set()

        while len(completed) < len(definition.steps):
            ready = []
            for step in definition.steps:
                if step.id in completed:
                    continue
                if (
                    step.id in execution.step_results
                    and execution.step_results[step.id].status == StepStatus.RUNNING
                ):
                    continue
                deps_met = all(dep in completed for dep in step.depends_on)
                if deps_met and step.id not in completed:
                    # Check if dep failed
                    deps_failed = any(
                        execution.step_results.get(dep)
                        and execution.step_results[dep].status == StepStatus.FAILED
                        for dep in step.depends_on
                    )
                    if deps_failed:
                        execution.step_results[step.id] = StepResult(
                            step_id=step.id,
                            status=StepStatus.SKIPPED,
                            error="dependency failed",
                        )
                        completed.add(step.id)
                        continue
                    ready.append(step)

            if not ready:
                all_done = all(s.id in completed for s in definition.steps)
                if all_done:
                    break
                await asyncio.sleep(0.01)
                continue

            tasks = [self._run_step(step, definition, execution) for step in ready]
            await asyncio.gather(*tasks)
            for step in ready:
                completed.add(step.id)

        # Collect outputs
        for step in definition.steps:
            result = execution.step_results.get(step.id)
            if result and result.status == StepStatus.SUCCESS:
                for k, v in result.output.items():
                    execution.output[f"{step.id}.{k}"] = v

    async def _run_step(
        self,
        step: FlowStep,
        definition: FlowDefinition,
        execution: FlowExecution,
    ) -> None:
        result = StepResult(step_id=step.id, status=StepStatus.RUNNING, started_at=time.time())
        execution.step_results[step.id] = result

        handler = self._handlers.get(step.name)
        if not handler:
            result.status = StepStatus.FAILED
            result.error = f"No handler for step: {step.name}"
            result.ended_at = time.time()
            result.duration_ms = (result.ended_at - result.started_at) * 1000
            return

        # Build input
        step_input = dict(execution.input)
        for dep_id in step.depends_on:
            dep_result = execution.step_results.get(dep_id)
            if dep_result and dep_result.status == StepStatus.SUCCESS:
                for k, v in dep_result.output.items():
                    step_input[f"{dep_id}.{k}"] = v
        step_input.update(step.properties)

        # Execute with retries
        last_error = None
        for attempt in range(step.retry_count + 1):
            try:
                async with self._semaphore:
                    if step.timeout_ms > 0:
                        output = await asyncio.wait_for(
                            handler(step_input),
                            timeout=step.timeout_ms / 1000.0,
                        )
                    else:
                        output = await handler(step_input)

                result.output = output
                result.status = StepStatus.SUCCESS
                result.error = ""
                break

            except asyncio.TimeoutError:
                last_error = f"Timeout after {step.timeout_ms}ms"
                result.retries = attempt
            except Exception as e:
                last_error = str(e)
                result.retries = attempt

            if attempt < step.retry_count:
                await asyncio.sleep(step.retry_delay_ms / 1000.0)
                result.status = StepStatus.RETRYING

        if result.status != StepStatus.SUCCESS:
            result.status = StepStatus.FAILED
            result.error = last_error or "Unknown error"

        result.ended_at = time.time()
        result.duration_ms = (result.ended_at - result.started_at) * 1000

    async def _emit(self, event: str, execution: FlowExecution) -> None:
        for handler in self._event_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event, execution)
                else:
                    handler(event, execution)
            except Exception:
                pass
