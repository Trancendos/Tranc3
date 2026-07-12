# tests/_worker_import_utils.py
"""Shared helper for importing hyphenated worker packages in tests.

Used by tests/test_workers_p0.py through test_workers_p3.py to load each
worker's worker.py as a uniquely-named module, since hyphenated directory
names (e.g. workers/infinity-ai/) aren't valid Python package names.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Many workers use identically-named internal modules (main.py, router.py,
# config.py, database.py, service.py, models.py). A bare `from router import
# x` caches under sys.modules["router"] — without eviction, the *next*
# worker's `from router import y` would silently reuse the first worker's
# cached module instead of re-resolving against its own sys.path entry.
# Evict + restore around each import so every worker gets a fresh resolution
# of its own same-named siblings.
_SHIM_MODULE_NAMES = ("main", "router", "config", "database", "service", "models")


def import_worker(module_dotted: str, file_path: Path):
    """Import a worker module with a hyphenated path using importlib.

    Adds the worker's own directory to sys.path for the duration of the
    import so shim-style workers (e.g. infinity-ai's worker.py -> main.py)
    can resolve their bare sibling imports, matching how the Dockerfile
    COPYs them flat into the container's WORKDIR.
    """
    worker_dir = str(file_path.parent)
    inserted = worker_dir not in sys.path
    if inserted:
        sys.path.insert(0, worker_dir)
    saved = {name: sys.modules.pop(name, None) for name in _SHIM_MODULE_NAMES}
    try:
        spec = importlib.util.spec_from_file_location(module_dotted, str(file_path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_dotted] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if inserted:
            sys.path.remove(worker_dir)
        for name, old_mod in saved.items():
            if old_mod is not None:
                sys.modules[name] = old_mod
            else:
                sys.modules.pop(name, None)
