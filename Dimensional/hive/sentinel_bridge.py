"""
The HIVE ↔ Sentinel Station Bridge
====================================
Bidirectional event bridge between The HIVE (data movement and swarm
coordination) and the Sentinel Station. Data flow events published in
the HIVE are forwarded to the Sentinel Station for cross-worker
distribution, and Sentinel events on HIVE-relevant channels are routed
into the HIVE for flow monitoring and swarm awareness.

Architecture:
    HIVE Data Event ──▸ Bridge ──▸ Sentinel Station ──▸ Workers
    Sentinel Event   ──▸ Bridge ──▸ HIVE FlowMonitor ──▸ Dashboard

Three Bridges through Sentinel Station:
    Bridge 1 — InfinityBridge : User context / human traffic
    Bridge 2 — The Nexus      : AI, Agent, and Bot traffic
    Bridge 3 — The HIVE       : Data movement and swarm coordination (THIS BRIDGE)

Channel Mapping:
    The HIVE primarily listens on SentinelChannel.HIVE for data events,
    but also monitors NEXUS and BRIDGE channels for cross-bridge awareness.
    Data transfer events (replication, chunk delivery, swarm progress) are
    published on the HIVE channel for downstream consumers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from Dimensional.infinity.nomenclature import SentinelChannel
from Dimensional.hive.hive_core import Hive, HiveEvent, get_hive

logger = logging.getLogger(__name__)

# Mapping between Sentinel Station channel names and SentinelChannel enum
SENTINEL_TO_HIVE_MAP = {
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

# Channels the HIVE bridge is most interested in
HIVE_PRIMARY_CHANNELS = {
    SentinelChannel.HIVE,
    SentinelChannel.INFRASTRUCTURE,
    SentinelChannel.EVENTS,
}


class HiveSentinelBridge:
    """Bidirectional bridge between The HIVE and Sentinel Station.

    When a HiveEvent is emitted through the HIVE, the bridge forwards it
    to the Sentinel Station for cross-worker distribution. When a Sentinel
    event is published on the Sentinel Station, the bridge routes it into
    the HIVE for flow monitoring and swarm awareness.

    This bridge specifically handles data movement and swarm coordination
    (HIVE domain). AI/Agent/Bot traffic uses The Nexus. User traffic uses
    the InfinityBridge.
    """

    def __init__(self, hive: Optional[Hive] = None):
        self._hive = hive
        self._sentinel_station = None
        self._sentinel_handler_id: Optional[str] = None
        self._handler_registered: bool = False
        self._forward_to_sentinel: bool = True
        self._forward_to_hive: bool = True
        self._stats = {
            "hive_to_sentinel": 0,
            "sentinel_to_hive": 0,
            "errors": 0,
        }

    @property
    def hive(self) -> Hive:
        if self._hive is None:
            self._hive = get_hive()
        return self._hive

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    async def attach_sentinel(self, sentinel_station=None):
        """Attach the bridge to a Sentinel Station instance.

        If no station is provided, attempts to get the default singleton.
        Sets up the bridge to forward HIVE events to Sentinel and receive
        Sentinel events on HIVE-relevant channels.
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

        # Subscribe to HIVE-relevant channels on Sentinel Station
        if not self._handler_registered and self._sentinel_station is not None:
            try:
                for channel in HIVE_PRIMARY_CHANNELS:
                    await self._sentinel_station.subscribe(
                        channel.value,
                        self._on_sentinel_event,
                    )
                self._handler_registered = True
                logger.info(f"HIVE bridge subscribed to {len(HIVE_PRIMARY_CHANNELS)} Sentinel channels")
            except Exception as e:
                logger.warning(f"Could not subscribe to Sentinel channels: {e}")

        logger.info("HIVE ↔ Sentinel Bridge attached")

    async def _on_sentinel_event(self, event):
        """Handle a Sentinel Station event and forward it into the HIVE."""
        if not self._forward_to_hive:
            return

        try:
            # Extract event details from SentinelEvent
            if hasattr(event, 'channel'):
                channel = event.channel
                payload = event.payload if hasattr(event, 'payload') else {}
                event_type = event.event_type if hasattr(event, 'event_type') else ""
                source = event.source if hasattr(event, 'source') else "sentinel"
            elif isinstance(event, dict):
                channel = event.get("channel", "hive")
                payload = event.get("payload", {})
                event_type = event.get("event_type", "")
                source = event.get("source", "sentinel")
            else:
                logger.debug(f"Unknown event type from Sentinel: {type(event)}")
                return

            # Emit into the HIVE
            await self.hive.emit_event(
                channel=channel,
                source=source,
                event_type=f"sentinel:{event_type}" if event_type else "sentinel_forward",
                payload=payload,
            )
            self._stats["sentinel_to_hive"] += 1
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"Failed to forward Sentinel→HIVE: {e}")

    async def on_hive_event(self, event: HiveEvent):
        """Handle a HIVE event and forward it to the Sentinel Station."""
        if not self._forward_to_sentinel or self._sentinel_station is None:
            return

        try:
            channel_name = str(event.channel).lower()

            # Map to Sentinel-compatible channel name
            sentinel_channel = channel_name
            if sentinel_channel not in SENTINEL_TO_HIVE_MAP:
                # Try to find matching channel
                for k, v in SENTINEL_TO_HIVE_MAP.items():
                    if v.value.lower() == channel_name:
                        sentinel_channel = k
                        break

            await self._sentinel_station.publish(
                channel=sentinel_channel,
                payload=event.payload or {},
                event_type=event.event_type,
                source=f"hive:{event.source}",
            )
            self._stats["hive_to_sentinel"] += 1
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"Failed to forward HIVE→Sentinel: {e}")

    async def on_sentinel_event_raw(
        self,
        channel: str,
        payload: Dict[str, Any],
        event_type: str = "",
        source: str = "",
    ):
        """Handle a raw Sentinel Station event and forward it into the HIVE.

        This method should be called by the Sentinel Station's handler
        mechanism when an event is published on a HIVE-relevant channel.
        """
        if not self._forward_to_hive:
            return

        try:
            # Map to HIVE SentinelChannel
            hive_channel = SENTINEL_TO_HIVE_MAP.get(
                channel.lower(), SentinelChannel.HIVE
            )

            await self.hive.emit_event(
                channel=hive_channel.value,
                source=source or "sentinel",
                event_type=event_type or "sentinel_forward",
                payload=payload,
            )
            self._stats["sentinel_to_hive"] += 1
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"Failed to forward Sentinel→HIVE: {e}")

    def pause_sentinel_forward(self):
        """Stop forwarding HIVE events to Sentinel Station."""
        self._forward_to_sentinel = False
        logger.info("HIVE→Sentinel forwarding paused")

    def resume_sentinel_forward(self):
        """Resume forwarding HIVE events to Sentinel Station."""
        self._forward_to_sentinel = True
        logger.info("HIVE→Sentinel forwarding resumed")

    def pause_hive_forward(self):
        """Stop forwarding Sentinel events to HIVE."""
        self._forward_to_hive = False
        logger.info("Sentinel→HIVE forwarding paused")

    def resume_hive_forward(self):
        """Resume forwarding Sentinel events to HIVE."""
        self._forward_to_hive = True
        logger.info("Sentinel→HIVE forwarding resumed")

    async def get_status(self) -> Dict[str, Any]:
        """Get the current bridge status."""
        return {
            "bridge": "HiveSentinelBridge",
            "description": "Bidirectional bridge for data movement between HIVE and Sentinel",
            "sentinel_attached": self._sentinel_station is not None,
            "handler_registered": self._handler_registered,
            "forward_to_sentinel": self._forward_to_sentinel,
            "forward_to_hive": self._forward_to_hive,
            "stats": dict(self._stats),
            "primary_channels": [ch.value for ch in HIVE_PRIMARY_CHANNELS],
            "channel_map": {k: v.value for k, v in SENTINEL_TO_HIVE_MAP.items()},
        }


# Module-level singleton
_bridge_instance: Optional[HiveSentinelBridge] = None


def get_bridge(hive: Optional[Hive] = None) -> HiveSentinelBridge:
    """Get or create the HIVE-Sentinel Bridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = HiveSentinelBridge(hive)
    return _bridge_instance
