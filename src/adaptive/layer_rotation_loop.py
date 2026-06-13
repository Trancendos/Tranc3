"""Background health refresh and automatic rotation for platform layers.

The loop runs every `interval` seconds and:
  1. Refreshes health state for all backends in each layer.
  2. If the active backend is unhealthy, triggers rotation to the next
     healthy backend automatically (no manual intervention required).
  3. Logs rotation events for observability.
  4. Records usage against zero-cost quotas when applicable.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from src.platform.infrastructure_mode import get_infrastructure_mode
from src.platform.layer_rotator import (
    BackendHealth,
    PlatformLayer,
    get_layer_rotator,
    layer_rotation_enabled,
)

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
                _check_and_rotate(rotator)
            except Exception as exc:
                logger.warning("Layer rotation tick failed: %s", exc)
            await asyncio.sleep(interval)

    _task = asyncio.create_task(_loop())


def _check_and_rotate(rotator: object) -> None:
    """
    For each layer, if the active backend is marked unhealthy trigger rotation
    to the next available healthy backend.
    """
    from src.platform.layer_rotator import PlatformLayerRotator

    if not isinstance(rotator, PlatformLayerRotator):
        return

    for layer_value, state in list(rotator._states.items()):
        if not state.backends:
            continue

        active_name = state.backends[state.index]
        active_health: BackendHealth = state.health.get(active_name, BackendHealth(name=active_name))

        if active_health.available:
            logger.debug("Layer %s healthy on %s", layer_value, active_name)
            continue

        # Active backend is unhealthy — find next healthy backend
        rotated = False
        num_backends = len(state.backends)
        for offset in range(1, num_backends):
            candidate_idx = (state.index + offset) % num_backends
            candidate_name = state.backends[candidate_idx]
            candidate_health = state.health.get(candidate_name, BackendHealth(name=candidate_name))

            # Check cooldown
            if time.time() < candidate_health.cooldown_until:
                continue

            if candidate_health.available:
                old_name = state.backends[state.index]
                state.index = candidate_idx
                state.last_rotation_at = time.time()
                logger.warning(
                    "Layer %s auto-rotated: %s → %s (failures=%d)",
                    layer_value,
                    old_name,
                    candidate_name,
                    active_health.failures,
                )
                rotated = True
                break

        if not rotated:
            logger.error(
                "Layer %s: all backends unhealthy (active=%s, candidates=%s)",
                layer_value,
                active_name,
                state.backends,
            )


async def stop_layer_auto_rotation() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
