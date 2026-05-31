"""Background health refresh and optional rotation for platform layers."""

from __future__ import annotations

import asyncio
import logging
import os
import time

from src.platform.infrastructure_mode import get_infrastructure_mode
from src.platform.layer_rotator import get_layer_rotator, layer_rotation_enabled

logger = logging.getLogger("tranc3.adaptive.layer_rotation")

_task: asyncio.Task[None] | None = None


async def start_layer_auto_rotation() -> None:
    global _task
    if _task is not None:
        return
    if not layer_rotation_enabled():
        logger.info("Platform layer auto-rotation disabled")
        return

    cfg_interval = 300.0
    try:
        from pathlib import Path

        import yaml

        path = Path(__file__).resolve().parents[2] / "config" / "platform" / "layer_rotation.yaml"
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            cfg_interval = float(data.get("auto_rotate_interval_seconds", 300))
    except Exception:
        pass

    interval = float(os.environ.get("PLATFORM_LAYER_ROTATE_SECONDS", str(cfg_interval)))

    async def _loop() -> None:
        rotator = get_layer_rotator()
        logger.info(
            "Platform layer auto-rotation started mode=%s interval=%ss",
            get_infrastructure_mode().value,
            interval,
        )
        while True:
            try:
                rotator.refresh_all()
                for layer in list(rotator._states.keys()):
                    active = rotator.active_backend(layer)
                    logger.debug(
                        "Layer tick %s active=%s at=%s",
                        layer,
                        active,
                        time.time(),
                    )
            except Exception as exc:
                logger.warning("Layer rotation tick failed: %s", exc)
            await asyncio.sleep(interval)

    _task = asyncio.create_task(_loop())


async def stop_layer_auto_rotation() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
