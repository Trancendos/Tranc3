"""
Dimensional Nexus ↔ Sentinel Station Bridge
=============================================
Bidirectional event bridge between the Dimensional Nexus and the
Sentinel Station. Events published to the Nexus are forwarded to
the Sentinel Station and vice versa, ensuring unified event flow
across the entire platform.

Architecture:
    Sentinel Event ──▸ Bridge ──▸ Nexus EventRouter ──▸ Dashboard
    Nexus Event     ──▸ Bridge ──▸ Sentinel Station  ──▸ Workers

Channel Mapping:
    Sentinel channels (lowercase) map directly to SentinelChannel enum
    values used by the Nexus EventRouter (uppercase).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from Dimensional.infinity.nomenclature import SentinelChannel
from Dimensional.nexus.nexus_core import DimensionalNexus, NexusEvent, get_nexus

logger = logging.getLogger(__name__)

# Mapping between Sentinel Station channel names and SentinelChannel enum
SENTINEL_TO_NEXUS_MAP = {
    "platform": SentinelChannel.PLATFORM,
    "agents": SentinelChannel.AGENTS,
    "models": SentinelChannel.MODELS,
    "workflows": SentinelChannel.WORKFLOWS,
    "security": SentinelChannel.SECURITY,
    "hive": SentinelChannel.HIVE,
    "nexus": SentinelChannel.NEXUS,
    "bridge": SentinelChannel.BRIDGE,
    "pillars": SentinelChannel.PILLARS,
    "infrastructure": SentinelChannel.INFRASTRUCTURE,
    "events": SentinelChannel.EVENTS,
}


class NexusSentinelBridge:
    """Bidirectional bridge between Dimensional Nexus and Sentinel Station.

    When a NexusEvent is emitted through the Nexus, the bridge forwards it
    to the Sentinel Station for cross-worker distribution. When a Sentinel
    event is published on the Sentinel Station, the bridge routes it into
    the Nexus for dashboard visualization and causal tracking.
    """

    def __init__(self, nexus: Optional[DimensionalNexus] = None):
        self._nexus = nexus
        self._sentinel_station = None
        self._sentinel_handler_id: Optional[str] = None
        self._nexus_handler_registered: bool = False
        self._forward_to_sentinel: bool = True
        self._forward_to_nexus: bool = True
        self._stats = {
            "nexus_to_sentinel": 0,
            "sentinel_to_nexus": 0,
            "errors": 0,
        }

    @property
    def nexus(self) -> DimensionalNexus:
        if self._nexus is None:
            self._nexus = get_nexus()
        return self._nexus

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    async def attach_sentinel(self, sentinel_station=None):
        """Attach the bridge to a Sentinel Station instance.

        If no station is provided, attempts to get the default singleton.
        Registers a handler on the Sentinel Station that forwards events
        into the Nexus.
        """
        if sentinel_station is not None:
            self._sentinel_station = sentinel_station
        else:
            try:
                from Dimensional.infinity.sentinel_station import get_sentinel_station
                self._sentinel_station = get_sentinel_station()
            except Exception as e:
                logger.warning(f"Could not get Sentinel Station: {e}")
                return

        # Register a Nexus handler that forwards events to Sentinel
        if not self._nexus_handler_registered:
            for channel in SentinelChannel:
                try:
                    await self.nexus.event_router.register_handler(
                        channel.value, self._on_nexus_event
                    )
                except Exception as e:
                    logger.debug(f"Handler registration for {channel.value}: {e}")
            self._nexus_handler_registered = True

        logger.info("Nexus ↔ Sentinel Bridge attached")

    async def _on_nexus_event(self, event: NexusEvent):
        """Handle a Nexus event and forward it to the Sentinel Station."""
        if not self._forward_to_sentinel or self._sentinel_station is None:
            return

        try:
            channel_name = (
                event.channel.value
                if isinstance(event.channel, SentinelChannel)
                else str(event.channel)
            ).lower()

            # Convert to Sentinel-compatible channel name
            sentinel_channel = channel_name
            if sentinel_channel not in SENTINEL_TO_NEXUS_MAP:
                # Try uppercase match
                for k, v in SENTINEL_TO_NEXUS_MAP.items():
                    if v.value.lower() == channel_name:
                        sentinel_channel = k
                        break

            await self._sentinel_station.publish(
                channel=sentinel_channel,
                payload=event.payload or {},
                event_type=event.event_type,
                source=f"nexus:{event.source_dimension}",
            )
            self._stats["nexus_to_sentinel"] += 1
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"Failed to forward Nexus→Sentinel: {e}")

    async def on_sentinel_event(self, channel: str, payload: Dict[str, Any],
                                 event_type: str = "", source: str = ""):
        """Handle a Sentinel Station event and forward it into the Nexus.

        This method should be called by the Sentinel Station's handler
        mechanism when an event is published.
        """
        if not self._forward_to_nexus:
            return

        try:
            # Map to Nexus SentinelChannel
            nexus_channel = SENTINEL_TO_NEXUS_MAP.get(
                channel.lower(), SentinelChannel.EVENTS
            )

            # Determine tier from source
            source_tier = 5  # Default to BOT tier
            source_dim = source or "sentinel"
            if ":" in source_dim:
                parts = source_dim.split(":", 1)
                source_dim = parts[1] if len(parts) > 1 else parts[0]

            await self.nexus.emit_event(
                channel=nexus_channel.value,
                source_dimension=source_dim,
                source_tier=source_tier,
                event_type=event_type or "sentinel_forward",
                payload=payload,
            )
            self._stats["sentinel_to_nexus"] += 1
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"Failed to forward Sentinel→Nexus: {e}")

    def pause_sentinel_forward(self):
        """Stop forwarding Nexus events to Sentinel Station."""
        self._forward_to_sentinel = False
        logger.info("Nexus→Sentinel forwarding paused")

    def resume_sentinel_forward(self):
        """Resume forwarding Nexus events to Sentinel Station."""
        self._forward_to_sentinel = True
        logger.info("Nexus→Sentinel forwarding resumed")

    def pause_nexus_forward(self):
        """Stop forwarding Sentinel events to Nexus."""
        self._forward_to_nexus = False
        logger.info("Sentinel→Nexus forwarding paused")

    def resume_nexus_forward(self):
        """Resume forwarding Sentinel events to Nexus."""
        self._forward_to_nexus = True
        logger.info("Sentinel→Nexus forwarding resumed")

    async def get_status(self) -> Dict[str, Any]:
        """Get the current bridge status."""
        return {
            "bridge": "NexusSentinelBridge",
            "sentinel_attached": self._sentinel_station is not None,
            "nexus_handler_registered": self._nexus_handler_registered,
            "forward_to_sentinel": self._forward_to_sentinel,
            "forward_to_nexus": self._forward_to_nexus,
            "stats": dict(self._stats),
            "channel_map": {k: v.value for k, v in SENTINEL_TO_NEXUS_MAP.items()},
        }


# Module-level singleton
_bridge_instance: Optional[NexusSentinelBridge] = None


def get_bridge(nexus: Optional[DimensionalNexus] = None) -> NexusSentinelBridge:
    """Get or create the Nexus-Sentinel Bridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = NexusSentinelBridge(nexus)
    return _bridge_instance
