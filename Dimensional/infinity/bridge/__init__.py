"""
Tranc3 InfinityBridge — User Context & Human Traffic Coordinator
================================================================
The InfinityBridge is the "Light Bridge" of the three-bridge architecture
through Sentinel Station. It manages user context propagation, session
lifecycle, location transitions, and presence tracking — all for HUMAN
traffic only.

Three Bridges through Sentinel Station:
    Bridge 1 — InfinityBridge : User context / human traffic (THIS PACKAGE)
    Bridge 2 — The Nexus      : AI, Agent, and Bot traffic
    Bridge 3 — The HIVE       : Data movement and swarm coordination

Critical Distinction:
    - InfinityBridge = User/human traffic and context ONLY
    - Nexus = AI, Agent, Bot movement and traffic ONLY
    - HIVE = Data movement and swarm systems ONLY

Usage:
    from Dimensional.infinity.bridge import InfinityBridge, get_infinity_bridge

    bridge = get_infinity_bridge()

    # Connect a user
    ctx = bridge.connect_user("user-123", location="infinity_portal")

    # Transition a user
    bridge.transition_user("user-123", target_location="infinity_gate")

    # Get users at a location
    users = bridge.get_users_at_location("infinity_gate")

    # Disconnect
    bridge.disconnect_user("user-123")
"""

from Dimensional.infinity.bridge.bridge_core import (
    BridgeEvent,
    BridgePath,
    BridgePathManager,
    ContextType,
    ContextWindow,
    InfinityBridge,
    InfinityBridgeEvent,
    InfinitySentinelBridge,
    PresenceTracker,
    SessionStatus,
    UserContext,
    UserTier,
    get_infinity_bridge,
    get_sentinel_bridge,
)

__all__ = [
    # Core bridge
    "InfinityBridge",
    "get_infinity_bridge",
    # Sentinel bridge
    "InfinitySentinelBridge",
    "get_sentinel_bridge",
    # Data models
    "UserContext",
    "InfinityBridgeEvent",
    "BridgePath",
    # Subsystems
    "ContextWindow",
    "PresenceTracker",
    "BridgePathManager",
    # Enums
    "UserTier",
    "SessionStatus",
    "ContextType",
    "BridgeEvent",
]
