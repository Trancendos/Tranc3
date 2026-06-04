"""System viewer — platform health, infrastructure mode, worker map."""

from __future__ import annotations

import os
import platform
import sys
import time
from typing import Any

from src.entities.platform import PLATFORM_ENTITIES
from src.platform.infrastructure_mode import infrastructure_status


def _worker_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for entity in PLATFORM_ENTITIES.values():
        port = getattr(entity, "worker_port", None)
        if port and port not in seen:
            seen.add(port)
            rows.append(
                {
                    "port": port,
                    "location": entity.location,
                    "pid": getattr(entity, "pid", None),
                    "path": getattr(entity, "worker_path", None),
                },
            )
    rows.sort(key=lambda r: r["port"] or 0)
    rows.append({"port": 8000, "location": "tranc3-backend", "pid": "API", "path": "/"})
    rows.append(
        {
            "port": 8044,
            "location": "Infinity-Admin",
            "pid": "ADM",
            "path": "workers/infinity-admin-service/",
        },
    )
    return rows


def system_snapshot() -> dict[str, Any]:
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cwd": os.getcwd(),
        "uptime_hint": time.time(),
        "infrastructure": infrastructure_status(),
        "workers": _worker_catalog(),
        "env": {
            "PLATFORM_INFRA_MODE": os.environ.get("PLATFORM_INFRA_MODE", ""),
            "ENVIRONMENT": os.environ.get("ENVIRONMENT", "development"),
            "ADMIN_OS_WORKSPACE_ROOT": os.environ.get(
                "ADMIN_OS_WORKSPACE_ROOT",
                "data/admin_os_workspace",
            ),
        },
    }
