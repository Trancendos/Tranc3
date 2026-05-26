"""
The InfinityBridge — User Context & Human Traffic Coordinator
=============================================================
The InfinityBridge manages user context propagation and human traffic
movement across the Tranc3 platform. It is the "Light Bridge" of the
three-bridge architecture, handling real-time user sessions, context
windows, location transitions, and presence information.

Three Bridges through Sentinel Station:
    Bridge 1 — InfinityBridge : User context / human traffic (THIS BRIDGE)
    Bridge 2 — The Nexus      : AI, Agent, and Bot traffic
    Bridge 3 — The HIVE       : Data movement and swarm coordination

Critical Distinction:
    - InfinityBridge = User/human traffic and context ONLY
    - Nexus = AI, Agent, Bot movement and traffic ONLY
    - HIVE = Data movement and swarm systems ONLY

Architecture:
    User Session ──▸ InfinityBridge ──▸ Sentinel Station ──▸ Workers
    Location Event ──▸ InfinityBridge ──▸ Context Window ──▸ Dashboard

The InfinityBridge connects the named locations in the Infinity Ecosystem
(Admin, Arcadia, The Citadel, Portal, Gate, etc.) and manages the flow
of users between them, carrying their context, permissions, and session
state along the way.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from Dimensional.infinity.nomenclature import (
    InfinityLocation,
    SentinelChannel,
    TransferSystem,
)

logger = logging.getLogger(__name__)


# ── Enums ──────────────────────────────────────────────────────────────────────

class UserTier(int, Enum):
    """User privilege tiers within the InfinityBridge.

    Maps to the platform tier system for access control:
        0 = HUMAN (override authority)
        1 = ORCHESTRATOR (system-level)
        2+ = service tiers below
    """
    HUMAN = 0
    ORCHESTRATOR = 1
    PRIME = 2


class SessionStatus(str, Enum):
    """Status of a user session on the InfinityBridge."""
    CONNECTING = "connecting"
    ACTIVE = "active"
    IDLE = "idle"
    TRANSITIONING = "transitioning"
    DISCONNECTED = "disconnected"


class ContextType(str, Enum):
    """Types of user context propagated through the InfinityBridge."""
    SESSION = "session"
    NAVIGATION = "navigation"
    PRESENCE = "presence"
    PERMISSION = "permission"
    PREFERENCE = "preference"
    WORKSPACE = "workspace"


class BridgeEvent(str, Enum):
    """Events specific to InfinityBridge traffic."""
    USER_CONNECT = "user_connect"
    USER_DISCONNECT = "user_disconnect"
    USER_TRANSITION = "user_transition"
    CONTEXT_UPDATE = "context_update"
    PRESENCE_UPDATE = "presence_update"
    SESSION_RESUME = "session_resume"
    SESSION_PAUSE = "session_pause"
    LOCATION_CHANGE = "location_change"
    BRIDGE_OPEN = "bridge_open"
    BRIDGE_CLOSE = "bridge_close"


# ── Data Models ────────────────────────────────────────────────────────────────

@dataclass
class UserContext:
    """A user's context window carried through the InfinityBridge.

    Contains all the information about a user's current state that
    needs to travel with them as they move through the platform.
    """
    user_id: str
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    location: str = InfinityLocation.PORTAL.value
    previous_location: str = ""
    tier: int = UserTier.HUMAN
    status: SessionStatus = SessionStatus.ACTIVE
    context_types: List[str] = field(default_factory=lambda: [ContextType.SESSION.value])
    metadata: Dict[str, Any] = field(default_factory=dict)
    connected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def touch(self):
        """Update last_active timestamp."""
        self.last_active = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "location": self.location,
            "previous_location": self.previous_location,
            "tier": self.tier,
            "status": self.status.value if isinstance(self.status, SessionStatus) else self.status,
            "context_types": self.context_types,
            "metadata": self.metadata,
            "connected_at": self.connected_at,
            "last_active": self.last_active,
        }


@dataclass
class InfinityBridgeEvent:
    """An event on the InfinityBridge.

    Represents user traffic flowing through the Light Bridge —
    connect, disconnect, transition, and context propagation events.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    event_type: str = BridgeEvent.CONTEXT_UPDATE.value
    user_id: str = ""
    session_id: str = ""
    source_location: str = ""
    target_location: str = ""
    channel: str = SentinelChannel.BRIDGE.value
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "source_location": self.source_location,
            "target_location": self.target_location,
            "channel": self.channel,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


