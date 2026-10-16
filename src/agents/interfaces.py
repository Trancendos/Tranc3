"""
Core interfaces for Hybrid Agent Orchestration (v0.9.0 design).

These are the foundational contracts. Concrete implementations will live in
orchestrator.py and concrete agent wrappers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TaskStatus(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Subtask:
    id: str
    description: str
    context: dict[str, Any] = field(default_factory=dict)
    required_capabilities: list[str] = field(default_factory=list)
    priority: int = 0


@dataclass
class Bid:
    agent_id: str
    confidence: float
    estimated_cost: float = 0.0
    notes: str = ""


@dataclass
class AgentResult:
    subtask_id: str
    agent_id: str
    success: bool
    output: Any
    confidence: float
    observations: list[str] = field(default_factory=list)
    routing_path: list[str] = field(default_factory=list)  # full audit trail
    error: Optional[str] = None


@dataclass
class Plan:
    goal: str
    subtasks: list[Subtask]
    metadata: dict[str, Any] = field(default_factory=dict)


class Orchestrator(ABC):
    """Thin orchestrator that owns planning, sequencing and final responsibility."""

    @abstractmethod
    def create_plan(self, goal: str, context: dict[str, Any] | None = None) -> Plan:
        ...

    @abstractmethod
    def broadcast_subtasks(self, plan: Plan) -> None:
        ...

    @abstractmethod
    def on_agent_result(self, result: AgentResult) -> None:
        ...

    @abstractmethod
    def should_replan(self) -> bool:
        ...

    @abstractmethod
    def replan(self) -> Plan:
        ...


class Agent(ABC):
    """Specialist agent with autonomy to accept, decline or invent helper roles."""

    agent_id: str
    capabilities: list[str]

    @abstractmethod
    def can_handle(self, subtask: Subtask) -> bool | Bid:
        ...

    @abstractmethod
    def accept(self, subtask: Subtask) -> None:
        ...

    @abstractmethod
    def decline(self, subtask: Subtask, reason: str) -> None:
        ...

    @abstractmethod
    def invent_helper_role(self, need: str) -> "Agent":
        ...

    @abstractmethod
    def execute(self, subtask: Subtask) -> AgentResult:
        ...

    @abstractmethod
    def reflect(self) -> dict[str, Any]:
        ...
