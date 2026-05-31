"""Auto and manual backups for Admin OS workspace + entity DB."""

from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.admin_os.db import db_path, get_setting, list_backup_log, log_backup, set_setting
from src.admin_os.files_manager import workspace_root

_BACKUP_ROOT = Path(os.environ.get("ADMIN_OS_BACKUP_DIR", "data/admin_os_backups"))
_DEFAULT_INTERVAL_HOURS = float(os.environ.get("ADMIN_OS_AUTO_BACKUP_HOURS", "24"))


def backup_config() -> dict[str, Any]:
    raw = get_setting("auto_backup_hours", str(_DEFAULT_INTERVAL_HOURS))
    try:
        hours = float(raw)
    except ValueError:
        hours = _DEFAULT_INTERVAL_HOURS
    return {
        "auto_backup_enabled": get_setting("auto_backup_enabled", "true").lower()
        in ("1", "true", "yes"),
        "auto_backup_hours": hours,
        "backup_root": str(_BACKUP_ROOT.resolve()),
        "last_backup_at": get_setting("last_backup_at", ""),
    }


def update_backup_config(
    *,
    enabled: bool | None = None,
    hours: float | None = None,
) -> dict[str, Any]:
    if enabled is not None:
        set_setting("auto_backup_enabled", "true" if enabled else "false")
    if hours is not None:
        set_setting("auto_backup_hours", str(hours))
    return backup_config()


def run_backup(trigger: str = "manual") -> dict[str, Any]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bid = uuid.uuid4().hex[:12]
    dest = _BACKUP_ROOT / f"backup-{stamp}-{bid}"
    dest.mkdir(parents=True, exist_ok=True)

    total = 0
    ws = workspace_root()
    if ws.is_dir():
        ws_dest = dest / "workspace"
        shutil.copytree(ws, ws_dest, dirs_exist_ok=True)
        total += sum(f.stat().st_size for f in ws_dest.rglob("*") if f.is_file())

    db = db_path()
    if db.is_file():
        db_dest = dest / "infinity_admin.db"
        shutil.copy2(db, db_dest)
        total += db_dest.stat().st_size

    log_backup(bid, str(dest), total, trigger)
    set_setting("last_backup_at", datetime.now(timezone.utc).isoformat())

    return {
        "id": bid,
        "path": str(dest),
        "size_bytes": total,
        "trigger": trigger,
        "created_at": stamp,
    }


def list_backups(limit: int = 30) -> list[dict[str, Any]]:
    logs = list_backup_log(limit)
    for row in logs:
        p = Path(row["path"])
        row["exists"] = p.is_dir()
    return logs
