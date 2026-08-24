# Dimensional/__init__.py
# Trancendos Dimensional — the Shared Functional Services Core (SFSC).
#
# WHY THIS PACKAGE IMPORTS LAZILY
#
# This file used to import its whole surface eagerly: eight submodules by name
# plus `from . import dimensionals, gas, genetics, infinity, liquid`. That made
# `import Dimensional` pull 1342 modules, among them torch, numpy, cuda, ncps
# and dill — because `genetics` and `liquid` reach into the ML stack.
#
# The cost was not startup time, it was reach. A worker installs only its own
# `requirements-worker.txt`; geo-service, for instance, has fastapi, starlette,
# uvicorn, pydantic and httpx. For such a worker
#
#     from Dimensional.service_auth import verify_internal_secret
#
# raised ImportError on torch before reaching `service_auth` — even though
# `service_auth` itself imports nothing but `hmac` and `os`. The eager package
# import made a stdlib-only module unreachable to the services that need it.
#
# That is the reason 41 services each hand-rolled their own X-Internal-Secret
# check rather than sharing one: the shared one could not be imported. Four of
# those hand-rolled copies failed open and 18 compared secrets with `!=`. The
# eager import was not a performance detail; it was the thing keeping the shared
# core from being shared.
#
# PEP 562 module `__getattr__` keeps the public API exactly as it was —
# `from Dimensional import EventBus` still works, and still returns the same
# object — while importing only what is actually asked for. A consumer that
# wants a stdlib-only submodule now pays for a stdlib-only submodule.

from __future__ import annotations

import importlib
from typing import Any

# Exported name -> the submodule that defines it. Kept as data rather than as
# import statements so that resolving one name cannot drag in the others.
_EXPORTS: dict[str, str] = {
    # Models
    "ServiceInfo": ".models",
    "ServiceHealth": ".models",
    "ServiceCapability": ".models",
    "EventMessage": ".models",
    "VectorClock": ".models",
    # Registry
    "ServiceRegistry": ".registry",
    # Bus
    "EventBus": ".bus",
    # Security
    "generate_jwt": ".security",
    "verify_jwt": ".security",
    "hash_password": ".security",
    "verify_password": ".security",
    # Path validation
    "PathTraversalError": ".path_validation",
    "validate_path": ".path_validation",
    "safe_join": ".path_validation",
    "sanitize_filename": ".path_validation",
    # Error handlers
    "safe_error_detail": ".error_handlers",
    "SafeHTTPException": ".error_handlers",
    # Log sanitization
    "sanitize_for_log": ".sanitize",
    "sanitize_dict_for_log": ".sanitize",
    "SafeLogger": ".sanitize",
    # Utilities
    "LazyLoader": ".optional_import",
}

# Subpackages that were previously imported eagerly so they were reachable as
# attributes of `Dimensional` after a bare `import Dimensional`. They stay
# reachable, on demand. `import Dimensional.infinity` never needed this entry —
# Python binds a submodule on its parent as part of importing it — but
# `Dimensional.infinity` after only `import Dimensional` does.
_SUBMODULES = ("dimensionals", "gas", "genetics", "infinity", "liquid")

# The submodules are deliberately NOT in `__all__`, matching what it listed
# before this file went lazy. `shared_core/__init__.py` does
# `from Dimensional import *`; adding the submodules here would make that star
# import pull `genetics` and `liquid` — and with them torch and numpy — undoing
# the whole point for every consumer of shared_core. They stay reachable as
# attributes through `__getattr__`, which does not consult `__all__`.
__all__ = list(_EXPORTS)

__version__ = "0.7.0"


def __getattr__(name: str) -> Any:
    """Resolve an exported name on first access, importing only its submodule.

    The resolved object is cached in the module globals, so the import cost is
    paid once and later accesses are ordinary attribute lookups. Anything not
    exported raises AttributeError with the standard message, so typos still
    fail the way they always did rather than turning into an obscure ImportError.
    """
    if name in _EXPORTS:
        module = importlib.import_module(_EXPORTS[name], __name__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    if name in _SUBMODULES:
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Report the full public surface without importing any of it.

    Without this, `dir(Dimensional)` would list only what has been resolved so
    far, making the package look progressively larger as a program runs and
    breaking tab-completion for anything not yet touched.
    """
    return sorted({*globals(), *__all__})
