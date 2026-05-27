"""
src/master/swarm_cli.py — CLI for running BotSwarm tasks manually.

Usage:
    python -m src.master.swarm_cli list
    python -m src.master.swarm_cli run health-check
    python -m src.master.swarm_cli run security-scan --tasks-dir tasks/
    python -m src.master.swarm_cli status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


async def _cmd_list(tasks_dir: str) -> None:
    from .task_loader import TaskLoader
    loader = TaskLoader(tasks_dir)
    tasks = loader.load_all()
    if not tasks:
        print(f"No tasks found in '{tasks_dir}'.")
        return
    print(f"Loaded {len(tasks)} task(s) from '{tasks_dir}':\n")
    for name, t in sorted(tasks.items()):
        status = "enabled" if t.enabled else "DISABLED"
        print(f"  {name:30s}  [{status}]  {t.description}")


async def _cmd_run(task_name: str, tasks_dir: str) -> None:
    from .master_worker import MasterWorker
    worker = MasterWorker(tasks_dir=tasks_dir)
    await worker.start()
    try:
        execution = await worker.run_task(task_name)
        summary = {
            "execution_id": execution.execution_id,
            "task": execution.task.name,
            "status": execution.status,
            "elapsed_ms": round(execution.elapsed_ms, 1),
            "steps": [
                {
                    "bot": r.bot_type,
                    "action": r.action,
                    "success": r.success,
                    "duration_ms": round(r.duration_ms, 1),
                    "error": r.error,
                }
                for r in execution.step_results
            ],
        }
        print(json.dumps(summary, indent=2))
        sys.exit(0 if execution.status == "completed" else 1)
    finally:
        await worker.stop()


async def _cmd_status(tasks_dir: str) -> None:
    from .master_worker import MasterWorker
    worker = MasterWorker(tasks_dir=tasks_dir)
    await worker.start()
    try:
        print("Tasks:")
        for name, info in sorted(worker.list_tasks().items()):
            print(f"  {name:30s}  {info['schedule']:10s}  {info['steps']} step(s)  {info['description']}")
        print("\nSwarm:")
        status = worker.swarm_status()
        if status:
            for bot_type, s in sorted(status.items()):
                print(f"  {bot_type:20s}  healthy={s['healthy']}  queue={s['queue_depth']}  ok={s['completed']}  fail={s['failed']}")
        else:
            print("  (no workers active)")
    finally:
        await worker.stop()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="swarm",
        description="TRANC3 BotSwarm CLI — run and inspect scheduled bot tasks",
    )
    parser.add_argument("--tasks-dir", default="tasks", help="Directory with task YAML/JSON files")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all loaded tasks")

    run_p = sub.add_parser("run", help="Run a task immediately by name")
    run_p.add_argument("task", help="Task name (matches 'name:' in the YAML file)")

    sub.add_parser("status", help="Show task list and swarm worker status")

    args = parser.parse_args()
    loop = asyncio.new_event_loop()
    try:
        if args.command == "list":
            loop.run_until_complete(_cmd_list(args.tasks_dir))
        elif args.command == "run":
            loop.run_until_complete(_cmd_run(args.task, args.tasks_dir))
        elif args.command == "status":
            loop.run_until_complete(_cmd_status(args.tasks_dir))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
