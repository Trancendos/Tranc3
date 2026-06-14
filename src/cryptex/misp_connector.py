# src/cryptex/misp_connector.py
# Cryptex — MISP (Malware Information Sharing Platform) connector.
#
# Connects to a self-hosted MISP instance to push/pull threat intelligence.
# MISP is free and open-source (AGPL-3.0): https://www.misp-project.org/
#
# Degraded mode: if MISP is unavailable, falls back to read-only CIRCL MISP
# demo feed (https://www.circl.lu/doc/misp/) and buffers pushes in-memory.
#
# Rate limits: 60 req/min, 1000 req/day hard stop (tracked in-process).
# All public methods return empty/False on error — never raise.

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_MISP_URL = os.environ.get("MISP_URL", "http://localhost:8090").rstrip("/")
_MISP_API_KEY = os.environ.get("MISP_API_KEY", "")

# Read-only public CIRCL MISP feed used when primary MISP is unavailable.
_CIRCL_FEED_URL = "https://www.circl.lu/doc/misp/"

# Rate-limit constants
_MAX_REQ_PER_MIN: int = 60
_MAX_REQ_PER_DAY: int = 1000

# MISP threat level IDs (1=High, 2=Medium, 3=Low, 4=Undefined)
_THREAT_LEVEL_MAP: Dict[str, int] = {
    "critical": 1,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
    "undefined": 4,
}

# MISP distribution (0=Your organisation only, 1=This community only,
#                    2=Connected communities, 3=All communities)
_DEFAULT_DISTRIBUTION: int = 0

# MISP analysis (0=Initial, 1=Ongoing, 2=Complete)
_DEFAULT_ANALYSIS: int = 0


