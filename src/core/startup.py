# src/core/startup.py
# TRANC3 Startup Validation — checks all subsystems on boot
# and provides a structured health report.
#
# Honest about what's working and what's not.
# No green-washing: if something is in bootstrap mode, we say so.

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ServiceStatus(str, Enum):
    HEALTHY   = "healthy"
    DEGRADED  = "degraded"     # Working but in fallback/bootstrap mode
    UNAVAIL   = "unavailable"  # Not working at all
    DISABLED  = "disabled"     # Intentionally turned off


@dataclass
class ServiceReport:
    name: str
    status: ServiceStatus
    message: str = ""
    latency_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


class StartupValidator:
    """
    Validates all TRANC3 subsystems at startup and on demand.
    Produces an honest health report that can be exposed via /health.
    """

    def __init__(self):
        self._reports: List[ServiceReport] = []
        self._start_time = time.monotonic()
        self._validated = False

    def validate_all(self) -> Dict[str, Any]:
        """Run all checks and return a structured health report."""
        self._reports.clear()
        t0 = time.monotonic()

        # Check each subsystem
        self._check_database()
        self._check_redis()
        self._check_auth()
        self._check_inference()
        self._check_personality()
        self._check_mcp()
        self._check_vector_store()
        self._check_observability()

        self._validated = True
        total_ms = (time.monotonic() - t0) * 1000

        # Compute overall status
        statuses = [r.status for r in self._reports]
        if all(s == ServiceStatus.HEALTHY for s in statuses):
            overall = ServiceStatus.HEALTHY
        elif any(s == ServiceStatus.UNAVAIL for s in statuses):
            overall = ServiceStatus.DEGRADED
        else:
            overall = ServiceStatus.DEGRADED

        return {
            "status": overall.value,
            "validation_time_ms": round(total_ms, 1),
            "uptime_seconds": round(time.monotonic() - self._start_time, 1),
            "services": {
                r.name: {
                    "status": r.status.value,
                    "message": r.message,
                    "latency_ms": round(r.latency_ms, 1),
                    **r.details,
                }
                for r in self._reports
            },
        }

    def _time_check(self, func) -> tuple:
        """Run a check function and time it."""
        t0 = time.monotonic()
        result = func()
        latency = (time.monotonic() - t0) * 1000
        return result, latency

    def _check_database(self):
        def check():
            db_url = os.getenv("DATABASE_URL", "")
            if not db_url:
                return ServiceReport(
                    name="database",
                    status=ServiceStatus.UNAVAIL,
                    message="DATABASE_URL not set",
                )
            try:
                from src.database.schema import DatabaseManager
                # Try connecting — the manager creates tables on init
                db_url_safe = db_url  # We won't log the URL (may contain password)
                # If we already have a global db_manager, use it
                try:
                    import api as _api
                    mgr = getattr(_api, "db_manager", None)
                    if mgr and mgr.health_check():
                        return ServiceReport(
                            name="database",
                            status=ServiceStatus.HEALTHY,
                            message="Connected and responsive",
                            details={"dialect": "sqlite" if mgr.is_sqlite else "postgresql"},
                        )
                except Exception:
                    pass

                # Try a fresh connection
                mgr = DatabaseManager(db_url)
                if mgr.health_check():
                    return ServiceReport(
                        name="database",
                        status=ServiceStatus.HEALTHY,
                        message="Connected and responsive",
                        details={"dialect": "sqlite" if mgr.is_sqlite else "postgresql"},
                    )
                return ServiceReport(
                    name="database",
                    status=ServiceStatus.UNAVAIL,
                    message="Health check failed",
                )
            except Exception as e:
                return ServiceReport(
                    name="database",
                    status=ServiceStatus.UNAVAIL,
                    message=f"Connection failed: {e}",
                )

        report, latency = self._time_check(check)
        report.latency_ms = latency
        self._reports.append(report)

    def _check_redis(self):
        def check():
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            try:
                import redis as redis_lib
                client = redis_lib.from_url(redis_url, decode_responses=True)
                client.ping()
                client.close()
                return ServiceReport(
                    name="redis",
                    status=ServiceStatus.HEALTHY,
                    message="Connected",
                    details={"url": redis_url.split("@")[-1] if "@" in redis_url else redis_url},
                )
            except Exception as e:
                return ServiceReport(
                    name="redis",
                    status=ServiceStatus.DEGRADED,
                    message=f"Unavailable: {e}. In-memory fallback active.",
                )

        report, latency = self._time_check(check)
        report.latency_ms = latency
        self._reports.append(report)

    def _check_auth(self):
        def check():
            secret = os.getenv("SECRET_KEY", "")
            if not secret:
                return ServiceReport(
                    name="auth",
                    status=ServiceStatus.UNAVAIL,
                    message="SECRET_KEY not set — auth disabled",
                )
            return ServiceReport(
                name="auth",
                status=ServiceStatus.HEALTHY,
                message="JWT auth configured",
                details={"algorithm": "HS256"},
            )

        report, latency = self._time_check(check)
        report.latency_ms = latency
        self._reports.append(report)

    def _check_inference(self):
        def check():
            # Check LLM router providers
            try:
                from src.inference.llm_router import get_router, Provider
                router = get_router()
                
                # health_check is async — run it synchronously
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # We're inside an async context already — use a thread
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            health = pool.submit(asyncio.run, router.health_check()).result()
                    else:
                        health = loop.run_until_complete(router.health_check())
                except RuntimeError:
                    health = asyncio.run(router.health_check())

                # Determine status based on available providers
                providers = health.get("providers", {})
                available = []
                for name, info in providers.items():
                    if info.get("status") in ("ok", "configured", "always_ok"):
                        available.append(name)

                if any(p in available for p in ("local", "huggingface", "groq", "openai")):
                    return ServiceReport(
                        name="inference",
                        status=ServiceStatus.HEALTHY,
                        message=f"Available providers: {', '.join(available)}",
                        details={"providers": providers},
                    )
                else:
                    return ServiceReport(
                        name="inference",
                        status=ServiceStatus.DEGRADED,
                        message="No LLM providers configured — bootstrap mode active. Set HF_API_KEY or GROQ_API_KEY.",
                        details={"providers": providers},
                    )
            except Exception as e:
                return ServiceReport(
                    name="inference",
                    status=ServiceStatus.DEGRADED,
                    message=f"Router init failed: {e}. Bootstrap fallback active.",
                )

        report, latency = self._time_check(check)
        report.latency_ms = latency
        self._reports.append(report)

    def _check_personality(self):
        def check():
            try:
                from src.personality.matrix import EnhancedPersonalityMatrix
                return ServiceReport(
                    name="personality",
                    status=ServiceStatus.HEALTHY,
                    message="Personality matrix available",
                    details={"profiles": [
                        "tranc3-base", "dorris-fontaine", "cornelius-macintyre",
                        "the-guardian", "vesper-nightingale", "atlas-meridian",
                    ]},
                )
            except Exception as e:
                return ServiceReport(
                    name="personality",
                    status=ServiceStatus.DEGRADED,
                    message=f"Personality matrix unavailable: {e}",
                )

        report, latency = self._time_check(check)
        report.latency_ms = latency
        self._reports.append(report)

    def _check_mcp(self):
        def check():
            try:
                from src.mcp.server import MCPServer
                return ServiceReport(
                    name="mcp",
                    status=ServiceStatus.HEALTHY,
                    message="MCP server available (JSON-RPC 2.0 + SSE)",
                )
            except Exception as e:
                return ServiceReport(
                    name="mcp",
                    status=ServiceStatus.DEGRADED,
                    message=f"MCP server unavailable: {e}",
                )

        report, latency = self._time_check(check)
        report.latency_ms = latency
        self._reports.append(report)

    def _check_vector_store(self):
        def check():
            try:
                from src.database.vector_store import vector_store
                return ServiceReport(
                    name="vector_store",
                    status=ServiceStatus.HEALTHY,
                    message="Vector store available",
                )
            except Exception as e:
                return ServiceReport(
                    name="vector_store",
                    status=ServiceStatus.DEGRADED,
                    message=f"Vector store unavailable: {e}",
                )

        report, latency = self._time_check(check)
        report.latency_ms = latency
        self._reports.append(report)

    def _check_observability(self):
        def check():
            try:
                from src.observability.metrics import record_request
                return ServiceReport(
                    name="observability",
                    status=ServiceStatus.HEALTHY,
                    message="Observability stack available",
                )
            except Exception as e:
                return ServiceReport(
                    name="observability",
                    status=ServiceStatus.DEGRADED,
                    message=f"Observability partial: {e}",
                )

        report, latency = self._time_check(check)
        report.latency_ms = latency
        self._reports.append(report)


# Module-level singleton
_validator: Optional[StartupValidator] = None


def get_validator() -> StartupValidator:
    global _validator
    if _validator is None:
        _validator = StartupValidator()
    return _validator