@dataclass
class BridgePath:
    """A path between two Infinity locations through the InfinityBridge.

    Light bridges connect named locations in the Infinity Ecosystem.
    Each path has a status (open/closed) and tracks the number of
    active users traversing it.
    """
    source: str
    target: str
    is_open: bool = True
    active_users: int = 0
    total_transitions: int = 0
    avg_transition_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def path_id(self) -> str:
        return f"{self.source}→{self.target}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "source": self.source,
            "target": self.target,
            "is_open": self.is_open,
            "active_users": self.active_users,
            "total_transitions": self.total_transitions,
            "avg_transition_ms": round(self.avg_transition_ms, 2),
            "created_at": self.created_at,
        }


# ── Context Manager ────────────────────────────────────────────────────────────

class ContextWindow:
    """Manages user context windows and their lifecycle.

    Each user on the platform has a context window that travels with
    them through the InfinityBridge. This manager tracks all active
    contexts and provides lookup/update operations.
    """

    def __init__(self, db_path: str = ":memory:"):
        self._db_path = db_path
        self._contexts: Dict[str, UserContext] = {}
        self._sessions: Dict[str, str] = {}  # session_id -> user_id
        self._location_index: Dict[str, Set[str]] = {}  # location -> set of user_ids
        self._init_db()

    def _init_db(self):
        """Initialize SQLite for persistent context storage."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_contexts (
                user_id TEXT PRIMARY KEY,
                session_id TEXT,
                location TEXT,
                previous_location TEXT,
                tier INTEGER,
                status TEXT,
                context_types TEXT,
                metadata TEXT,
                connected_at TEXT,
                last_active TEXT
            )
        """)
        self._conn.commit()

    def register(self, context: UserContext) -> UserContext:
        """Register a new user context."""
        self._contexts[context.user_id] = context
        self._sessions[context.session_id] = context.user_id
        loc = context.location
        if loc not in self._location_index:
            self._location_index[loc] = set()
        self._location_index[loc].add(context.user_id)
        # Persist
        self._conn.execute(
            "INSERT OR REPLACE INTO user_contexts VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                context.user_id, context.session_id, context.location,
                context.previous_location, context.tier,
                context.status.value if isinstance(context.status, SessionStatus) else context.status,
                ",".join(context.context_types),
                str(context.metadata), context.connected_at, context.last_active,
            ),
        )
        self._conn.commit()
        return context

    def get(self, user_id: str) -> Optional[UserContext]:
        """Get a user's context by user_id."""
        return self._contexts.get(user_id)

    def get_by_session(self, session_id: str) -> Optional[UserContext]:
        """Get a user's context by session_id."""
        user_id = self._sessions.get(session_id)
        if user_id:
            return self._contexts.get(user_id)
        return None

    def update_location(self, user_id: str, new_location: str) -> Optional[UserContext]:
        """Update a user's location and return the updated context."""
        ctx = self._contexts.get(user_id)
        if ctx is None:
            return None
        # Remove from old location index
        old_loc = ctx.location
        if old_loc in self._location_index:
            self._location_index[old_loc].discard(user_id)
        # Update
        ctx.previous_location = old_loc
        ctx.location = new_location
        ctx.touch()
        # Add to new location index
        if new_location not in self._location_index:
            self._location_index[new_location] = set()
        self._location_index[new_location].add(user_id)
        return ctx

    def update_status(self, user_id: str, status: SessionStatus) -> Optional[UserContext]:
        """Update a user's session status."""
        ctx = self._contexts.get(user_id)
        if ctx is None:
            return None
        ctx.status = status
        ctx.touch()
        return ctx

    def remove(self, user_id: str) -> Optional[UserContext]:
        """Remove a user context."""
        ctx = self._contexts.pop(user_id, None)
        if ctx:
            self._sessions.pop(ctx.session_id, None)
            loc = ctx.location
            if loc in self._location_index:
                self._location_index[loc].discard(user_id)
        return ctx

    def get_users_at(self, location: str) -> List[UserContext]:
        """Get all user contexts at a specific location."""
        user_ids = self._location_index.get(location, set())
        return [self._contexts[uid] for uid in user_ids if uid in self._contexts]

    def get_all(self) -> List[UserContext]:
        """Get all registered user contexts."""
        return list(self._contexts.values())

    def get_location_counts(self) -> Dict[str, int]:
        """Get the count of users at each location."""
        return {loc: len(users) for loc, users in self._location_index.items()}

    @property
    def total_users(self) -> int:
        return len(self._contexts)

    @property
    def active_users(self) -> int:
        return sum(
            1 for ctx in self._contexts.values()
            if ctx.status in (SessionStatus.ACTIVE, SessionStatus.TRANSITIONING)
        )


