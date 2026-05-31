"""Background auto-rotation of free cloud AI providers (CLOUD_ONLY / HYBRID)."""

from __future__ import annotations

import asyncio
import logging
import os
import time

from src.platform.infrastructure_mode import cloud_auto_rotation_enabled, get_infrastructure_mode

logger = logging.getLogger("tranc3.adaptive.cloud_rotation")

_task: asyncio.Task[None] | None = None


async def start_cloud_auto_rotation() -> None:
    global _task
    if _task is not None:
        return
    if not cloud_auto_rotation_enabled():
        logger.info(
            "Cloud auto-rotation disabled (mode=%s)",
            get_infrastructure_mode().value,
        )
        return

    interval = float(os.environ.get("ADAPTIVE_CLOUD_AUTO_ROTATE_SECONDS", "180"))

    async def _loop() -> None:
        from src.adaptive.provider_rotator import get_provider_rotator

        rotator = get_provider_rotator()
        logger.info(
            "Cloud auto-rotation started mode=%s chain=%s interval=%ss",
            get_infrastructure_mode().value,
            rotator._state.chain_name,
            interval,
        )
        while True:
            try:
                rotator.refresh_availability()
                active = rotator.active_provider()
                rotator._rotate()
                nxt = rotator.active_provider()
                logger.debug(
                    "Cloud rotation tick active=%s next=%s at=%s",
                    active,
                    nxt,
                    time.time(),
                )
            except Exception as exc:
                logger.warning("Cloud rotation tick failed: %s", exc)
            await asyncio.sleep(interval)

    _task = asyncio.create_task(_loop())


async def stop_cloud_auto_rotation() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
