from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path

_ROOT_MODULE_NAME = "_tranc3_root_api"
_load_lock = threading.RLock()


def _load_root_app():
    with _load_lock:
        module = sys.modules.get(_ROOT_MODULE_NAME)
        if module is None:
            api_path = Path(__file__).parent.parent / "api.py"
            spec = importlib.util.spec_from_file_location(_ROOT_MODULE_NAME, str(api_path))
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load api.py from {api_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[_ROOT_MODULE_NAME] = module
            try:
                spec.loader.exec_module(module)  # type: ignore[union-attr]
            except Exception:
                sys.modules.pop(_ROOT_MODULE_NAME, None)
                raise
        return module.app


def __getattr__(name: str):
    if name != "app":
        raise AttributeError(name)
    app = _load_root_app()
    globals()["app"] = app
    return app
