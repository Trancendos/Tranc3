"""
Agent Orchestrator — Multi-Agent Task Queue with SQLite Persistence
===================================================================
Registers agents, queues tasks, tracks status, and measures performance.
Provides a simple in-memory priority queue with SQLite persistence.

Inspired by: @trancendos/agent-sdk agent-orchestrator.ts (infinity-adminOS)
Zero-cost: Pure Python asyncio + sqlite3. No external dependencies.

Tier 4 dispatch is gated by the AI Governance Constitution's escalation FSM
(src/compliance/escalation_fsm.py, Phase 3) — see submit_task() below.
"""

from __future__ import annotations

import asyncio
import heapq
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.compliance.escalation_fsm import ActionRequest, get_escalation_fsm
from src.database.encrypted_sqlite import connect as sqlite3_connect

# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class AgentConfig:
    """Static configuration for a registered agent."""

    id: str
    name: str
    role: str
    tools: list[str] = field(default_factory=list)
    max_concurrent_tasks: int = 5
    priority: int = 5  # 0-10
    domain: str = "unassigned"  # PrimeDomain slug — resolves the agent's charter (Phase 3)


@dataclass
class AgentTask:
    """A unit of work submitted to an agent."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    description: str = ""
    action: str = (
        ""  # charter-matched verb (e.g. "read_approved_documents"); falls back to description
    )
    priority: int = 5  # 0-10
    # pending|running|completed|failed|pending_governance|blocked_governance
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    escalation_record_id: Optional[str] = None


@dataclass
class AgentPerformance:
    """Aggregate performance metrics for an agent."""

    agent_id: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    avg_duration_ms: float = 0.0
    success_rate: float = 0.0


# ── Database helpers ──────────────────────────────────────────────────────────


def _ensure_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3_connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_tasks (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            description TEXT,
            action TEXT DEFAULT '',
            priority INTEGER DEFAULT 5,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,
            error TEXT,
            escalation_record_id TEXT
        )
        """
    )
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_tasks)").fetchall()}
    if "action" not in existing_cols:
        conn.execute("ALTER TABLE agent_tasks ADD COLUMN action TEXT DEFAULT ''")
    if "escalation_record_id" not in existing_cols:
        conn.execute("ALTER TABLE agent_tasks ADD COLUMN escalation_record_id TEXT")
    conn.commit()
    return conn


# ── Orchestrator ──────────────────────────────────────────────────────────────


