"""Quota Rotation Daemon — watches all provider quotas and rotates at threshold.

Runs as a background asyncio task.  Every `interval` seconds it:
  1. Reads the current quota state from QuotaEnforcer.
  2. If *any* provider's usage crosses the hard-stop threshold (default 80 %),
     it calls next_provider() to select the replacement and emits an
     Observatory audit event so the rotation is visible in The Observatory.
  3. Publishes a rotation event to the platform EventBus.
  4. If ALL providers (including offline) are blocked it logs a CRITICAL
     alert and sets the global active provider to "offline".

The loop never raises — all exceptions are caught and logged so a single
bad cycle cannot crash the background task.

Usage (in FastAPI lifespan):
    from src.adaptive.quota_rotation_loop import start_quota_rotation

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(start_quota_rotation())
        yield
        task.cancel()
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("tranc3.adaptive.quota_rotation")

# ── Config ─────────────────────────────────────────────────────────────────────

_INTERVAL: int = int(os.environ.get("QUOTA_ROTATION_INTERVAL", "30"))
_THRESHOLD: float = float(os.environ.get("QUOTA_THRESHOLD_PCT", "80"))

# ── Global active provider (shared state) ──────────────────────────────────────

_active_provider: str = "ollama"
_last_rotation_at: float = 0.0
_rotation_cooldown: float = float(os.environ.get("QUOTA_ROTATION_COOLDOWN", "60"))


def get_active_provider() -> str:
    """Return the currently selected zero-cost provider."""
    return _active_provider


def set_active_provider(provider: str) -> None:
    """Override the active provider (for testing or manual intervention)."""
    global _active_provider
    _active_provider = provider


# ── Rotation helpers ───────────────────────────────────────────────────────────


def _emit_observatory(event_type: str, **kwargs) -> None:
    """Fire-and-forget audit event to The Observatory."""
    try:
        from src.observability.observatory import EventCategory, observe

        observe(
            event_type,
            service="quota_rotation_loop",
            category=EventCategory.SYSTEM,
            **kwargs,
        )
    except Exception:
        pass  # observability is optional; startup must not block


def _emit_event_bus(payload: dict) -> None:
    """Publish rotation event to platform EventBus if available."""
    try:
        from src.event_bus.bus import get_event_bus

        bus = get_event_bus()
        asyncio.create_task(bus.publish("quota.rotation", payload))
    except Exception:
        pass  # event bus is optional; startup must not block


def _check_and_rotate() -> Optional[str]:
    """
    Check all provider quotas.  Returns the new provider name if rotation
    occurred, or None if no change was needed.
    """
    global _active_provider, _last_rotation_at

    try:
        from src.mesh.quota_enforcer import get_enforcer
    except ImportError:
        logger.debug("quota_enforcer not available — skipping rotation check")
        return None

    enforcer = get_enforcer()
    now = time.monotonic()

    # Enforce cooldown between rotations to prevent thrashing
    if now - _last_rotation_at < _rotation_cooldown:
        return None

    statuses = {s.provider: s for s in enforcer.all_statuses()}
    current = _active_provider
    current_status = statuses.get(current)

    if current_status is None or current_status.available:
        return None  # Current provider is fine

    # Current provider hit its threshold — find the next available one
    blocked_reason = current_status.blocked_reason or "threshold exceeded"
    new_provider = enforcer.next_provider(current)

    if new_provider == current:
        # All providers exhausted — stay on offline
        logger.critical(
            "quota_rotation: all providers at threshold — forcing offline; current=%s reason=%s",
            current,
            blocked_reason,
        )
        _emit_observatory(
            "quota.all_providers_blocked",
            severity="critical",
            metadata={"current": current, "reason": blocked_reason},
        )
        _active_provider = "offline"
        _last_rotation_at = now
        return "offline"

    logger.warning(
        "quota_rotation: rotating %s → %s (reason: %s)",
        current,
        new_provider,
        blocked_reason,
    )

    _active_provider = new_provider
    _last_rotation_at = now

    payload = {
        "from_provider": current,
        "to_provider": new_provider,
        "reason": blocked_reason,
        "threshold_pct": enforcer.threshold_pct,
    }
    _emit_observatory(
        "quota.provider_rotated",
        severity="warning",
        metadata=payload,
    )
    _emit_event_bus(payload)

    return new_provider


async def _rotation_loop() -> None:
    """Async background loop — runs forever until task is cancelled."""
    logger.info(
        "quota_rotation_loop started (interval=%ds threshold=%.0f%%)",
        _INTERVAL,
        _THRESHOLD,
    )
    while True:
        try:
            new = _check_and_rotate()
            if new:
                logger.info("quota_rotation: active provider → %s", new)
        except Exception as exc:
            logger.error("quota_rotation: unexpected error: %s", exc)
        await asyncio.sleep(_INTERVAL)


async def start_quota_rotation() -> None:
    """Entry-point coroutine — await this or wrap in asyncio.create_task()."""
    await _rotation_loop()