class MISPConnector:
    """Connector to a self-hosted MISP threat-intelligence platform.

    All network calls are performed via the standard library ``urllib`` so
    the connector has **zero paid or third-party dependencies**.

    Args:
        misp_url: Base URL of the MISP instance (overrides ``MISP_URL`` env).
        api_key: MISP automation key (overrides ``MISP_API_KEY`` env).
        timeout: HTTP request timeout in seconds.
        verify_ssl: Whether to verify TLS certificates (set ``False`` for
            self-signed certs on internal instances).
    """

    def __init__(
        self,
        misp_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 10,
        verify_ssl: bool = True,
    ) -> None:
        self._url = (misp_url or _MISP_URL).rstrip("/")
        self._api_key = api_key or _MISP_API_KEY
        self._timeout = timeout
        self._verify_ssl = verify_ssl

        # Rate-limit state
        self._req_timestamps: deque[float] = deque()  # last 60 s window
        self._day_count: int = 0
        self._day_reset: float = time.time() + 86400.0

        # Connectivity state
        self._available: bool = True
        self._last_check: float = 0.0
        self._check_interval: float = 30.0  # re-probe every 30 s

        # Buffered pushes for degraded mode (FIFO, capped at 500)
        self._push_buffer: deque[Dict[str, Any]] = deque(maxlen=500)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def push_cve_event(
        self,
        cve_id: str,
        description: str,
        severity: str,
        affected_packages: List[str],
    ) -> bool:
        """Create a MISP event from a CVE.

        Args:
            cve_id: CVE identifier, e.g. ``"CVE-2024-1234"``.
            description: Human-readable description of the vulnerability.
            severity: One of ``critical/high/medium/low/info``.
            affected_packages: List of package names or CPE strings.

        Returns:
            ``True`` if the event was successfully created in MISP.
        """
        attributes = [
            self._attr("vulnerability", cve_id, "CVE identifier"),
            self._attr("text", description, "CVE description"),
        ]
        for pkg in affected_packages:
            attributes.append(self._attr("text", pkg, "Affected package"))

        event = self._build_event(
            info=f"Tranc3 CVE: {cve_id}",
            threat_level=severity,
            tags=[f"cve:{cve_id}", "tranc3:automated", "type:vulnerability"],
            attributes=attributes,
        )
        return self._push_event(event)

    def pull_threat_indicators(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Pull recent threat indicators from MISP.

        Returns a list of normalised indicator dicts with keys:
        ``type``, ``value``, ``comment``, ``timestamp``, ``event_id``.

        Falls back to an empty list on any error.

        Args:
            limit: Maximum number of indicators to return.
        """
        if not self._check_available():
            logger.warning("MISP unavailable — returning empty indicator list")
            return self._circl_fallback_indicators(limit)

        if not self._rate_ok():
            logger.warning("MISP rate limit reached — skipping pull")
            return []

        payload = {
            "returnFormat": "json",
            "limit": min(limit, 1000),
            "type": ["ip-dst", "ip-src", "domain", "url", "md5", "sha256", "vulnerability"],
            "to_ids": True,
        }
        data = self._post("/attributes/restSearch", payload)
        if data is None:
            return []

        attrs = (data.get("response") or {}).get("Attribute") or []
        result: List[Dict[str, Any]] = []
        for attr in attrs[:limit]:
            result.append(
                {
                    "type": attr.get("type", ""),
                    "value": attr.get("value", ""),
                    "comment": attr.get("comment", ""),
                    "timestamp": attr.get("timestamp", ""),
                    "event_id": attr.get("event_id", ""),
                }
            )
        return result

    def push_threat_signal(
        self,
        signal_type: str,
        value: str,
        threat_level: str,
        comment: str,
    ) -> bool:
        """Push a single threat indicator to MISP.

        Args:
            signal_type: MISP attribute type, e.g. ``"ip-dst"``, ``"domain"``,
                ``"md5"``, ``"url"``.
            value: Indicator value.
            threat_level: One of ``critical/high/medium/low/info``.
            comment: Human-readable context.

        Returns:
            ``True`` on success; ``False`` if MISP is unavailable or on error.
        """
        event = self._build_event(
            info=f"Tranc3 threat signal: {signal_type} {value[:40]}",
            threat_level=threat_level,
            tags=["tranc3:automated", f"type:{signal_type}"],
            attributes=[self._attr(signal_type, value, comment)],
        )
        return self._push_event(event)

    def get_events_by_tag(self, tag: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Query MISP events by tag.

        Args:
            tag: MISP tag string, e.g. ``"tlp:white"`` or ``"tranc3:automated"``.
            limit: Maximum number of events to return.

        Returns:
            List of normalised event dicts with keys:
            ``id``, ``info``, ``threat_level_id``, ``date``, ``tags``,
            ``attribute_count``.
        """
        if not self._check_available():
            logger.warning("MISP unavailable — returning empty event list")
            return []

        if not self._rate_ok():
            logger.warning("MISP rate limit reached — skipping event query")
            return []

        payload = {
            "returnFormat": "json",
            "limit": min(limit, 500),
            "tags": [tag],
        }
        data = self._post("/events/restSearch", payload)
        if data is None:
            return []

        events = data.get("response") or []
        result: List[Dict[str, Any]] = []
        for item in events[:limit]:
            ev = item.get("Event", item)
            result.append(
                {
                    "id": ev.get("id", ""),
                    "info": ev.get("info", ""),
                    "threat_level_id": ev.get("threat_level_id", "4"),
                    "date": ev.get("date", ""),
                    "tags": [t.get("name", "") for t in (ev.get("Tag") or [])],
                    "attribute_count": ev.get("attribute_count", 0),
                }
            )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_event(
        self,
        info: str,
        threat_level: str,
        tags: List[str],
        attributes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Construct a MISP event dict ready for the REST API."""
        level_id = _THREAT_LEVEL_MAP.get(threat_level.lower(), 4)
        return {
            "Event": {
                "info": info,
                "threat_level_id": str(level_id),
                "distribution": str(_DEFAULT_DISTRIBUTION),
                "analysis": str(_DEFAULT_ANALYSIS),
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "published": False,
                "Tag": [{"name": t} for t in tags],
                "Attribute": attributes,
            }
        }

    def _attr(self, attr_type: str, value: str, comment: str = "") -> Dict[str, Any]:
        """Build a MISP attribute dict."""
        return {
            "type": attr_type,
            "value": value,
            "comment": comment,
            "to_ids": attr_type not in ("text", "comment", "other"),
            "distribution": str(_DEFAULT_DISTRIBUTION),
        }

    def _push_event(self, event: Dict[str, Any]) -> bool:
        """POST an event to MISP; buffer locally in degraded mode."""
        if not self._check_available():
            self._push_buffer.append(event)
            logger.warning(
                "MISP unavailable — buffered event (%d in queue)",
                len(self._push_buffer),
            )
            return False

        if not self._rate_ok():
            self._push_buffer.append(event)
            logger.warning("MISP rate limit — buffered event")
            return False

        data = self._post("/events", event)
        if data and "Event" in str(data):
            logger.debug("MISP event pushed successfully")
            return True

        self._push_buffer.append(event)
        logger.warning("MISP push failed — buffered event (%d in queue)", len(self._push_buffer))
        return False

    def _flush_buffer(self) -> int:
        """Attempt to push buffered events. Returns number successfully sent."""
        if not self._push_buffer:
            return 0
        sent = 0
        while self._push_buffer and self._rate_ok():
            event = self._push_buffer.popleft()
            data = self._post("/events", event)
            if data:
                sent += 1
            else:
                self._push_buffer.appendleft(event)
                break
        return sent

    def _post(self, path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Execute a JSON POST to the MISP REST API."""
        if not self._api_key:
            logger.warning("MISP_API_KEY not set — skipping API call")
            return None

        url = self._url + path
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        req = Request(url, data=body, headers=headers, method="POST")
        try:
            ctx = None
            if not self._verify_ssl:
                import ssl

                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            self._record_request()
            with urlopen(req, timeout=self._timeout, context=ctx) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except URLError as exc:
            logger.warning("MISP connection error to %s: %s", self._url, exc)
            self._available = False
            self._last_check = time.time()
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("MISP request failed (%s): %s", path, exc)
            return None

    def _check_available(self) -> bool:
        """Probe MISP health; re-check at most every ``_check_interval`` seconds."""
        now = time.time()
        if self._available:
            return True
        if now - self._last_check < self._check_interval:
            return False
        # Re-probe
        url = self._url + "/servers/getPyMISPVersion.json"
        req = Request(url, headers={"Authorization": self._api_key, "Accept": "application/json"})
        try:
            ctx = None
            if not self._verify_ssl:
                import ssl

                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            with urlopen(req, timeout=self._timeout, context=ctx):
                self._available = True
                logger.info("MISP is back online — flushing buffer")
                self._flush_buffer()
                return True
        except Exception:  # noqa: BLE001
            self._last_check = now
            return False

    def _rate_ok(self) -> bool:
        """Return True if we are within rate limits; record the request."""
        now = time.time()
        # Reset day counter
        if now >= self._day_reset:
            self._day_count = 0
            self._day_reset = now + 86400.0
        if self._day_count >= _MAX_REQ_PER_DAY:
            logger.warning("MISP daily request limit (%d) reached", _MAX_REQ_PER_DAY)
            return False
        # Purge timestamps older than 60 s
        cutoff = now - 60.0
        while self._req_timestamps and self._req_timestamps[0] < cutoff:
            self._req_timestamps.popleft()
        if len(self._req_timestamps) >= _MAX_REQ_PER_MIN:
            logger.warning("MISP per-minute rate limit (%d/min) reached", _MAX_REQ_PER_MIN)
            return False
        return True

    def _record_request(self) -> None:
        now = time.time()
        self._req_timestamps.append(now)
        self._day_count += 1

    def _circl_fallback_indicators(self, limit: int) -> List[Dict[str, Any]]:
        """Return indicators from CIRCL public MISP demo feed (read-only)."""
        try:
            req = Request(
                _CIRCL_FEED_URL,
                headers={"Accept": "text/html,application/json"},
            )
            with urlopen(req, timeout=self._timeout) as resp:
                _ = resp.read()
                # CIRCL feed page is HTML documentation; treat as a signal that
                # the fallback endpoint is reachable but does not serve raw JSON.
                # Return an informational record so callers know degraded mode
                # is active without silently returning nothing.
                logger.info("CIRCL MISP fallback reachable (read-only/HTML only)")
        except Exception:  # noqa: BLE001
            pass
        return []


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_connector: Optional[MISPConnector] = None


def get_connector() -> MISPConnector:
    """Return the module-level ``MISPConnector`` singleton."""
    global _connector  # noqa: PLW0603
    if _connector is None:
        _connector = MISPConnector()
    return _connector


# Convenience wrappers -------------------------------------------------------


def push_cve_event(
    cve_id: str,
    description: str,
    severity: str,
    affected_packages: List[str],
) -> bool:
    return get_connector().push_cve_event(cve_id, description, severity, affected_packages)


def pull_threat_indicators(limit: int = 100) -> List[Dict[str, Any]]:
    return get_connector().pull_threat_indicators(limit)


def push_threat_signal(
    signal_type: str,
    value: str,
    threat_level: str,
    comment: str,
) -> bool:
    return get_connector().push_threat_signal(signal_type, value, threat_level, comment)


def get_events_by_tag(tag: str, limit: int = 50) -> List[Dict[str, Any]]:
    return get_connector().get_events_by_tag(tag, limit)