class AgentOrchestrator:
    """Simple multi-agent task orchestrator.

    Tasks are queued in memory (priority queue) and persisted to SQLite so
    they survive a restart.  The in-process async runner is intentionally
    lightweight — for production use couple this with a proper worker pool.
    """

    def __init__(self, db_path: str = "data/agents.db") -> None:
        self._agents: dict[str, AgentConfig] = {}
        self._tasks: dict[str, AgentTask] = {}
        # Priority queue: (-priority, created_at, task_id)
        self._queue: list[tuple[int, str, str]] = []
        self._db = _ensure_db(Path(db_path))
        self._lock = asyncio.Lock()
        self._perf: dict[str, dict] = {}  # agent_id → perf accumulator
        self._load_tasks_from_db()

    # ── Agent registration ────────────────────────────────────────────────────

    def register_agent(self, config: AgentConfig) -> None:
        """Register an agent configuration."""
        self._agents[config.id] = config
        if config.id not in self._perf:
            self._perf[config.id] = {
                "total": 0,
                "success": 0,
                "failed": 0,
                "total_ms": 0.0,
            }

    def list_agents(self) -> list[AgentConfig]:
        """Return all registered agent configs."""
        return list(self._agents.values())

    # ── Task submission ────────────────────────────────────────────────────────

    def submit_task(self, task: AgentTask) -> str:
        """Resolve the task against the AI Governance Constitution's escalation FSM
        (Tier 4, per-agent domain), persist it, and enqueue it only if the FSM's
        first resting state is 'approved'.

        Per §3.4 of docs/governance/AI-GOVERNANCE-CONSTITUTION.md, ambiguity never
        defaults permissive: an unmatched action escalates rather than being queued.
        A 'rejected'/'halted' outcome leaves the task un-queued with
        status='blocked_governance'; 'escalated'/'pending_cab' leaves it un-queued
        with status='pending_governance' until resolved via the /governance routes.
        Returns the task id in all cases so the caller can inspect
        escalation_record_id / status to see why a task didn't run.
        """
        if not task.id:
            task.id = str(uuid.uuid4())

        agent = self._agents.get(task.agent_id)
        domain = agent.domain if agent is not None else "unassigned"
        request = ActionRequest(
            tier=4,
            domain=domain,
            action=task.action or task.description,
            requestor=task.agent_id or "unknown",
        )
        record = get_escalation_fsm().submit(request)
        task.escalation_record_id = record.record_id

        if record.state in ("rejected", "halted"):
            task.status = "blocked_governance"
            task.error = f"Blocked by governance ({record.state}): {record.reason or ''}".strip()
            self._tasks[task.id] = task
            self._persist_task(task)
            return task.id

        self._tasks[task.id] = task
        self._persist_task(task)

        if record.state == "approved":
            heapq.heappush(self._queue, (-task.priority, task.created_at, task.id))
        else:
            task.status = "pending_governance"
            self._persist_task(task)
        return task.id

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        """Return the task with the given id, or None."""
        return self._tasks.get(task_id)

    # ── Performance tracking ──────────────────────────────────────────────────

    def record_task_outcome(
        self,
        task_id: str,
        success: bool,
        duration_ms: float,
    ) -> None:
        """Record the outcome of a completed task for performance metrics."""
        task = self._tasks.get(task_id)
        if not task:
            return
        acc = self._perf.setdefault(
            task.agent_id,
            {"total": 0, "success": 0, "failed": 0, "total_ms": 0.0},
        )
        acc["total"] += 1
        acc["total_ms"] += duration_ms
        if success:
            acc["success"] += 1
        else:
            acc["failed"] += 1

    def get_performance(self, agent_id: str) -> AgentPerformance:
        """Return performance metrics for a given agent."""
        acc = self._perf.get(agent_id, {"total": 0, "success": 0, "failed": 0, "total_ms": 0.0})
        total = acc["total"]
        avg_ms = acc["total_ms"] / total if total > 0 else 0.0
        success_rate = acc["success"] / total if total > 0 else 0.0
        return AgentPerformance(
            agent_id=agent_id,
            total_tasks=total,
            successful_tasks=acc["success"],
            failed_tasks=acc["failed"],
            avg_duration_ms=avg_ms,
            success_rate=success_rate,
        )

    # ── SQLite persistence ─────────────────────────────────────────────────────

    def _persist_task(self, task: AgentTask) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO agent_tasks
                (id, agent_id, description, action, priority, status, created_at,
                 started_at, completed_at, result, error, escalation_record_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.agent_id,
                task.description,
                task.action,
                task.priority,
                task.status,
                task.created_at,
                task.started_at,
                task.completed_at,
                task.result,
                task.error,
                task.escalation_record_id,
            ),
        )
        self._db.commit()

    def _load_tasks_from_db(self) -> None:
        rows = self._db.execute(
            "SELECT id, agent_id, description, action, priority, status, "
            "created_at, started_at, completed_at, result, error, escalation_record_id "
            "FROM agent_tasks WHERE status IN "
            "('pending', 'running', 'pending_governance', 'blocked_governance')"
        ).fetchall()

        for row in rows:
            task = AgentTask(
                id=row[0],
                agent_id=row[1],
                description=row[2] or "",
                action=row[3] or "",
                priority=row[4] or 5,
                status=row[5] or "pending",
                created_at=row[6] or "",
                started_at=row[7],
                completed_at=row[8],
                result=row[9],
                error=row[10],
                escalation_record_id=row[11],
            )
            self._tasks[task.id] = task
            if task.status == "pending":
                heapq.heappush(self._queue, (-task.priority, task.created_at, task.id))


# ── Module-level singleton ─────────────────────────────────────────────────────

orchestrator = AgentOrchestrator()

__all__ = [
    "AgentConfig",
    "AgentOrchestrator",
    "AgentPerformance",
    "AgentTask",
    "orchestrator",
]
