"""
Tranc3 Observability Package
=============================
Structured logging, Prometheus metrics, distributed tracing, and health aggregation.
Zero-cost: No external APM services. All data stays in-process and SQLite.

Why the re-exports below are lazy
---------------------------------
This module used to import `health`, `metrics` and `tracing` eagerly, purely
to offer 25 convenience names at the package root. **Nothing in the
repository imports any of those 25 names from here** — the only importer of
the package root is `tests/test_library_pipeline.py`, and it imports a
submodule. So the convenience API had no consumers, and it had a real cost:
a package `__init__` runs before any module inside it, so

    from src.observability.observatory import EventCategory

executed this file and pulled in `aiohttp`, `structlog` and the whole
metrics/tracing/health chain — even though `observatory.py` itself is
standard library plus one in-repo helper.

That cost was not theoretical. It broke this PR's own Service Topology job
at 596a4431, on a runner that installs only PyYAML and pydantic, and it is
why `src/validation/validators.py` had to defer its enum import — which in
turn made `typing.get_type_hints(audit_action)` fail. One eager import in a
package `__init__` produced a CI break and a broken public signature two
modules away.

PEP 562 keeps the convenience API exactly as it was — `from
src.observability import HealthChecker` still works — while charging its
cost only to callers that actually use it.
"""

from importlib import import_module
from typing import Any

#: Public name -> the submodule that defines it. Resolved on first access
#: and cached into this module's globals, so the second access is a plain
#: dict lookup and repeated use costs nothing.
_LAZY: dict[str, str] = {
    # Health
    "SERVICE_REGISTRY": ".health",
    "HealthChecker": ".health",
    "SystemHealth": ".health",
    # Metrics
    "PROMETHEUS_AVAILABLE": ".metrics",
    "log": ".metrics",
    "record_churn_risk": ".metrics",
    "record_emotion": ".metrics",
    "record_phi": ".metrics",
    "record_quality": ".metrics",
    "record_request": ".metrics",
    "record_revenue": ".metrics",
    "record_tokens": ".metrics",
    "timed_operation": ".metrics",
    # Tracing
    "Span": ".tracing",
    "Tracer": ".tracing",
    "clear_trace": ".tracing",
    "current_span_id": ".tracing",
    "current_trace_id": ".tracing",
    "extract_trace_context": ".tracing",
    "get_tracer": ".tracing",
    "init_tracing": ".tracing",
    "inject_trace_context": ".tracing",
    "new_span_id": ".tracing",
    "new_trace_id": ".tracing",
    "set_trace": ".tracing",
}


def __getattr__(name: str) -> Any:
    """Resolve a re-exported name on first access (PEP 562)."""
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY})


__all__ = sorted(_LAZY)
