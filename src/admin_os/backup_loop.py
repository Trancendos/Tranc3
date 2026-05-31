"""Background auto-backup for Admin OS workspace."""

from __future__ import annotations

import asyncio
import logging
import time

from src.admin_os import backups

logger = logging.getLogger("tranc3.admin_os.backup")

_task: asyncio.Task[None] | None = None


async def start_admin_os_auto_backup() -> None:
    global _task
    if _task is not None:
        return
    cfg = backups.backup_config()
    if not cfg.get("auto_backup_enabled"):
        logger.info("Admin OS auto-backup disabled")
        return

    async def _loop() -> None:
        while True:
            cfg_inner = backups.backup_config()
            hours = float(cfg_inner.get("auto_backup_hours", 24))
            await asyncio.sleep(max(hours * 3600, 3600))
            try:
                if backups.backup_config().get("auto_backup_enabled"):
                    result = backups.run_backup(trigger="auto")
                    logger.info("Admin OS auto-backup %s (%s bytes)", result["id"], result["size_bytes"])
            except Exception as exc:
                logger.warning("Admin OS auto-backup failed: %s", exc)

    _task = asyncio.create_task(_loop())
    logger.info("Admin OS auto-backup loop started")


async def stop_admin_os_auto_backup() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
