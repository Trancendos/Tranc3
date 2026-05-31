"""
Proactive zero-cost management loop.

Runs health probes, zero-cost audit, and swarm manifests on an interval
without paid external services.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("tranc3.adaptive.proactive")

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ProactiveRun:
    run_at: float
    health_rc: int | None = None
    audit_rc: int | None = None
    swarm_rc: int | None = None
    rotation: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class ProactiveOrchestrator:
    def __init__(self) -> None:
        self._interval = float(os.environ.get("PROACTIVE_INTERVAL_SECONDS", "600"))
        self._enabled = os.environ.get("PROACTIVE_ORCHESTRATOR_ENABLED", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        self._last: ProactiveRun | None = None
        self._task: asyncio.Task[None] | None = None

    async def run_once(self) -> ProactiveRun:
        run = ProactiveRun(run_at=time.time())
        try:
            from src.adaptive.provider_rotator import get_provider_rotator

            run.rotation = get_provider_rotator().status()
        except Exception as exc:
            run.errors.append(f"rotation: {exc}")

        run.health_rc = await asyncio.to_thread(self._run_script, "scripts/health_check.py")
        run.audit_rc = await asyncio.to_thread(self._run_script, "scripts/zero_cost_audit.py")
        run.swarm_rc = await asyncio.to_thread(
            self._run_script,
            "scripts/swarm_runner.py",
            "--manifest",
            "config/swarm/manifests/adaptive-zero-cost.yaml",
        )
        self._last = run
        self._persist(run)
        return run

    def _run_script(self, script: str, *args: str) -> int:
        path = ROOT / script
        if not path.is_file():
            return 2
        proc = subprocess.run(
            [sys.executable, str(path), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            logger.warning("%s exited %s: %s", script, proc.returncode, proc.stderr[-200:])
        return proc.returncode

    def _persist(self, run: ProactiveRun) -> None:
        log_path = ROOT / "logs" / "proactive-orchestrator.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_at": run.run_at,
            "health_rc": run.health_rc,
            "audit_rc": run.audit_rc,
            "swarm_rc": run.swarm_rc,
            "rotation": run.rotation,
            "errors": run.errors,
        }
        with log_path.open("a") as fh:
            fh.write(json.dumps(payload) + "\n")

    async def start_background(self) -> None:
        if not self._enabled or self._task:
            return

        async def _loop() -> None:
            while True:
                try:
                    await self.run_once()
                except Exception as exc:
                    logger.exception("Proactive loop error: %s", exc)
                await asyncio.sleep(self._interval)

        self._task = asyncio.create_task(_loop())
        logger.info("Proactive orchestrator started interval=%ss", self._interval)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "interval_seconds": self._interval,
            "last_run": None
            if self._last is None
            else {
                "run_at": self._last.run_at,
                "health_rc": self._last.health_rc,
                "audit_rc": self._last.audit_rc,
                "swarm_rc": self._last.swarm_rc,
                "errors": self._last.errors,
            },
        }


_orchestrator: ProactiveOrchestrator | None = None


def get_proactive_orchestrator() -> ProactiveOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ProactiveOrchestrator()
    return _orchestrator
