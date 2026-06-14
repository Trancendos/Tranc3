"""APScheduler-based scheduler for the Section 7 intelligence loop."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Intelligence loop runs every 6 hours — balances freshness vs. free-tier limits.
_INTERVAL_HOURS = 6
_INTERVAL_SECONDS = _INTERVAL_HOURS * 3600

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import]
    from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import]

    _APSCHEDULER_AVAILABLE = True
except ImportError:
    _APSCHEDULER_AVAILABLE = False
    AsyncIOScheduler = None  # type: ignore[assignment]
    IntervalTrigger = None  # type: ignore[assignment]


async def _run_intelligence_loop() -> None:
    """Execute one full Section 7 intelligence cycle."""
    logger.info("Section 7: starting intelligence cycle at %s", time.strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        from src.section7.web_scraper import run_full_scrape

        results = await asyncio.to_thread(run_full_scrape)
        for intel in results:
            if intel.error:
                logger.warning("Section 7: source=%s error=%s", intel.source, intel.error)
            else:
                logger.info(
                    "Section 7: source=%s cves=%d items=%d",
                    intel.source,
                    len(intel.cve_ids),
                    len(intel.raw_items),
                )
    except Exception as exc:
        logger.error("Section 7: intelligence loop failed: %s", exc)

    try:
        from src.section7.cve_ingester import ingest_from_scrape  # type: ignore[import]

        await ingest_from_scrape()
    except Exception as exc:
        logger.debug("Section 7: cve_ingester not available: %s", exc)

    try:
        from src.section7.information_router import get_router

        router = get_router()
        await router.flush_pending()  # type: ignore[attr-defined]
    except Exception as exc:
        logger.debug("Section 7: information_router flush skipped: %s", exc)

    logger.info("Section 7: intelligence cycle complete")


class Section7Scheduler:
    """Manages the Section 7 background intelligence loop."""

    def __init__(self, interval_seconds: int = _INTERVAL_SECONDS) -> None:
        self._interval = interval_seconds
        self._scheduler: Optional[object] = None
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._running = False
        self._started = False

    def start(self) -> None:
        """Start the scheduler using APScheduler if available, else asyncio fallback."""
        if self._started:
            return
        self._started = True
        if _APSCHEDULER_AVAILABLE:
            self._scheduler = AsyncIOScheduler()
            self._scheduler.add_job(  # type: ignore[union-attr]
                _run_intelligence_loop,
                trigger=IntervalTrigger(seconds=self._interval),
                id="section7_intel_loop",
                replace_existing=True,
                max_instances=1,
            )
            self._scheduler.start()  # type: ignore[union-attr]
            logger.info("Section 7: APScheduler started (interval=%ds)", self._interval)
        else:
            # Asyncio fallback — no external dependency required.
            self._running = True
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(self._asyncio_loop())
            logger.info("Section 7: asyncio scheduler started (interval=%ds)", self._interval)

    def stop(self) -> None:
        """Gracefully stop the scheduler."""
        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=False)  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001 — ignore shutdown errors
                pass
        self._running = False
        self._started = False
        if self._task is not None:
            self._task.cancel()
        logger.info("Section 7: scheduler stopped")

    async def _asyncio_loop(self) -> None:
        """Asyncio-native loop that fires every interval."""
        while self._running:
            await _run_intelligence_loop()
            await asyncio.sleep(self._interval)

    @property
    def is_running(self) -> bool:
        if _APSCHEDULER_AVAILABLE and self._scheduler is not None:
            return self._scheduler.running  # type: ignore[union-attr]
        return self._running


_default_scheduler: Optional[Section7Scheduler] = None


def get_scheduler() -> Section7Scheduler:
    """Return the singleton scheduler instance."""
    global _default_scheduler
    if _default_scheduler is None:
        _default_scheduler = Section7Scheduler()
    return _default_scheduler


def start_scheduler() -> Section7Scheduler:
    """Start and return the singleton scheduler."""
    scheduler = get_scheduler()
    scheduler.start()
    return scheduler
