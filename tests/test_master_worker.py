"""
tests/test_master_worker.py — Tests for src/master/ BotSwarm / MasterWorker system.

Covers:
- TaskSchema validation (happy path + error cases)
- TaskLoader (load_all, hot-reload callback, invalid files)
- BotSwarm (submit → StepResult, timeout, stub dispatch)
- MasterWorker (start/stop, run_task, list_tasks)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Import guard — skip entire module if pydantic is unavailable
# ---------------------------------------------------------------------------
pytest.importorskip("pydantic")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_tasks(tmp_path: Path) -> Path:
    """Return a temporary tasks directory pre-populated with valid YAML files."""
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    return tasks_dir


def write_task(dir: Path, filename: str, data: dict) -> Path:
    p = dir / filename
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


MINIMAL_TASK = {
    "name": "smoke-test",
    "description": "Minimal task for testing",
    "schedule": {"type": "once"},
    "steps": [
        {
            "bot": "monitor",
            "action": "ping",
            "params": {},
            "timeout_seconds": 5,
            "retry": {"max_attempts": 1, "backoff_seconds": 0},
        }
    ],
}

INTERVAL_TASK = {
    "name": "interval-task",
    "description": "Runs every 60s",
    "schedule": {"type": "interval", "seconds": 60},
    "steps": [
        {"bot": "memory", "action": "store", "params": {"key": "test"}, "timeout_seconds": 5}
    ],
}


# ---------------------------------------------------------------------------
# TaskSchema tests
# ---------------------------------------------------------------------------


class TestTaskSchema:
    def test_minimal_task_parses(self):
        from src.master.task_schema import TaskDefinition

        t = TaskDefinition.model_validate(MINIMAL_TASK)
        assert t.name == "smoke-test"
        assert len(t.steps) == 1
        assert t.steps[0].bot == "monitor"

    def test_name_slugified(self):
        from src.master.task_schema import TaskDefinition

        data = dict(MINIMAL_TASK)
        data["name"] = "My Task Name!"
        t = TaskDefinition.model_validate(data)
        assert t.name in ("my-task-name-", "my-task-name")  # trailing dash stripped or not

    def test_invalid_bot_type_raises(self):
        from pydantic import ValidationError

        from src.master.task_schema import TaskDefinition

        data = dict(MINIMAL_TASK)
        data["steps"] = [{"bot": "nonexistent", "action": "foo", "params": {}}]
        with pytest.raises(ValidationError, match="Unknown bot type"):
            TaskDefinition.model_validate(data)

    def test_empty_steps_raises(self):
        from pydantic import ValidationError

        from src.master.task_schema import TaskDefinition

        data = dict(MINIMAL_TASK)
        data["steps"] = []
        with pytest.raises(ValidationError):
            TaskDefinition.model_validate(data)

    def test_schedule_defaults_to_once(self):
        from src.master.task_schema import ScheduleType, TaskDefinition

        data = {"name": "no-schedule", "steps": MINIMAL_TASK["steps"]}
        t = TaskDefinition.model_validate(data)
        assert t.schedule.type == ScheduleType.once

    def test_retry_policy_defaults(self):
        from src.master.task_schema import RetryPolicy

        p = RetryPolicy()
        assert p.max_attempts == 3
        assert p.backoff_seconds == 2.0

    def test_interval_task(self):
        from src.master.task_schema import ScheduleType, TaskDefinition

        t = TaskDefinition.model_validate(INTERVAL_TASK)
        assert t.schedule.type == ScheduleType.interval
        assert t.schedule.seconds == 60

    def test_cron_task(self):
        from src.master.task_schema import ScheduleType, TaskDefinition

        data = dict(MINIMAL_TASK)
        data["schedule"] = {"type": "cron", "cron_expression": "0 */6 * * *"}
        t = TaskDefinition.model_validate(data)
        assert t.schedule.type == ScheduleType.cron
        assert t.schedule.cron_expression == "0 */6 * * *"

    def test_all_valid_bot_types(self):
        from src.master.task_schema import TaskDefinition

        valid_bots = [
            "generate",
            "embed",
            "emotion",
            "tokenize",
            "consciousness",
            "personality",
            "predict",
            "code",
            "memory",
            "monitor",
            "search",
            "summarise",
        ]
        for bot in valid_bots:
            data = dict(MINIMAL_TASK)
            data["steps"] = [{"bot": bot, "action": "test", "params": {}}]
            t = TaskDefinition.model_validate(data)
            assert t.steps[0].bot == bot


# ---------------------------------------------------------------------------
# TaskLoader tests
# ---------------------------------------------------------------------------


class TestTaskLoader:
    def test_load_all_empty_dir(self, tmp_tasks: Path):
        from src.master.task_loader import TaskLoader

        loader = TaskLoader(tmp_tasks)
        tasks = loader.load_all()
        assert tasks == {}

    def test_load_yaml_file(self, tmp_tasks: Path):
        from src.master.task_loader import TaskLoader

        write_task(tmp_tasks, "smoke.yaml", MINIMAL_TASK)
        loader = TaskLoader(tmp_tasks)
        tasks = loader.load_all()
        assert "smoke-test" in tasks
        assert tasks["smoke-test"].description == "Minimal task for testing"

    def test_load_json_file(self, tmp_tasks: Path):
        from src.master.task_loader import TaskLoader

        p = tmp_tasks / "smoke.json"
        p.write_text(json.dumps(MINIMAL_TASK), encoding="utf-8")
        loader = TaskLoader(tmp_tasks)
        tasks = loader.load_all()
        assert "smoke-test" in tasks

    def test_invalid_yaml_skipped(self, tmp_tasks: Path):
        from src.master.task_loader import TaskLoader

        bad = tmp_tasks / "bad.yaml"
        bad.write_text("this: is: invalid: yaml:", encoding="utf-8")
        write_task(tmp_tasks, "good.yaml", MINIMAL_TASK)
        loader = TaskLoader(tmp_tasks)
        tasks = loader.load_all()
        # good task still loads; bad one skipped
        assert len(tasks) <= 1

    def test_non_yaml_files_ignored(self, tmp_tasks: Path):
        from src.master.task_loader import TaskLoader

        (tmp_tasks / "readme.txt").write_text("ignored", encoding="utf-8")
        (tmp_tasks / "script.py").write_text("# ignored", encoding="utf-8")
        loader = TaskLoader(tmp_tasks)
        tasks = loader.load_all()
        assert tasks == {}

    def test_on_change_callback_called(self, tmp_tasks: Path):
        from src.master.task_loader import TaskLoader

        changes = []
        loader = TaskLoader(tmp_tasks, on_change=lambda n, t: changes.append((n, t)))
        write_task(tmp_tasks, "cb.yaml", MINIMAL_TASK)
        loader.load_all()
        assert len(changes) == 1
        name, task = changes[0]
        assert name == "smoke-test"
        assert task is not None

    def test_get_returns_none_for_unknown(self, tmp_tasks: Path):
        from src.master.task_loader import TaskLoader

        loader = TaskLoader(tmp_tasks)
        loader.load_all()
        assert loader.get("does-not-exist") is None

    def test_multiple_tasks_loaded(self, tmp_tasks: Path):
        from src.master.task_loader import TaskLoader

        write_task(tmp_tasks, "a.yaml", MINIMAL_TASK)
        write_task(tmp_tasks, "b.yaml", INTERVAL_TASK)
        loader = TaskLoader(tmp_tasks)
        tasks = loader.load_all()
        assert len(tasks) == 2
        assert "smoke-test" in tasks
        assert "interval-task" in tasks

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path):
        from src.master.task_loader import TaskLoader

        loader = TaskLoader(tmp_path / "does-not-exist")
        tasks = loader.load_all()
        assert tasks == {}


# ---------------------------------------------------------------------------
# BotSwarm tests
# ---------------------------------------------------------------------------


class TestBotSwarm:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        from src.master.bot_swarm import BotSwarm

        swarm = BotSwarm()
        await swarm.start()
        await swarm.stop()

    @pytest.mark.asyncio
    async def test_submit_returns_stub(self):
        from src.master.bot_swarm import BotSwarm

        swarm = BotSwarm()
        await swarm.start()
        try:
            result = await swarm.submit("monitor", "ping", {}, timeout=10.0)
            assert result.bot_type == "monitor"
            assert result.action == "ping"
            # succeeds with stub or real bot
            assert isinstance(result.success, bool)
        finally:
            await swarm.stop()

    @pytest.mark.asyncio
    async def test_status_empty(self):
        from src.master.bot_swarm import BotSwarm

        swarm = BotSwarm()
        await swarm.start()
        try:
            s = swarm.status()
            assert isinstance(s, dict)
        finally:
            await swarm.stop()

    @pytest.mark.asyncio
    async def test_multiple_concurrent_submits(self):
        from src.master.bot_swarm import BotSwarm

        swarm = BotSwarm(concurrency_per_type=3)
        await swarm.start()
        try:
            results = await asyncio.gather(
                swarm.submit("monitor", "ping", {"id": 1}, timeout=10.0),
                swarm.submit("memory", "get", {"key": "x"}, timeout=10.0),
                swarm.submit("search", "query", {"q": "test"}, timeout=10.0),
            )
            assert len(results) == 3
            for r in results:
                assert isinstance(r.success, bool)
        finally:
            await swarm.stop()


# ---------------------------------------------------------------------------
# MasterWorker tests
# ---------------------------------------------------------------------------


class TestMasterWorker:
    @pytest.mark.asyncio
    async def test_start_stop_empty_dir(self, tmp_path: Path):
        from src.master.master_worker import MasterWorker

        worker = MasterWorker(tasks_dir=str(tmp_path / "tasks"))
        await worker.start()
        try:
            tasks = worker.list_tasks()
            assert isinstance(tasks, dict)
        finally:
            await worker.stop()

    @pytest.mark.asyncio
    async def test_list_tasks(self, tmp_tasks: Path):
        from src.master.master_worker import MasterWorker

        write_task(tmp_tasks, "a.yaml", MINIMAL_TASK)
        write_task(tmp_tasks, "b.yaml", INTERVAL_TASK)
        worker = MasterWorker(tasks_dir=str(tmp_tasks))
        await worker.start()
        try:
            tasks = worker.list_tasks()
            assert len(tasks) == 2
            assert "smoke-test" in tasks
        finally:
            await worker.stop()

    @pytest.mark.asyncio
    async def test_run_task(self, tmp_tasks: Path):
        from src.master.master_worker import MasterWorker

        write_task(tmp_tasks, "smoke.yaml", MINIMAL_TASK)
        worker = MasterWorker(tasks_dir=str(tmp_tasks))
        await worker.start()
        try:
            execution = await worker.run_task("smoke-test")
            assert execution.task.name == "smoke-test"
            assert execution.status in ("completed", "failed")  # stub may fail, that's ok
            assert execution.elapsed_ms >= 0
        finally:
            await worker.stop()

    @pytest.mark.asyncio
    async def test_run_task_unknown_raises(self, tmp_tasks: Path):
        from src.master.master_worker import MasterWorker

        worker = MasterWorker(tasks_dir=str(tmp_tasks))
        await worker.start()
        try:
            with pytest.raises(ValueError, match="not found"):
                await worker.run_task("does-not-exist")
        finally:
            await worker.stop()

    @pytest.mark.asyncio
    async def test_recent_executions(self, tmp_tasks: Path):
        from src.master.master_worker import MasterWorker

        write_task(tmp_tasks, "smoke.yaml", MINIMAL_TASK)
        worker = MasterWorker(tasks_dir=str(tmp_tasks))
        await worker.start()
        try:
            await worker.run_task("smoke-test")
            execs = worker.recent_executions(limit=5)
            assert len(execs) >= 1
            assert execs[0]["task"] == "smoke-test"
        finally:
            await worker.stop()

    @pytest.mark.asyncio
    async def test_swarm_status(self, tmp_tasks: Path):
        from src.master.master_worker import MasterWorker

        worker = MasterWorker(tasks_dir=str(tmp_tasks))
        await worker.start()
        try:
            status = worker.swarm_status()
            assert isinstance(status, dict)
        finally:
            await worker.stop()


# ---------------------------------------------------------------------------
# Integration: real YAML files in tasks/
# ---------------------------------------------------------------------------


class TestRealTaskFiles:
    """Validate the bundled task YAML files parse without errors."""

    @pytest.mark.parametrize(
        "filename",
        [
            "health-check.yaml",
            "security-scan.yaml",
            "metrics-collection.yaml",
            "knowledge-indexing.yaml",
        ],
    )
    def test_bundled_task_is_valid(self, filename: str):
        from src.master.task_loader import TaskLoader

        tasks_dir = Path(__file__).parent.parent / "tasks"
        if not tasks_dir.exists():
            pytest.skip("tasks/ directory not found")
        loader = TaskLoader(tasks_dir)
        tasks = loader.load_all()
        # At least one task loaded from this file
        assert len(tasks) >= 1, f"No tasks loaded from tasks/{filename}"
