# src/fluidic/hot_config.py
# Hot-reload configuration — watch .env/config files and reload without restart

import asyncio
import logging
import os
from typing import Any, Callable, Dict, List, Optional
from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class HotConfig:
    """
    Configuration hot-reload system.
    Watches specified files for changes and triggers callbacks.
    Enables zero-downtime configuration updates.
    """

    def __init__(self, watch_paths: Optional[List[str]] = None):
        self._watch_paths = watch_paths or [".env", "config.json"]
        self._callbacks: List[Callable] = []
        self._file_mtimes: Dict[str, float] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._poll_interval: float = 5.0  # seconds
        self._config_cache: Dict[str, Any] = {}

    def add_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for config changes"""
        self._callbacks.append(callback)

    def add_watch_path(self, path: str) -> None:
        """Add a file path to watch"""
        if path not in self._watch_paths:
            self._watch_paths.append(path)

    async def start(self) -> None:
        """Start watching for config changes"""
        self._running = True
        # Initialize mtimes
        for path in self._watch_paths:
            if os.path.exists(path):
                self._file_mtimes[path] = os.path.getmtime(path)

        self._task = asyncio.create_task(self._watch_loop())
        logger.info("HotConfig watching: %s", sanitize_for_log(self._watch_paths))

    async def stop(self) -> None:
        """Stop watching"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _watch_loop(self) -> None:
        """Poll files for changes"""
        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)
                changes = self._detect_changes()
                if changes:
                    logger.info("Config changed: %s", sanitize_for_log(list(changes.keys())))
                    self._config_cache.update(changes)
                    for callback in self._callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(changes)
                            else:
                                callback(changes)
                        except Exception as e:
                            logger.error("Config callback error: %s", sanitize_for_log(e))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("HotConfig watch error: %s", sanitize_for_log(e))

    def _detect_changes(self) -> Dict[str, Any]:
        """Detect file changes and return updated values"""
        changes: Dict[str, Any] = {}

        for path in self._watch_paths:
            if not os.path.exists(path):
                continue

            current_mtime = os.path.getmtime(path)
            previous_mtime = self._file_mtimes.get(path, 0)

            if current_mtime > previous_mtime:
                self._file_mtimes[path] = current_mtime

                # Parse .env file
                if path.endswith(".env"):
                    changes.update(self._parse_env_file(path))
                # Parse JSON config
                elif path.endswith(".json"):
                    changes.update(self._parse_json_file(path))

        return changes

    def _parse_env_file(self, path: str) -> Dict[str, str]:
        """Parse a .env file into key-value pairs"""
        result = {}
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip("\"'")
                        if key:
                            result[key] = value
                            # Also update os.environ
                            os.environ[key] = value
        except Exception as e:
            logger.error("Error parsing %s: %s", sanitize_for_log(path), sanitize_for_log(e))
        return result

    def _parse_json_file(self, path: str) -> Dict[str, Any]:
        """Parse a JSON config file"""
        import json

        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Error parsing %s: %s", sanitize_for_log(path), sanitize_for_log(e))
            return {}

    @property
    def cache(self) -> Dict[str, Any]:
        """Current cached configuration"""
        return self._config_cache.copy()


async def watch_config(
    *paths: str,
    callback: Optional[Callable] = None,
) -> HotConfig:
    """Convenience function to start watching config files"""
    hc = HotConfig(list(paths))
    if callback:
        hc.add_callback(callback)
    await hc.start()
    return hc
