"""Async web scraper for Section 7 threat intelligence gathering."""

from __future__ import annotations

import gzip
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Rate limiting: 1 req/sec is the floor imposed by all free sources.
_MIN_INTERVAL = 1.0
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0

# Free-tier source endpoints — no API keys required.
_NVD_RECENT_URL = "https://nvd.nist.gov/feeds/json/cve/1.1/nvdcve-1.1-recent.json.gz"
_OPENCVE_URL = "https://www.opencve.io/api/cve"
_GITHUB_ADVISORIES_URL = "https://api.github.com/advisories"


@dataclass
class ThreatIntel:
    """Structured output from a single scrape run."""

    source: str
    fetched_at: float = field(default_factory=time.time)
    cve_ids: list[str] = field(default_factory=list)
    raw_items: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


def _sleep(seconds: float) -> None:
    """Isolated sleep — patched in tests."""
    time.sleep(seconds)


def _fetch_url(
    url: str, *, headers: Optional[dict[str, str]] = None, timeout: float = 10.0
) -> bytes:
    """Synchronous HTTP GET with exponential backoff; stdlib only."""
    import urllib.request

    hdrs = {"User-Agent": "tranc3-section7/1.0 (threat-intel; +https://trancendos.com)"}
    if headers:
        hdrs.update(headers)

    from urllib.parse import urlparse as _urlparse

    _scheme = _urlparse(url).scheme
    if _scheme not in ("http", "https"):
        raise ValueError(f"_fetch_url: only http/https URLs are permitted, got scheme {_scheme!r}")

    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_MAX_RETRIES):
        if attempt > 0:
            _sleep(_BACKOFF_BASE**attempt)
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — scheme validated above
                return resp.read()
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "fetch attempt %d/%d failed for %s: %s", attempt + 1, _MAX_RETRIES, url, exc
            )
    raise last_exc


def scrape_nvd_recent() -> ThreatIntel:
    """Fetch and decompress the NVD recent CVE feed (gzipped JSON)."""
    intel = ThreatIntel(source="nvd")
    try:
        raw = _fetch_url(_NVD_RECENT_URL)
        data = json.loads(gzip.decompress(raw))
        for item in data.get("CVE_Items", []):
            cve_id = item.get("cve", {}).get("CVE_data_meta", {}).get("ID", "")
            if cve_id:
                intel.cve_ids.append(cve_id)
            intel.raw_items.append(item)
        _sleep(_MIN_INTERVAL)
    except Exception as exc:
        intel.error = str(exc)
        logger.error("NVD scrape failed: %s", exc)
    return intel


def scrape_opencve(page: int = 1, limit: int = 20) -> ThreatIntel:
    """Fetch CVEs from OpenCVE free API (unauthenticated, paginated)."""
    intel = ThreatIntel(source="opencve")
    try:
        url = f"{_OPENCVE_URL}?page={page}&limit={limit}"
        raw = _fetch_url(url)
        items = json.loads(raw)
        if isinstance(items, list):
            for item in items:
                cve_id = item.get("id") or item.get("cve_id", "")
                if cve_id:
                    intel.cve_ids.append(cve_id)
                intel.raw_items.append(item)
        elif isinstance(items, dict):
            intel.raw_items.append(items)
        _sleep(_MIN_INTERVAL)
    except Exception as exc:
        intel.error = str(exc)
        logger.error("OpenCVE scrape failed: %s", exc)
    return intel


def scrape_github_advisories(per_page: int = 30) -> ThreatIntel:
    """Fetch GitHub Security Advisories — unauthenticated, free tier."""
    intel = ThreatIntel(source="github_advisories")
    try:
        url = f"{_GITHUB_ADVISORIES_URL}?per_page={per_page}&type=reviewed"
        # GitHub unauthenticated rate limit: 60 req/hr — well within our 1 req/6hr cadence.
        raw = _fetch_url(url, headers={"Accept": "application/vnd.github+json"})
        items = json.loads(raw)
        for item in items if isinstance(items, list) else []:
            cve_id = item.get("cve_id")
            if cve_id and isinstance(cve_id, str):
                intel.cve_ids.append(cve_id)
            intel.raw_items.append(item)
        _sleep(_MIN_INTERVAL)
    except Exception as exc:
        intel.error = str(exc)
        logger.error("GitHub Advisories scrape failed: %s", exc)
    return intel


def run_full_scrape() -> list[ThreatIntel]:
    """Execute all free-tier scrape sources in sequence; return collected intel."""
    return [
        scrape_nvd_recent(),
        scrape_opencve(),
        scrape_github_advisories(),
    ]
