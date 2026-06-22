"""The Digital Grid — Pydantic models and enums"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    paused = "paused"


class StepStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class EngineType(str, Enum):
    internal = "internal"    # built-in Python DAG executor (Tier 1)
    n8n = "n8n"              # n8n REST API           (Tier 2)
    prefect = "prefect"      # Prefect server API     (Tier 3)
    temporal = "temporal"    # Temporal gRPC          (Tier 4)
    airflow = "airflow"      # Apache Airflow REST    (Tier 5)
    dagster = "dagster"      # Dagster GraphQL        (Tier 6)
    luigi = "luigi"          # Luigi in-process       (Tier 7)
    offline = "offline"      # deterministic stub     (Tier 8)


class WorkflowStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    action: str
    config: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 300


class WorkflowDefinition(BaseModel):
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    steps: List[WorkflowStep]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    preferred_engine: Optional[EngineType] = None


class WorkflowExecution(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.pending
    engine_used: Optional[str] = None
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    step_results: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EngineStatus(BaseModel):
    engine: str
    healthy: bool
    pheromone: float
    requests_in_window: int
    threshold: int
    blocked: bool
    last_checked: Optional[str] = None
