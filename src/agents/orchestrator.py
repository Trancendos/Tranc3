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
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from Dimensional.sanitize import sanitize_for_log
from src.compliance.escalation_fsm import ActionRequest, RecordNotFoundError, get_escalation_fsm
from src.database.encrypted_sqlite import connect as sqlite3_connect

logger = logging.getLogger("tranc3.agents.orchestrator")

# Governance FSM states that must never leave a task runnable. 'frozen' sits
# between 'escalated' and 'halted' in the FSM (§3.2) — a critical-severity hold,
# not yet irreversible, but still a hard stop on this task until a human acts.
_BLOCKING_STATES = frozenset({"rejected", "frozen", "halted"})

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

    # Field order preserves the pre-Phase-3 constructor contract for positional
    # callers — the two Phase 3 additions (action, escalation_record_id) are
    # appended at the end, not inserted in the middle.
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    description: str = ""
    priority: int = 5  # 0-10
    # pending|running|completed|failed|pending_governance|blocked_governance
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    action: str = (
        ""  # charter-matched verb (e.g. "read_approved_documents"); falls back to description
    )
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


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, ddl_type: str
) -> None:
    """ALTER TABLE ADD COLUMN, tolerating the race where a second concurrent worker
    also observed the column missing and got there first — see cab_gate.py's
    _init_db() for the same pattern. busy_timeout (set on the connection below)
    means a losing worker waits for the winner's transaction instead of getting an
    immediate 'database is locked'; once it proceeds, it hits 'duplicate column
    name' instead, which this tolerates."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    except sqlite3.OperationalError as exc:
        if f"duplicate column name: {column}" not in str(exc):
            raise


def _ensure_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3_connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
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
        _add_column_if_missing(conn, "agent_tasks", "action", "TEXT DEFAULT ''")
    if "escalation_record_id" not in existing_cols:
        _add_column_if_missing(conn, "agent_tasks", "escalation_record_id", "TEXT")
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
        A 'rejected' outcome leaves the task un-queued with status='blocked_governance'
        ('halted'/'frozen' are not reachable here — EscalationFSM.submit() never
        returns them; those states are only reached later via an explicit
        EscalationFSM.halt()/freeze() call — see dequeue_task(), which is what
        actually enforces them against an already-queued task, since being
        'approved' at submit time is not a permanent guarantee).
        'escalated'/'pending_cab' leaves it un-queued with status='pending_governance'
        until resolved via the /governance routes — call resync_governance(task_id)
        afterwards to actually enqueue (or block) the task once that decision lands;
        nothing does this automatically today. Returns the task id in all cases so the
        caller can inspect escalation_record_id / status to see why a task didn't run.
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

        if record.state == "rejected":
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

    def resync_governance(self, task_id: str) -> Optional[AgentTask]:
        """Re-check a 'pending_governance' task's escalation record and, if it has
        since reached a resting state, actually apply that decision — closing the
        loop submit_task() otherwise leaves open. Without this, a task approved via
        POST /governance/actions/{id}/cab-decision stays 'pending_governance' forever:
        that route only updates the FSM record, it has no idea AgentOrchestrator or
        this task exist. Not wired to any automatic trigger (no event bus between the
        two modules) — call it explicitly (e.g. from a poller, or right after you know
        a CAB decision landed for this task's escalation_record_id).

        Returns the updated task, or None if task_id is unknown. A task not currently
        'pending_governance' is returned unchanged (idempotent to call repeatedly).
        """
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if task.status != "pending_governance" or not task.escalation_record_id:
            return task

        try:
            record = get_escalation_fsm().get(task.escalation_record_id)
        except RecordNotFoundError:
            return task

        if record.state == "approved":
            task.status = "pending"
            self._persist_task(task)
            heapq.heappush(self._queue, (-task.priority, task.created_at, task.id))
        elif record.state in _BLOCKING_STATES:
            task.status = "blocked_governance"
            task.error = f"Blocked by governance ({record.state}): {record.reason or ''}".strip()
            self._persist_task(task)
        # else: still escalated/pending_cab/policy_checked — nothing to do yet.
        return task

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
                self._reenqueue_if_still_approved(task)

    def _reenqueue_if_still_approved(self, task: AgentTask) -> None:
        """Restores a 'pending' task to the runnable queue on process restart — but
        only after re-checking its *live* governance state, not the status column
        alone. A stored status='pending' snapshot only reflects what was true at the
        moment it was last persisted; if the escalation record was halted or frozen
        any time between then and this restart (e.g. via POST
        /governance/actions/{id}/halt), blindly trusting the column would silently
        make hard-stopped work runnable again.
        """
        if not task.escalation_record_id:
            # A 'pending' row with no escalation_record_id predates Phase 3's gating
            # (submit_task() always sets one now) — an upgrade must not silently run
            # this legacy work outside the Tier 4 gate. Leave it inspectable via
            # get_task() but out of the runnable queue until resubmitted.
            logger.warning(
                "agent_tasks row %s is 'pending' with no escalation_record_id "
                "(pre-Phase-3 data) — not enqueueing; resubmit via submit_task()",
                sanitize_for_log(task.id),  # codeql[py/log-injection]
            )
            return

        try:
            record = get_escalation_fsm().get(task.escalation_record_id)
        except RecordNotFoundError:
            record = None

        if record is None or record.state in _BLOCKING_STATES:
            task.status = "blocked_governance"
            reason = record.reason if record else "escalation record no longer found"
            state = record.state if record else "unknown"
            task.error = f"Blocked by governance ({state}): {reason or ''}".strip()
            self._persist_task(task)
            return

        if record.state != "approved":
            # escalated/pending_cab/policy_checked — no longer a clean 'approved'
            # snapshot; fall back to the same un-queued, inspectable state
            # submit_task() itself would have left it in.
            task.status = "pending_governance"
            self._persist_task(task)
            return

        heapq.heappush(self._queue, (-task.priority, task.created_at, task.id))

    def dequeue_task(self) -> Optional[AgentTask]:
        """Pop the next runnable task for a worker to execute — the sanctioned way to
        consume this queue, and the reason one exists at all: a task can sit queued
        for a while before a worker reaches it, and if its escalation record was
        halted or frozen after it was enqueued, the stale status='pending' snapshot
        on the task itself must not be trusted at dispatch time. Re-validates the
        live governance state for each candidate, skipping (and blocking) anything
        no longer 'approved', until it finds a genuinely runnable task or the queue
        empties. Marks the returned task 'running' before handing it back.
        """
        while self._queue:
            _, _, task_id = heapq.heappop(self._queue)
            task = self._tasks.get(task_id)
            if task is None or task.status != "pending" or not task.escalation_record_id:
                continue  # stale queue entry — already handled/mutated elsewhere

            try:
                record = get_escalation_fsm().get(task.escalation_record_id)
            except RecordNotFoundError:
                continue

            if record.state != "approved":
                task.status = "blocked_governance"
                task.error = (
                    f"Blocked by governance ({record.state}): {record.reason or ''}".strip()
                )
                self._persist_task(task)
                continue

            task.status = "running"
            task.started_at = datetime.now(timezone.utc).isoformat()
            self._persist_task(task)
            return task
        return None


# ── Module-level singleton ─────────────────────────────────────────────────────

orchestrator = AgentOrchestrator()

__all__ = [
    "AgentConfig",
    "AgentOrchestrator",
    "AgentPerformance",
    "AgentTask",
    "orchestrator",
]
