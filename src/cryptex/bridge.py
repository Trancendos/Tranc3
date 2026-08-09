# src/cryptex/bridge.py
# Bridge between the in-process Cryptex threat detector (per-process,
# memory-only — src/cryptex/threat_detector.py's Cryptex._blocked_ips) and
# workers/cryptex/'s durable, shared IOC database.
#
# Two fail-open, non-blocking mechanisms, both deliberately kept off the hot
# request path so request latency never depends on the worker being up:
#
# 1. Periodic background sync (start_background_sync): pulls the worker's
#    current "ip"-type IOC list into the in-process Cryptex._blocked_ips set
#    every CRYPTEX_SYNC_INTERVAL_SECONDS, so a block recorded by any
#    Trancendos process eventually becomes visible on every other process
#    too — a genuine correctness gap otherwise, since is_blocked() only ever
#    saw its own process's memory. A failed sync just skips that cycle; the
#    in-process set keeps whatever it already had (nothing is ever evicted
#    by a failed sync).
# 2. Fire-and-forget forward (forward_block_ip): when this process blocks an
#    IP itself, also POST it to the worker so every other process picks it
#    up on its next sync. Same fire-and-forget, capped-concurrency pattern
#    as src/nexus/hub.py and src/basement/bridge.py.
#
# Both mechanisms are best-effort by explicit product decision (2026-08-08:
# fail-open across basement/cryptex/billing). If workers/cryptex/ is
# unreachable, request handling is entirely unaffected — the in-process,
# per-process Cryptex check remains the sole gate, exactly as it behaved
# before this bridge existed. `is_blocked()` itself is never modified to
# call out over the network; it stays a pure in-memory set lookup.
#
# Hardening pass (post-implementation, same 2026-08-08 decision): a shared
# CircuitBreaker gates both the sync loop and the forward path so a
# sustained outage stops attempting doomed connections on schedule and
# self-probes back to closed once the worker recovers.

from __future__ import annotations

import asyncio
import logging
import os

from Dimensional.sanitize import sanitize_for_log

from src.mesh.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

_CRYPTEX_URL = os.environ.get("CRYPTEX_URL", "http://cryptex:8053")
_CRYPTEX_INTERNAL_SECRET = os.environ.get("CRYPTEX_INTERNAL_SECRET", "")

_SYNC_INTERVAL_SECONDS = float(os.environ.get("CRYPTEX_SYNC_INTERVAL_SECONDS", "30"))
_FORWARD_CONCURRENCY = int(os.environ.get("CRYPTEX_FORWARD_CONCURRENCY", "10"))
_forward_inflight = 0

_sync_task: "asyncio.Task | None" = None

_circuit = CircuitBreaker("cryptex")


def _headers() -> dict:
    return {"X-Internal-Secret": _CRYPTEX_INTERNAL_SECRET} if _CRYPTEX_INTERNAL_SECRET else {}


async def start_background_sync() -> None:
    """Start the periodic IOC sync loop. Idempotent — safe to call more than
    once (e.g. from a lifespan that could theoretically re-run)."""
    global _sync_task
    if _sync_task is not None and not _sync_task.done():
        return
    _sync_task = asyncio.create_task(_sync_loop())


async def _sync_loop() -> None:
    while True:
        if _circuit.can_execute():
            try:
                await _sync_once()
                _circuit.record_success()
            except Exception as exc:
                _circuit.record_failure()
                logger.debug(
                    "cryptex: background IOC sync skipped: %s", sanitize_for_log(exc)
                )  # codeql[py/cleartext-logging]
        await asyncio.sleep(_SYNC_INTERVAL_SECONDS)


async def _sync_once() -> None:
    import httpx

    from src.cryptex.threat_detector import get_cryptex

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{_CRYPTEX_URL}/intel",
            params={"ioc_type": "ip", "limit": 1000},
            headers=_headers(),
        )
        response.raise_for_status()
        data = response.json()

    cx = get_cryptex()
    for indicator in data.get("indicators", []):
        ip = indicator.get("value")
        if ip:
            # Direct set write, not block_ip() — block_ip() forwards back to
            # the worker, which would just re-ingest an indicator the worker
            # already has on every sync cycle.
            cx._blocked_ips.add(ip)  # noqa: SLF001


def forward_block_ip(ip: str, reason: str = "") -> None:
    """Fire-and-forget: push a locally-recorded IP block to the worker so
    other processes pick it up on their next sync. Fail-open — never raises,
    never blocks the caller."""
    global _forward_inflight
    if not _circuit.can_execute():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _forward_inflight >= _FORWARD_CONCURRENCY:
        return
    _forward_inflight += 1
    loop.create_task(_post_block(ip, reason))


async def _post_block(ip: str, reason: str) -> None:
    global _forward_inflight
    try:
        import httpx

        payload = {
            "ioc_type": "ip",
            "value": ip,
            "severity": "critical",
            "source": "cryptex-in-process-block",
            "tags": ["blocked"] + ([reason] if reason else []),
        }
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{_CRYPTEX_URL}/intel/ingest",
                json=payload,
                headers=_headers(),
            )
            response.raise_for_status()
        _circuit.record_success()
    except Exception as exc:
        _circuit.record_failure()
        safe_ip = str(ip).replace("\r", "").replace("\n", "")
        logger.debug(
            "cryptex: block-ip forward skipped (ip=%s): %s",
            safe_ip,
            sanitize_for_log(exc),
        )  # codeql[py/cleartext-logging]
    finally:
        _forward_inflight -= 1
