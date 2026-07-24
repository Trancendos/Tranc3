"""
The Nexus — WebSocket API Worker
===================================
Self-hosted replacement for Cloudflare infinity-ws-api worker.
Provides real-time WebSocket communication for the Trancendos platform.

Features:
- WebSocket connection management (upgrade, heartbeat, close)
- Channel-based pub/sub messaging
- JWT authentication on WebSocket upgrade
- Rate limiting per connection
- Message broadcasting to channels
- Connection state tracking

Zero-cost: FastAPI WebSocket + asyncio. No CF Durable Objects.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

import jwt as pyjwt
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sanitize import sanitize_for_log

from src.entities.health_metadata import health_entity_block

logger = logging.getLogger("tranc3.workers.infinity-ws")

# ── Fail-fast on missing critical secrets ──────────────────────
_jwt_secret_raw = os.environ.get("JWT_SECRET")
if not _jwt_secret_raw:
    raise RuntimeError(
        "JWT_SECRET is not set. The Nexus cannot authenticate WebSocket connections. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
JWT_SECRET: str = _jwt_secret_raw

# ── Models ───────────────────────────────────────────────────


class WSMessage(BaseModel):
    """WebSocket message envelope."""

    type: str  # "subscribe", "unsubscribe", "message", "ping", "pong", "error"
    channel: Optional[str] = None
    data: Any = None
    timestamp: str = ""
    sender: str = ""
    message_id: str = ""


class ChannelInfo(BaseModel):
    """Channel information."""

    name: str
    subscribers: int = 0
    created_at: str = ""


class ConnectionStats(BaseModel):
    """Connection statistics."""

    total_connections: int = 0
    total_channels: int = 0
    messages_sent: int = 0
    uptime_seconds: float = 0.0


# ── Connection Manager ───────────────────────────────────────


class ConnectionManager:
    """
    Manages WebSocket connections and channel subscriptions.

    Replaces Cloudflare Durable Objects with in-memory state
    managed by asyncio. Connections are tracked per-channel
    for efficient broadcasting.
    """

    # Per-connection message rate limit: 60 messages per 60-second window
    _MSG_RATE_LIMIT = 60
    _MSG_RATE_WINDOW = 60.0

    def __init__(self, max_connections: int = 1000, max_channels: int = 100) -> None:
        self.max_connections = max_connections
        self.max_channels = max_channels
        # channel_name -> set of WebSocket connections
        self._channels: dict[str, set[WebSocket]] = defaultdict(set)
        # websocket -> set of channel names
        self._subscriptions: dict[WebSocket, set[str]] = defaultdict(set)
        # websocket -> connection metadata
        self._connections: dict[WebSocket, dict[str, Any]] = {}
        # websocket -> (message_count, window_start) for rate limiting
        self._msg_rate: dict[WebSocket, tuple[int, float]] = {}
        self._messages_sent = 0
        self._started_at = time.monotonic()

    @property
    def total_connections(self) -> int:
        return len(self._connections)

    @property
    def total_channels(self) -> int:
        return len(self._channels)

    @property
    def stats(self) -> ConnectionStats:
        return ConnectionStats(
            total_connections=self.total_connections,
            total_channels=self.total_channels,
            messages_sent=self._messages_sent,
            uptime_seconds=time.monotonic() - self._started_at,
        )

    async def connect(
        self, ws: WebSocket, user_id: str, metadata: dict[str, Any] | None = None
    ) -> bool:
        """Accept a new WebSocket connection."""
        if self.total_connections >= self.max_connections:
            await ws.close(code=1013, reason="Maximum connections reached")
            return False

        await ws.accept()
        self._connections[ws] = {
            "user_id": user_id,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        logger.info(
            "ws_connected: user=%s, total=%s",
            sanitize_for_log(user_id),
            self.total_connections,
        )  # codeql[py/cleartext-logging]
        return True

    def is_message_rate_limited(self, ws: WebSocket) -> bool:
        """Return True if this connection has exceeded the message rate limit."""
        now = time.monotonic()
        count, window_start = self._msg_rate.get(ws, (0, now))
        if now - window_start >= self._MSG_RATE_WINDOW:
            self._msg_rate[ws] = (1, now)
            return False
        count += 1
        self._msg_rate[ws] = (count, window_start)
        return count > self._MSG_RATE_LIMIT

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket connection and clean up subscriptions."""
        # Unsubscribe from all channels
        for channel in self._subscriptions.get(ws, set()):
            self._channels[channel].discard(ws)
            if not self._channels[channel]:
                del self._channels[channel]

        self._subscriptions.pop(ws, None)
        self._msg_rate.pop(ws, None)
        conn_info = self._connections.pop(ws, None)
        if conn_info:
            logger.info(
                "ws_disconnected: user=%s", sanitize_for_log(conn_info.get("user_id", "unknown"))
            )  # codeql[py/cleartext-logging]

    async def subscribe(self, ws: WebSocket, channel: str) -> bool:
        """Subscribe a connection to a channel."""
        if channel not in self._channels and self.total_channels >= self.max_channels:
            return False

        self._channels[channel].add(ws)
        self._subscriptions[ws].add(channel)

        # Notify channel of new subscriber
        await self._broadcast_to_channel(
            channel,
            WSMessage(
                type="subscribe",
                channel=channel,
                data={"subscriber_count": len(self._channels[channel])},
                sender="system",
                message_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            exclude=ws,
        )
        return True

    async def unsubscribe(self, ws: WebSocket, channel: str) -> bool:
        """Unsubscribe a connection from a channel."""
        self._channels[channel].discard(ws)
        self._subscriptions[ws].discard(channel)

        if not self._channels[channel]:
            del self._channels[channel]

        return True

    async def broadcast(self, ws: WebSocket, message: WSMessage) -> int:
        """Broadcast a message to a channel. Returns number of recipients."""
        channel = message.channel
        if not channel:
            return 0

        message.sender = self._connections.get(ws, {}).get("user_id", "unknown")
        message.message_id = str(uuid.uuid4())
        message.timestamp = datetime.now(timezone.utc).isoformat()

        recipients = await self._broadcast_to_channel(channel, message)
        self._messages_sent += recipients
        return recipients

    async def _broadcast_to_channel(
        self, channel: str, message: WSMessage, exclude: WebSocket | None = None
    ) -> int:
        """Broadcast a message to all connections in a channel."""
        recipients = self._channels.get(channel, set())
        sent = 0
        for ws in recipients:
            if ws == exclude:
                continue
            try:
                await ws.send_json(message.model_dump())
                sent += 1
            except Exception:
                # Connection is broken, will be cleaned up on disconnect
                pass
        return sent

    def get_channels(self) -> list[ChannelInfo]:
        """Get information about all active channels."""
        return [
            ChannelInfo(
                name=name,
                subscribers=len(connections),
                created_at="",  # Would track in production
            )
            for name, connections in self._channels.items()
        ]

    def get_user_channels(self, ws: WebSocket) -> list[str]:
        """Get channels a connection is subscribed to."""
        return list(self._subscriptions.get(ws, set()))


# ── JWT Verification (lightweight) ──────────────────────────


def verify_token(token: str, secret: str = "") -> dict[str, Any] | None:
    """Verify a JWT token signature and return its payload, or None on failure."""
    key = secret or JWT_SECRET
    try:
        return pyjwt.decode(token, key, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        logger.warning("token_verification_failed: token expired")
        return None
    except pyjwt.InvalidTokenError as e:
        logger.warning(
            "token_verification_failed: %s", sanitize_for_log(e)
        )  # codeql[py/cleartext-logging]
        return None


# ── FastAPI Application ──────────────────────────────────────

app = FastAPI(
    title="The Nexus — WebSocket API",
    description="Self-hosted WebSocket communication hub for Trancendos",
    version="1.0.0",
)

# OpenTelemetry instrumentation
try:
    from src.observability.worker_setup import instrument_worker

    instrument_worker(app, service_name="tranc3.infinity-ws")
except Exception:
    pass  # OTel is optional — never block startup

_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()

_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "infinity-ws",
        "connections": manager.total_connections,
        "channels": manager.total_channels,
        "entity": health_entity_block(8004, "infinity-ws"),
    }


@_router.get("/stats")
async def stats():
    """Get connection statistics."""
    return manager.stats.model_dump()


@_router.get("/channels")
async def list_channels():
    """List all active channels."""
    return {"channels": [c.model_dump() for c in manager.get_channels()]}


class BroadcastRequest(BaseModel):
    """Server-to-server broadcast request — lets other platform services
    (e.g. src.nexus.hub.NexusHub) fan an event out to WS subscribers without
    holding their own persistent connection to this worker."""

    channel: str
    data: Any = None
    type: str = "message"


@_router.post("/broadcast")
async def broadcast(body: BroadcastRequest):
    """Broadcast a server-originated message to all subscribers of a channel."""
    message = WSMessage(
        type=body.type,
        channel=body.channel,
        data=body.data,
        sender="system",
        message_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    recipients = await manager._broadcast_to_channel(body.channel, message)
    manager._messages_sent += recipients
    return {"channel": body.channel, "recipients": recipients}


@app.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    token: str = Query(default=""),
    user_id: str = Query(default="anonymous"),
):
    """
    Main WebSocket endpoint.

    Query params:
    - token: JWT token for authentication
    - user_id: User identifier (fallback if no token)
    """
    # Authenticate via token if provided
    if token:
        payload = verify_token(token)
        if payload:
            user_id = payload.get("sub", payload.get("user_id", user_id))
        else:
            await ws.close(code=4001, reason="Invalid token")
            return

    # Accept connection
    connected = await manager.connect(ws, user_id=user_id)
    if not connected:
        return

    try:
        while True:
            # Receive message
            raw = await ws.receive_text()

            # Per-connection message rate limit
            if manager.is_message_rate_limited(ws):
                await ws.send_json(
                    WSMessage(
                        type="error",
                        data={"error": "Rate limit exceeded. Max 60 messages per 60 seconds."},
                        sender="system",
                        message_id=str(uuid.uuid4()),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ).model_dump()
                )
                continue

            try:
                msg_data = json.loads(raw)
                message = WSMessage(**msg_data)
            except (json.JSONDecodeError, Exception) as e:
                await ws.send_json(
                    WSMessage(
                        type="error",
                        data={"error": f"Invalid message format: {e}"},
                        sender="system",
                        message_id=str(uuid.uuid4()),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ).model_dump()
                )
                continue

            # Handle message types
            if message.type == "ping":
                await ws.send_json(
                    WSMessage(
                        type="pong",
                        sender="system",
                        message_id=str(uuid.uuid4()),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ).model_dump()
                )

            elif message.type == "subscribe" and message.channel:
                success = await manager.subscribe(ws, message.channel)
                await ws.send_json(
                    WSMessage(
                        type="subscribed" if success else "error",
                        channel=message.channel,
                        data={"channels": manager.get_user_channels(ws)}
                        if success
                        else {"error": "Cannot subscribe"},
                        sender="system",
                        message_id=str(uuid.uuid4()),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ).model_dump()
                )

            elif message.type == "unsubscribe" and message.channel:
                await manager.unsubscribe(ws, message.channel)
                await ws.send_json(
                    WSMessage(
                        type="unsubscribed",
                        channel=message.channel,
                        data={"channels": manager.get_user_channels(ws)},
                        sender="system",
                        message_id=str(uuid.uuid4()),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ).model_dump()
                )

            elif message.type == "message" and message.channel:
                recipients = await manager.broadcast(ws, message)
                # Send delivery confirmation
                await ws.send_json(
                    WSMessage(
                        type="delivered",
                        channel=message.channel,
                        data={"recipients": recipients},
                        sender="system",
                        message_id=message.message_id,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ).model_dump()
                )

            elif message.type == "channels":
                channels = manager.get_user_channels(ws)
                await ws.send_json(
                    WSMessage(
                        type="channels",
                        data={"channels": channels},
                        sender="system",
                        message_id=str(uuid.uuid4()),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ).model_dump()
                )

    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        logger.error("ws_error: %s", sanitize_for_log(e))  # codeql[py/cleartext-logging]
        manager.disconnect(ws)


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)  # nosec B104 — containerised service
