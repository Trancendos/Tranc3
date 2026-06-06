"""
Warp Radio station implementation.

Zero-cost audio streaming using Icecast (OSS, GPL) or direct HTTP streams.
Lead AI: Rocking Ricki
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class StreamStatus(str, Enum):
    LIVE = "live"
    BUFFERING = "buffering"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class StreamSource:
    id: str
    name: str
    url: str
    format: str = "mp3"          # mp3, ogg, aac
    bitrate_kbps: int = 128
    cost: str = "zero"           # Icecast self-hosted = zero cost
    active: bool = False
    listeners: int = 0


@dataclass
class WarpRadioConfig:
    icecast_url: str = "http://localhost:8000"
    icecast_admin_password: str = "hackme"
    mount_point: str = "/stream"
    max_listeners: int = 100
    default_format: str = "mp3"
    default_bitrate: int = 128


class WarpRadio:
    """
    Warp Radio controller.

    Self-hosted Icecast-based audio streaming. Zero cost.
    Planned integration: LibreTime (free scheduling) or Liquidsoap (scripted playout).
    """

    def __init__(self, config: Optional[WarpRadioConfig] = None) -> None:
        self.config = config or WarpRadioConfig()
        self._sources: dict[str, StreamSource] = {}
        self._status = StreamStatus.UNKNOWN
        self._listeners = 0

    # ------------------------------------------------------------------
    # Source management
    # ------------------------------------------------------------------

    def register_source(self, source: StreamSource) -> None:
        self._sources[source.id] = source
        logger.info("Warp Radio: registered source %s (%s)", source.id, source.url)

    def get_source(self, source_id: str) -> Optional[StreamSource]:
        return self._sources.get(source_id)

    def list_sources(self) -> list[StreamSource]:
        return list(self._sources.values())

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def health(self) -> dict:
        """Check Icecast health and current listener count."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(
                    f"{self.config.icecast_url}/status-json.xsl",
                    auth=("admin", self.config.icecast_admin_password),
                )
                if r.status_code == 200:
                    data = r.json()
                    sources = data.get("icestats", {}).get("source", [])
                    if isinstance(sources, dict):
                        sources = [sources]
                    listeners = sum(s.get("listeners", 0) for s in sources)
                    self._status = StreamStatus.LIVE
                    self._listeners = listeners
                    return {
                        "status": StreamStatus.LIVE,
                        "listeners": listeners,
                        "sources": len(sources),
                        "icecast_url": self.config.icecast_url,
                    }
        except Exception as exc:
            logger.debug("Warp Radio health check failed: %s", exc)

        self._status = StreamStatus.OFFLINE
        return {
            "status": StreamStatus.OFFLINE,
            "listeners": 0,
            "sources": 0,
            "note": "Icecast not running or not configured",
        }

    @property
    def status(self) -> StreamStatus:
        return self._status

    @property
    def listener_count(self) -> int:
        return self._listeners

    def summary(self) -> dict:
        return {
            "entity": "Warp Radio",
            "lead_ai": "Rocking Ricki",
            "status": self._status,
            "listeners": self._listeners,
            "sources": len(self._sources),
            "icecast_url": self.config.icecast_url,
            "mount_point": self.config.mount_point,
            "cost": "zero — self-hosted Icecast",
        }


# Module-level singleton — lazy init
_warp_radio: Optional[WarpRadio] = None


def get_warp_radio() -> WarpRadio:
    global _warp_radio
    if _warp_radio is None:
        _warp_radio = WarpRadio()
    return _warp_radio
