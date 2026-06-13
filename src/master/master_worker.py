"""
src/master/master_worker.py — MasterWorker orchestrator.

Reads TaskDefinition objects from TaskLoader, schedules them via APScheduler,
executes steps through BotSwarm, and emits lifecycle events to the EventBus
and The Observatory.

Quick start:
    worker = MasterWorker(tasks_dir="tasks/")
    await worker.start()
    # tasks auto-load, schedule, and execute
    await worker.stop()
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log

from .bot_swarm import BotSwarm, StepResult
from .task_loader import TaskLoader
from .task_schema import RetryPolicy, TaskDefinition, TaskStep

logger = logging.getLogger(__name__)

# Service port constants (Trancendos platform)
PORT_INFINITY_WS = 8004  # The Nexus WebSocket hub
PORT_INFINITY_AUTH = 8005  # Infinity OAuth2/SSO/MFA
PORT_USERS_SERVICE = 8006  # Users service
PORT_MONITORING = 8007  # The Observatory monitoring
PORT_NOTIFICATIONS = 8008  # Notifications service
PORT_INFINITY_AI = 8009  # Infinity AI (Luminous)
PORT_THE_GRID = 8010  # The Digital Grid


class TaskExecution:
    """Tracks a single run of a TaskDefinition."""

    def __init__(self, task: TaskDefinition) -> None:
        self.task = task
        self.execution_id = f"{task.name}-{int(time.time() * 1000)}"
        self.status = "pending"
        self.step_results: List[StepResult] = []
        self.started_at = time.monotonic()
        self.finished_at: Optional[float] = None
        self.error: Optional[str] = None

    @property
    def elapsed_ms(self) -> float:
        end = self.finished_at or time.monotonic()
        return (end - self.started_at) * 1000


class MasterWorker:
    """
    Central BotSwarm orchestrator.

    Responsibilities:
    - Load task YAML/JSON files from tasks_dir
    - Schedule them via APScheduler
    - Execute each step via BotSwarm
    - Emit events to EventBus (if available)
    - Report outcomes to The Observatory (if available)
    """

    def __init__(
        self,
        tasks_dir: str = "tasks",
        concurrency_per_bot: int = 2,
    ) -> None:
        self._tasks_dir = tasks_dir
        self._loader = TaskLoader(tasks_dir, on_change=self._on_task_change)
        self._swarm = BotSwarm(concurrency_per_type=concurrency_per_bot)
        self._scheduler = None
        self._running = False
        self._executions: Dict[str, TaskExecution] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        await self._swarm.start()
        self._loader.start()
        self._init_scheduler()
        self._schedule_all_tasks()
        logger.info("MasterWorker started — %d task(s) loaded.", len(self._loader.all()))

    async def stop(self) -> None:
        self._running = False
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._loader.stop()
        await self._swarm.stop()
        logger.info("MasterWorker stopped.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_task(self, name: str) -> TaskExecution:
        """Execute a named task immediately (bypasses schedule)."""
        task = self._loader.get(name)
        if task is None:
            raise ValueError(f"Task '{name}' not found. Loaded: {list(self._loader.all())}")
        return await self._execute_task(task)

    def list_tasks(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "description": t.description,
                "enabled": t.enabled,
                "steps": len(t.steps),
                "schedule": t.schedule.type.value,
                "tags": t.tags,
            }
            for name, t in self._loader.all().items()
        }

    def swarm_status(self) -> Dict[str, Any]:
        return self._swarm.status()

    def recent_executions(self, limit: int = 20) -> List[Dict[str, Any]]:
        execs = sorted(self._executions.values(), key=lambda e: e.started_at, reverse=True)
        return [
            {
                "execution_id": e.execution_id,
                "task": e.task.name,
                "status": e.status,
                "elapsed_ms": round(e.elapsed_ms, 1),
                "steps": len(e.step_results),
                "error": e.error,
            }
            for e in execs[:limit]
        ]

    # ------------------------------------------------------------------
    # Internal — Scheduling
    # ------------------------------------------------------------------

    def _init_scheduler(self) -> None:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            scheduler = AsyncIOScheduler(timezone="UTC")
            scheduler.start()
            self._scheduler = scheduler
            logger.info("APScheduler (AsyncIOScheduler) started.")
        except ImportError:
            logger.warning(
                "apscheduler not installed — scheduled tasks disabled. "
                "Run: pip install apscheduler==3.10.4"
            )
            self._scheduler = None

    def _schedule_all_tasks(self) -> None:
        for task in self._loader.all().values():
            self._schedule_task(task)

    def _schedule_task(self, task: TaskDefinition) -> None:
        if not task.enabled or self._scheduler is None:
            return
        sc = task.schedule
        job_id = f"task-{task.name}"

        try:
            if sc.type.value == "interval":
                kwargs: Dict[str, Any] = {}
                if sc.seconds:
                    kwargs["seconds"] = sc.seconds
                if sc.minutes:
                    kwargs["minutes"] = sc.minutes
                if sc.hours:
                    kwargs["hours"] = sc.hours
                if not kwargs:
                    logger.warning(
                        "Task '%s': interval schedule missing time unit — skipping.", task.name
                    )
                    return
                self._scheduler.add_job(
                    self._scheduled_run,
                    "interval",
                    id=job_id,
                    replace_existing=True,
                    args=[task.name],
                    **kwargs,
                )
            elif sc.type.value == "cron" and sc.cron_expression:
                parts = sc.cron_expression.split()
                if len(parts) == 5:
                    minute, hour, day, month, day_of_week = parts
                    self._scheduler.add_job(
                        self._scheduled_run,
                        "cron",
                        id=job_id,
                        replace_existing=True,
                        args=[task.name],
                        minute=minute,
                        hour=hour,
                        day=day,
                        month=month,
                        day_of_week=day_of_week,
                    )
            elif sc.type.value == "date" and sc.run_date:
                self._scheduler.add_job(
                    self._scheduled_run,
                    "date",
                    id=job_id,
                    replace_existing=True,
                    args=[task.name],
                    run_date=sc.run_date,
                )
            # "once" — run immediately once
            elif sc.type.value == "once":
                asyncio.create_task(self._execute_task_by_name(task.name))
            logger.info("MasterWorker: scheduled task '%s' (%s).", task.name, sc.type.value)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "MasterWorker: failed to schedule '%s': %s",
                sanitize_for_log(task.name),
                sanitize_for_log(exc),
            )

    async def _scheduled_run(self, task_name: str) -> None:
        await self._execute_task_by_name(task_name)

    async def _execute_task_by_name(self, name: str) -> None:
        task = self._loader.get(name)
        if task and task.enabled:
            await self._execute_task(task)

    # ------------------------------------------------------------------
    # Internal — Execution
    # ------------------------------------------------------------------

    async def _execute_task(self, task: TaskDefinition) -> TaskExecution:
        execution = TaskExecution(task)
        self._executions[execution.execution_id] = execution
        execution.status = "running"

        await self._emit(
            "task.started", {"execution_id": execution.execution_id, "task": task.name}
        )
        logger.info("MasterWorker: executing task '%s' (%s).", task.name, execution.execution_id)

        try:
            for step in task.steps:
                if not self._running:
                    execution.status = "cancelled"
                    break
                result = await self._execute_step_with_retry(step, task.name)
                execution.step_results.append(result)
                if not result.success:
                    execution.status = "failed"
                    execution.error = f"Step '{step.bot}.{step.action}' failed: {result.error}"
                    break
            else:
                if execution.status == "running":
                    execution.status = "completed"
        except Exception as exc:  # noqa: BLE001
            execution.status = "failed"
            execution.error = str(exc)
            logger.error(
                "MasterWorker: task '%s' raised exception: %s",
                sanitize_for_log(task.name),
                sanitize_for_log(exc),
                exc_info=True,
            )

        execution.finished_at = time.monotonic()
        event_name = "task.completed" if execution.status == "completed" else "task.failed"
        await self._emit(
            event_name,
            {
                "execution_id": execution.execution_id,
                "task": task.name,
                "status": execution.status,
                "elapsed_ms": round(execution.elapsed_ms, 1),
                "steps": len(execution.step_results),
                "error": execution.error,
            },
        )
        logger.info(
            "MasterWorker: task '%s' %s in %.1fms.",
            task.name,
            execution.status,
            execution.elapsed_ms,
        )
        return execution

    async def _execute_step_with_retry(self, step: TaskStep, task_name: str) -> StepResult:
        policy: RetryPolicy = step.retry
        attempt = 0
        backoff = policy.backoff_seconds

        while attempt < policy.max_attempts:
            attempt += 1
            result = await self._swarm.submit(
                bot_type=step.bot,
                action=step.action,
                params=step.params,
                timeout=step.timeout_seconds,
            )
            if result.success:
                return result

            if attempt < policy.max_attempts:
                logger.warning(
                    "MasterWorker: step %s.%s failed (attempt %d/%d): %s. Retrying in %.1fs.",
                    step.bot,
                    step.action,
                    attempt,
                    policy.max_attempts,
                    result.error,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * policy.backoff_multiplier, policy.max_backoff_seconds)
            else:
                logger.error(
                    "MasterWorker: step %s.%s exhausted retries (%d). Last error: %s",
                    sanitize_for_log(step.bot),
                    sanitize_for_log(step.action),
                    policy.max_attempts,
                    sanitize_for_log(result.error),
                )

        return result  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal — Event bus bridge
    # ------------------------------------------------------------------

    async def _emit(self, event: str, data: Any) -> None:
        try:
            from src.workflow.executor import event_bus

            await event_bus.publish(event, data)
        except Exception:  # noqa: S110
            pass  # EventBus is optional — never block on it

    # ------------------------------------------------------------------
    # Hot-reload callback
    # ------------------------------------------------------------------

    def _on_task_change(self, name: str, task: Optional[TaskDefinition]) -> None:
        if task is None:
            # File deleted — remove scheduler job
            if self._scheduler:
                try:
                    self._scheduler.remove_job(f"task-{name}")
                    logger.info("MasterWorker: unscheduled task '%s'.", name)
                except Exception:  # noqa: S110
                    pass  # graceful degradation
        else:
            # File added/modified — reschedule
            self._schedule_task(task)
