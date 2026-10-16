# Hybrid Agent Orchestration Architecture

**Status**: Design for v0.9.0 MVP  
**Location**: `src/agents/`

---

## 1. Design Goals

- Keep a **thin Orchestrator** that owns high-level planning and final responsibility.
- Give specialist agents **real autonomy** (accept / decline / invent short-lived helper roles).
- Trigger re-planning on **events or observation staleness** rather than continuous re-reasoning.
- Maintain a full **routing / audit path** for every decision.
- Work cleanly with the existing MCP tool registry and worker set.

This hybrid style (light structure + meaningful autonomy) is supported by recent multi-agent research.

---

## 2. High-Level Architecture

```
User / External Goal
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│              Thin Orchestrator (Squad Leader)               │
│  • create_plan()                                            │
│  • broadcast_subtasks()                                     │
│  • on_agent_result()                                        │
│  • should_replan() / replan()                               │
│  • owns final responsibility + audit log                    │
└───────────────────────────────────────────────────────────┴──────────────────────────────────────────────────────────┐
             │                               │
             ▼                               ▼
┌───────────────────────────┐   ┌───────────────────────────┐
│   Specialist Agents /      │   │   Worker Groups /          │
│   Role-capable Agents      │   │   MCP Tool Clusters        │
│                            │   │                            │
│  • can_handle() / Bid      │   │  • execute tools           │
│  • accept / decline        │   │  • report results + conf.  │
│  • invent_helper_role()    │   │  • request help            │
│  • execute + reflect       │   │                            │
└───────────────────────────┴──────────────────────────────────────────────────────────┐
                             │
                             ▼
              Reflection & Re-planning Loop
              (event-triggered or staleness-based)
```

---

## 3. Core Interfaces (Python)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

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
    @abstractmethod
    def create_plan(self, goal: str, context: dict[str, Any] | None = None) -> Plan: ...

    @abstractmethod
    def broadcast_subtasks(self, plan: Plan) -> None: ...

    @abstractmethod
    def on_agent_result(self, result: AgentResult) -> None: ...

    @abstractmethod
    def should_replan(self) -> bool: ...

    @abstractmethod
    def replan(self) -> Plan: ...

class Agent(ABC):
    agent_id: str
    capabilities: list[str]

    @abstractmethod
    def can_handle(self, subtask: Subtask) -> bool | Bid: ...

    @abstractmethod
    def accept(self, subtask: Subtask) -> None: ...

    @abstractmethod
    def decline(self, subtask: Subtask, reason: str) -> None: ...

    @abstractmethod
    def invent_helper_role(self, need: str) -> "Agent": ...

    @abstractmethod
    def execute(self, subtask: Subtask) -> AgentResult: ...

    @abstractmethod
    def reflect(self) -> dict[str, Any]: ...
```

---

## 4. Sequence (Happy Path)

1. User submits goal.
2. Orchestrator.create_plan(goal) → Plan with ordered/parallel Subtasks.
3. Orchestrator.broadcast_subtasks(plan).
4. Each interested Agent calls can_handle() and returns Bid or False.
5. Orchestrator assigns (or agents self-accept).
6. Agents execute (possibly inventing short-lived helpers).
7. Each Agent returns AgentResult including full routing_path.
8. Orchestrator.on_agent_result() updates state.
9. If should_replan() (staleness or failure event) → replan and continue.
10. When all critical subtasks succeed → final result returned to user.

---

## 5. Implementation Notes for v0.9.0 MVP

- Place core interfaces in `src/agents/interfaces.py`.
- Implement a simple `SimpleOrchestrator` in `src/agents/orchestrator.py`.
- Existing workers can be wrapped as Agents.
- Log every routing decision for auditability.
- Start with sequential + limited parallel execution; expand later.
