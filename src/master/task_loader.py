"""
src/master/task_loader.py — YAML/JSON task file loader with hot-reload.

Watches a directory for *.yaml / *.yml / *.json files containing TaskDefinition
schemas. File changes trigger automatic re-registration without restart.

Usage:
    loader = TaskLoader("tasks/")
    loader.start()          # begin watching
    tasks = loader.all()    # {name: TaskDefinition}
    loader.stop()
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

import yaml

from .task_schema import TaskDefinition

logger = logging.getLogger(__name__)


class TaskLoader:
    def __init__(
        self,
        tasks_dir: str | Path = "tasks",
        on_change: Optional[Callable[[str, Optional[TaskDefinition]], None]] = None,
    ) -> None:
        self._dir = Path(tasks_dir)
        self._tasks: Dict[str, TaskDefinition] = {}
        self._lock = threading.RLock()
        self._on_change = on_change
        self._observer = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_all(self) -> Dict[str, TaskDefinition]:
        """Scan the directory and load all task files. Returns the full map."""
        if not self._dir.exists():
            logger.warning("Tasks directory %s does not exist — no tasks loaded.", self._dir)
            return {}
        for path in sorted(self._dir.glob("*")):
            if path.suffix in (".yaml", ".yml", ".json"):
                self._load_file(path)
        logger.info("TaskLoader: loaded %d task(s) from %s", len(self._tasks), self._dir)
        return dict(self._tasks)

    def start(self) -> None:
        """Start filesystem watcher for hot-reload. Loads all tasks first."""
        self.load_all()
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            handler = _TaskFileHandler(self)
            self._observer = Observer()
            self._observer.schedule(handler, str(self._dir), recursive=False)
            self._observer.start()
            logger.info("TaskLoader: watching %s for changes.", self._dir)
        except ImportError:
            logger.warning(
                "watchdog not installed — hot-reload disabled. "
                "Run: pip install watchdog==4.0.0"
            )

    def stop(self) -> None:
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join()
            logger.info("TaskLoader: stopped filesystem watcher.")

    def all(self) -> Dict[str, TaskDefinition]:
        with self._lock:
            return dict(self._tasks)

    def get(self, name: str) -> Optional[TaskDefinition]:
        with self._lock:
            return self._tasks.get(name)

    def remove(self, name: str) -> None:
        with self._lock:
            if name in self._tasks:
                del self._tasks[name]
                logger.info("TaskLoader: removed task '%s'.", name)
                if self._on_change:
                    self._on_change(name, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_file(self, path: Path) -> None:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw) if path.suffix == ".json" else yaml.safe_load(raw)
            if not isinstance(data, dict):
                logger.warning("TaskLoader: %s is not a mapping — skipped.", path)
                return
            task = TaskDefinition.model_validate(data)
            with self._lock:
                self._tasks[task.name] = task
            logger.info("TaskLoader: (re)loaded task '%s' from %s.", task.name, path.name)
            if self._on_change:
                self._on_change(task.name, task)
        except Exception as exc:  # noqa: BLE001
            logger.error("TaskLoader: failed to parse %s: %s", path.name, exc)

    def _remove_by_path(self, path: Path) -> None:
        # Find task name by scanning current tasks for one loaded from this path.
        # Simpler: reload all (cheap for small dirs).
        with self._lock:
            self._tasks.clear()
        self.load_all()


class _TaskFileHandler:
    """Watchdog event handler — delegates to TaskLoader."""

    def __init__(self, loader: TaskLoader) -> None:
        self._loader = loader

    def dispatch(self, event) -> None:  # type: ignore[override]
        path = Path(getattr(event, "src_path", ""))
        if path.suffix not in (".yaml", ".yml", ".json"):
            return
        event_type = type(event).__name__
        if "Created" in event_type or "Modified" in event_type:
            self._loader._load_file(path)
        elif "Deleted" in event_type or "Moved" in event_type:
            self._loader._remove_by_path(path)