# ── Presence Tracker ───────────────────────────────────────────────────────────

class PresenceTracker:
    """Tracks user presence across Infinity locations.

    Maintains a real-time presence map showing which users are at
    which locations, with idle detection and presence notifications.
    """

    def __init__(self, idle_timeout_seconds: int = 300):
        self._idle_timeout = idle_timeout_seconds
        self._presence: Dict[str, Dict[str, Any]] = {}  # user_id -> presence info

    def update_presence(self, user_id: str, location: str, status: str = "active"):
        """Update a user's presence."""
        self._presence[user_id] = {
            "location": location,
            "status": status,
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "timestamp": time.time(),
        }

    def get_presence(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user's presence information."""
        pres = self._presence.get(user_id)
        if pres is None:
            return None
        # Check if idle
        elapsed = time.time() - pres.get("timestamp", 0)
        if elapsed > self._idle_timeout and pres["status"] == "active":
            pres["status"] = "idle"
        return pres

    def remove_presence(self, user_id: str):
        """Remove a user's presence."""
        self._presence.pop(user_id, None)

    def get_location_presence(self, location: str) -> List[Dict[str, Any]]:
        """Get all presence entries for a location."""
        result = []
        for user_id, pres in self._presence.items():
            if pres.get("location") == location:
                entry = dict(pres)
                entry["user_id"] = user_id
                result.append(entry)
        return result

    def get_idle_users(self) -> List[str]:
        """Get user_ids that have been idle past the timeout."""
        now = time.time()
        return [
            uid for uid, pres in self._presence.items()
            if now - pres.get("timestamp", 0) > self._idle_timeout
        ]

    @property
    def total_online(self) -> int:
        return len(self._presence)

    def get_stats(self) -> Dict[str, Any]:
        """Get presence statistics."""
        location_counts: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        for pres in self._presence.values():
            loc = pres.get("location", "unknown")
            location_counts[loc] = location_counts.get(loc, 0) + 1
            status = pres.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        return {
            "total_online": self.total_online,
            "location_counts": location_counts,
            "status_counts": status_counts,
            "idle_timeout_seconds": self._idle_timeout,
        }


# ── Bridge Path Manager ────────────────────────────────────────────────────────

class BridgePathManager:
    """Manages the Light Bridge paths between Infinity locations.

    Each path represents a connection between two locations through
    which users can travel. Paths can be opened or closed, and
    track the volume of user transitions.
    """

    def __init__(self):
        self._paths: Dict[str, BridgePath] = {}

    def open_path(self, source: str, target: str) -> BridgePath:
        """Open a bridge path between two locations."""
        path_id = f"{source}→{target}"
        if path_id in self._paths:
            path = self._paths[path_id]
            path.is_open = True
            return path
        path = BridgePath(source=source, target=target, is_open=True)
        self._paths[path_id] = path
        return path

    def close_path(self, source: str, target: str) -> Optional[BridgePath]:
        """Close a bridge path."""
        path_id = f"{source}→{target}"
        path = self._paths.get(path_id)
        if path:
            path.is_open = False
        return path

    def get_path(self, source: str, target: str) -> Optional[BridgePath]:
        """Get a specific bridge path."""
        return self._paths.get(f"{source}→{target}")

    def record_transition(self, source: str, target: str, transition_ms: float = 0.0):
        """Record a user transition across a bridge path."""
        path_id = f"{source}→{target}"
        path = self._paths.get(path_id)
        if path is None:
            path = self.open_path(source, target)
        path.total_transitions += 1
        # Running average
        if path.avg_transition_ms == 0:
            path.avg_transition_ms = transition_ms
        else:
            path.avg_transition_ms = (
                (path.avg_transition_ms * (path.total_transitions - 1) + transition_ms)
                / path.total_transitions
            )

    def get_open_paths(self) -> List[BridgePath]:
        """Get all open bridge paths."""
        return [p for p in self._paths.values() if p.is_open]

    def get_all_paths(self) -> List[BridgePath]:
        """Get all bridge paths (open and closed)."""
        return list(self._paths.values())

    def get_paths_from(self, location: str) -> List[BridgePath]:
        """Get all paths originating from a location."""
        return [p for p in self._paths.values() if p.source == location]

    def get_paths_to(self, location: str) -> List[BridgePath]:
        """Get all paths leading to a location."""
        return [p for p in self._paths.values() if p.target == location]

    @property
    def total_paths(self) -> int:
        return len(self._paths)

    @property
    def open_path_count(self) -> int:
        return sum(1 for p in self._paths.values() if p.is_open)


# ── InfinityBridge Core ────────────────────────────────────────────────────────

class InfinityBridge:
    """The InfinityBridge — User Context & Human Traffic Coordinator.

    The InfinityBridge (Light Bridge) manages the flow of users across
    the Tranc3 platform. It handles session lifecycle, location transitions,
    context propagation, and presence tracking — all for HUMAN traffic only.

    AI/Agent/Bot traffic uses The Nexus. Data movement uses The HIVE.

    Architecture:
        Users connect → InfinityBridge manages their context
        Users transition → Light Bridge paths carry them between locations
        Users disconnect → Context is preserved for session resume

    Subsystems:
        ContextWindow     — User context registration and lookup
        PresenceTracker   — Real-time presence across locations
        BridgePathManager — Light Bridge path management
    """

    def __init__(self, db_path: str = ":memory:"):
        self._context_window = ContextWindow(db_path)
        self._presence = PresenceTracker()
        self._paths = BridgePathManager()
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._stats = {
            "total_connections": 0,
            "total_disconnections": 0,
            "total_transitions": 0,
            "total_context_updates": 0,
            "events_emitted": 0,
        }
        self._started_at: Optional[str] = None

    @property
    def stats(self) -> Dict[str, int]:
        """Public accessor for bridge statistics."""
        return dict(self._stats)

    @property
    def context_window(self) -> ContextWindow:
        return self._context_window

    @property
    def presence(self) -> PresenceTracker:
        return self._presence

    @property
    def paths(self) -> BridgePathManager:
        return self._paths

    # ── Session Lifecycle ──────────────────────────────────────────────────

    def connect_user(
        self,
        user_id: str,
        location: str = InfinityLocation.PORTAL.value,
        tier: int = UserTier.HUMAN,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UserContext:
        """Connect a user to the InfinityBridge.

        Creates a new user context with an active session at the
        specified location. Emits a user_connect event.
        """
        ctx = UserContext(
            user_id=user_id,
            location=location,
            tier=tier,
            status=SessionStatus.ACTIVE,
            metadata=metadata or {},
        )
        self._context_window.register(ctx)
        self._presence.update_presence(user_id, location, "active")
        self._stats["total_connections"] += 1

        event = InfinityBridgeEvent(
            event_type=BridgeEvent.USER_CONNECT.value,
            user_id=user_id,
            session_id=ctx.session_id,
            source_location=location,
            target_location=location,
            payload={"tier": tier, "metadata": metadata or {}},
        )
        self._emit_event(event)
        return ctx

    def disconnect_user(self, user_id: str) -> Optional[UserContext]:
        """Disconnect a user from the InfinityBridge.

        Removes the user's context and presence. Emits a
        user_disconnect event.
        """
        ctx = self._context_window.get(user_id)
        if ctx is None:
            return None

        event = InfinityBridgeEvent(
            event_type=BridgeEvent.USER_DISCONNECT.value,
            user_id=user_id,
            session_id=ctx.session_id,
            source_location=ctx.location,
            payload={"last_location": ctx.location},
        )
        self._emit_event(event)

        self._context_window.remove(user_id)
        self._presence.remove_presence(user_id)
        self._stats["total_disconnections"] += 1
        return ctx

    # ── Location Transitions ───────────────────────────────────────────────

    def transition_user(
        self,
        user_id: str,
        target_location: str,
        transition_ms: float = 0.0,
    ) -> Optional[UserContext]:
        """Transition a user to a new Infinity location.

        Moves the user's context to the target location through
        the Light Bridge path. Emits a user_transition event.
        """
        ctx = self._context_window.get(user_id)
        if ctx is None:
            return None

        source = ctx.location
        ctx = self._context_window.update_location(user_id, target_location)
        if ctx is None:
            return None

        ctx.status = SessionStatus.ACTIVE
        self._presence.update_presence(user_id, target_location, "active")
        self._paths.record_transition(source, target_location, transition_ms)
        self._stats["total_transitions"] += 1

        event = InfinityBridgeEvent(
            event_type=BridgeEvent.USER_TRANSITION.value,
            user_id=user_id,
            session_id=ctx.session_id,
            source_location=source,
            target_location=target_location,
            payload={"transition_ms": transition_ms},
        )
        self._emit_event(event)
        return ctx

    # ── Context Propagation ────────────────────────────────────────────────

    def update_context(
        self,
        user_id: str,
        context_type: str = ContextType.SESSION.value,
        updates: Optional[Dict[str, Any]] = None,
    ) -> Optional[UserContext]:
        """Update a user's context with new information.

        Propagates context changes through the InfinityBridge for
        other services to react to. Emits a context_update event.
        """
        ctx = self._context_window.get(user_id)
        if ctx is None:
            return None

        if context_type not in ctx.context_types:
            ctx.context_types.append(context_type)
        if updates:
            ctx.metadata.update(updates)
        ctx.touch()
        self._stats["total_context_updates"] += 1

        event = InfinityBridgeEvent(
            event_type=BridgeEvent.CONTEXT_UPDATE.value,
            user_id=user_id,
            session_id=ctx.session_id,
            source_location=ctx.location,
            payload={"context_type": context_type, "updates": updates or {}},
        )
        self._emit_event(event)
        return ctx

    # ── Presence ───────────────────────────────────────────────────────────

    def update_presence(self, user_id: str, status: str = "active") -> bool:
        """Update a user's presence status."""
        ctx = self._context_window.get(user_id)
        if ctx is None:
            return False
        self._presence.update_presence(user_id, ctx.location, status)
        ctx.touch()

        event = InfinityBridgeEvent(
            event_type=BridgeEvent.PRESENCE_UPDATE.value,
            user_id=user_id,
            session_id=ctx.session_id,
            source_location=ctx.location,
            payload={"presence_status": status},
        )
        self._emit_event(event)
        return True

    def get_users_at_location(self, location: str) -> List[UserContext]:
        """Get all users at a specific Infinity location."""
        return self._context_window.get_users_at(location)

    # ── Event System ───────────────────────────────────────────────────────

    def register_handler(self, event_type: str, handler: Callable):
        """Register an event handler for a specific event type."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def _emit_event(self, event: InfinityBridgeEvent):
        """Emit an event to all registered handlers."""
        self._stats["events_emitted"] += 1
        handlers = self._event_handlers.get(event.event_type, [])
        handlers += self._event_handlers.get("*", [])  # Wildcard
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.debug(f"Event handler error: {e}")

    # ── Bridge Path Management ─────────────────────────────────────────────

    def open_bridge(self, source: str, target: str) -> BridgePath:
        """Open a Light Bridge path between two locations."""
        path = self._paths.open_path(source, target)

        event = InfinityBridgeEvent(
            event_type=BridgeEvent.BRIDGE_OPEN.value,
            source_location=source,
            target_location=target,
            payload={"path_id": path.path_id},
        )
        self._emit_event(event)
        return path

    def close_bridge(self, source: str, target: str) -> Optional[BridgePath]:
        """Close a Light Bridge path between two locations."""
        path = self._paths.close_path(source, target)
        if path:
            event = InfinityBridgeEvent(
                event_type=BridgeEvent.BRIDGE_CLOSE.value,
                source_location=source,
                target_location=target,
                payload={"path_id": path.path_id},
            )
            self._emit_event(event)
        return path

    # ── Status & Health ────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get the current InfinityBridge status.

        Includes the three_bridges dict identifying this bridge's
        role in the three-bridge architecture.
        """
        return {
            "bridge": "InfinityBridge",
            "bridge_type": "infinity",
            "description": "User Context & Human Traffic Coordinator (Light Bridge)",
            "status": "active",
            "started_at": self._started_at,
            "stats": dict(self._stats),
            "users": {
                "total": self._context_window.total_users,
                "active": self._context_window.active_users,
            },
            "presence": self._presence.get_stats(),
            "paths": {
                "total": self._paths.total_paths,
                "open": self._paths.open_path_count,
            },
            "location_counts": self._context_window.get_location_counts(),
            "three_bridges": {
                "infinity_bridge": {
                    "name": "InfinityBridge",
                    "role": "User Context & Human Traffic",
                    "description": "User Context & Human Traffic (Light Bridge)",
                    "status": "active",
                    "bridge_type": "infinity",
                },
                "nexus": {
                    "name": "The Nexus",
                    "role": "AI, Agent, and Bot Traffic",
                    "description": "AI, Agent, and Bot Traffic Coordination",
                    "status": "see_nexus_status",
                    "bridge_type": "nexus",
                },
                "hive": {
                    "name": "The HIVE",
                    "role": "Data Movement & Swarm Coordination",
                    "description": "Data Movement & Swarm System Coordination",
                    "status": "see_hive_status",
                    "bridge_type": "hive",
                },
            },
        }

    def get_health(self) -> Dict[str, Any]:
        """Get the InfinityBridge health summary."""
        total = self._context_window.total_users
        active = self._context_window.active_users
        return {
            "bridge": "InfinityBridge",
            "healthy": True,
            "users": {
                "total": total,
                "active": active,
                "idle": total - active,
            },
            "open_paths": self._paths.open_path_count,
            "total_paths": self._paths.total_paths,
            "stats": dict(self._stats),
        }

    def start(self):
        """Start the InfinityBridge."""
        self._started_at = datetime.now(timezone.utc).isoformat()
        logger.info("InfinityBridge started — Light Bridge active")

    def stop(self):
        """Stop the InfinityBridge."""
        logger.info(
            f"InfinityBridge stopped — {self._context_window.total_users} users disconnected"
        )


# ── Sentinel Bridge ────────────────────────────────────────────────────────────

class InfinitySentinelBridge:
    """Bidirectional bridge between the InfinityBridge and Sentinel Station.

    When a user event occurs on the InfinityBridge, the bridge forwards
    it to the Sentinel Station for cross-worker distribution. When a
    Sentinel event is published on BRIDGE-relevant channels, the bridge
    routes it into the InfinityBridge for context awareness.

    This bridge specifically handles user/human traffic (InfinityBridge domain).
    AI/Agent/Bot traffic uses The Nexus. Data traffic uses The HIVE.
    """

    # Channels the InfinityBridge primarily listens on
    INFINITY_PRIMARY_CHANNELS = {
        SentinelChannel.BRIDGE,
        SentinelChannel.PLATFORM,
        SentinelChannel.EVENTS,
    }

    def __init__(self, infinity_bridge: Optional[InfinityBridge] = None):
        self._bridge = infinity_bridge
        self._sentinel_station = None
        self._handler_registered: bool = False
        self._forward_to_sentinel: bool = True
        self._forward_to_bridge: bool = True
        self._stats = {
            "bridge_to_sentinel": 0,
            "sentinel_to_bridge": 0,
            "errors": 0,
        }

    @property
    def bridge(self) -> InfinityBridge:
        if self._bridge is None:
            self._bridge = get_infinity_bridge()
        return self._bridge

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    async def attach_sentinel(self, sentinel_station=None):
        """Attach the bridge to a Sentinel Station instance."""
        if sentinel_station is not None:
            self._sentinel_station = sentinel_station
        else:
            try:
                from Dimensional.infinity.sentinel_station import get_sentinel_station
                self._sentinel_station = get_sentinel_station()
            except Exception as e:
                logger.warning(f"Could not get Sentinel Station: {e}")
                return

        # Register a handler on the InfinityBridge that forwards to Sentinel
        if not self._handler_registered:
            self._bridge.register_handler("*", self._on_bridge_event)
            self._handler_registered = True

        logger.info("InfinityBridge ↔ Sentinel Bridge attached")

    def _on_bridge_event(self, event: InfinityBridgeEvent):
        """Handle an InfinityBridge event and forward to Sentinel Station."""
        if not self._forward_to_sentinel or self._sentinel_station is None:
            return

        try:
            # Schedule the async publish
            asyncio.get_event_loop().create_task(
                self._sentinel_station.publish(
                    channel=SentinelChannel.BRIDGE.value,
                    payload=event.to_dict(),
                    event_type=event.event_type,
                    source=f"infinity_bridge:{event.user_id}",
                )
            )
            self._stats["bridge_to_sentinel"] += 1
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"Failed to forward InfinityBridge→Sentinel: {e}")

    async def on_sentinel_event(
        self,
        channel: str,
        payload: Dict[str, Any],
        event_type: str = "",
        source: str = "",
    ):
        """Handle a Sentinel Station event and forward into InfinityBridge."""
        if not self._forward_to_bridge:
            return

        try:
            # Only forward BRIDGE/PLATFORM/EVENTS channel events
            if channel.lower() not in {"bridge", "platform", "events"}:
                return

            # Emit into InfinityBridge event system
            bridge_event = InfinityBridgeEvent(
                event_type=f"sentinel:{event_type}" if event_type else "sentinel_forward",
                payload=payload,
                channel=channel,
            )
            self._bridge._emit_event(bridge_event)
            self._stats["sentinel_to_bridge"] += 1
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"Failed to forward Sentinel→InfinityBridge: {e}")

    def pause_sentinel_forward(self):
        """Stop forwarding InfinityBridge events to Sentinel Station."""
        self._forward_to_sentinel = False

    def resume_sentinel_forward(self):
        """Resume forwarding InfinityBridge events to Sentinel Station."""
        self._forward_to_sentinel = True

    def pause_bridge_forward(self):
        """Stop forwarding Sentinel events to InfinityBridge."""
        self._forward_to_bridge = False

    def resume_bridge_forward(self):
        """Resume forwarding Sentinel events to InfinityBridge."""
        self._forward_to_bridge = True

    async def get_status(self) -> Dict[str, Any]:
        """Get the current bridge status."""
        return {
            "bridge": "InfinitySentinelBridge",
            "description": "Bidirectional bridge for user/human traffic between InfinityBridge and Sentinel",
            "sentinel_attached": self._sentinel_station is not None,
            "handler_registered": self._handler_registered,
            "forward_to_sentinel": self._forward_to_sentinel,
            "forward_to_bridge": self._forward_to_bridge,
            "stats": dict(self._stats),
            "primary_channels": [ch.value for ch in self.INFINITY_PRIMARY_CHANNELS],
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_bridge_instance: Optional[InfinityBridge] = None
_sentinel_bridge_instance: Optional[InfinitySentinelBridge] = None


def get_infinity_bridge(db_path: str = ":memory:") -> InfinityBridge:
    """Get or create the InfinityBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = InfinityBridge(db_path)
        _bridge_instance.start()
    return _bridge_instance


def get_sentinel_bridge(bridge: Optional[InfinityBridge] = None) -> InfinitySentinelBridge:
    """Get or create the InfinityBridge-Sentinel Bridge singleton."""
    global _sentinel_bridge_instance
    if _sentinel_bridge_instance is None:
        _sentinel_bridge_instance = InfinitySentinelBridge(bridge)
    return _sentinel_bridge_instance
