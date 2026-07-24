"""Adaptive Fabric admin surface — status + live system-load feed.

Wraps src.core.adaptive_fabric.fabric (the module-level AdaptiveFabric
singleton) so its DimensionalContext.load reflects real system pressure
instead of permanently-zero placeholder values, and exposes fabric status
for observability.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Union

from src.core.adaptive_fabric import fabric as _fabric


def _current_load() -> Dict[str, Union[float, int]]:
    try:
        load1, _, _ = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        cpu_fraction = min(1.0, load1 / cpu_count)
    except (OSError, AttributeError):
        # os.getloadavg() is POSIX-only.
        cpu_fraction = 0.0
    return {"cpu": cpu_fraction, "memory": 0.0, "queue_depth": 0}


def status() -> Dict[str, Any]:
    load = _current_load()
    _fabric.context.load.value = load
    result = _fabric.status()
    result["context"]["load"] = load
    return result
