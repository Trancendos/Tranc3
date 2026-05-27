"""
src/master — Master Worker / BotSwarm orchestration layer.

Reads YAML/JSON task definitions from tasks/, distributes work to typed
workers via BotRegistry + EventBus, tracks state, and reports to The Observatory.

Public surface:
    MasterWorker   — central orchestrator (start / stop / run_task)
    BotSwarm       — worker pool with health-based routing
    TaskDefinition — Pydantic model for a task YAML
    TaskLoader     — file-system watcher with hot-reload
"""

from .bot_swarm import BotSwarm
from .master_worker import MasterWorker
from .task_loader import TaskLoader
from .task_schema import RetryPolicy, ScheduleConfig, TaskDefinition, TaskStep

__all__ = [
    "MasterWorker",
    "BotSwarm",
    "TaskLoader",
    "TaskDefinition",
    "TaskStep",
    "ScheduleConfig",
    "RetryPolicy",
]
