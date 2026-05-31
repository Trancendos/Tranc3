"""
Tranc3 InfinityBridge Worker Service
=====================================
Standalone worker entry point for the InfinityBridge service.
Provides REST API and WebSocket endpoints for user context
management and human traffic coordination on port 8070.

Three Bridges:
    - InfinityBridge (port 8070) : User context / human traffic
    - The Nexus (port 8050)      : AI, Agent, Bot traffic
    - The HIVE (port 8060)       : Data movement / swarm coordination
"""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from Dimensional.infinity.bridge.bridge_core import (
    InfinityBridge,
    InfinityBridgeEvent,
    get_infinity_bridge,
)

logger = logging.getLogger(__name__)

WORKER_NAME = "infinity-bridge"
WORKER_PORT = int(os.environ.get("INFINITY_BRIDGE_PORT", "8070"))
_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

# Global bridge instance
_bridge: InfinityBridge | None = None
_ws_connections: list[WebSocket] = []


def get_bridge() -> InfinityBridge:
    global _bridge
    if _bridge is None:
        _bridge = get_infinity_bridge()
        # Register event handler for WebSocket broadcasting
        _bridge.register_handler("*", _on_bridge_event)
    return _bridge


def _on_bridge_event(event: InfinityBridgeEvent):
    """Broadcast bridge events to connected WebSocket clients."""
    import json

    data = json.dumps(event.to_dict())
    for ws in _ws_connections[:]:
        try:
            asyncio.get_event_loop().create_task(ws.send_text(data))
        except Exception:
            _ws_connections.remove(ws)


def create_bridge_app() -> FastAPI:
    """Create the FastAPI application for the InfinityBridge worker."""
    app = FastAPI(
        title="Tranc3 InfinityBridge",
        description="User Context & Human Traffic Coordinator (Light Bridge)",
        version="1.0.0",
    )

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

    _secret = _INTERNAL_SECRET

    @app.middleware("http")
    async def _internal_auth(request: Request, call_next):
        if _secret and request.url.path not in ("/health", "/"):
            token = request.headers.get("x-internal-secret", "")
            if token != _secret:
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)

    @app.get("/")
    async def root():
        return {
            "service": "Tranc3 InfinityBridge",
            "bridge_type": "infinity",
            "description": "User Context & Human Traffic Coordinator (Light Bridge)",
            "three_bridges": {
                "infinity_bridge": {
                    "name": "InfinityBridge",
                    "role": "User Context & Human Traffic",
                    "port": WORKER_PORT,
                    "bridge_type": "infinity",
                },
                "nexus": {
                    "name": "The Nexus",
                    "role": "AI, Agent, and Bot Traffic",
                    "port": 8050,
                    "bridge_type": "nexus",
                },
                "hive": {
                    "name": "The HIVE",
                    "role": "Data Movement & Swarm Coordination",
                    "port": 8060,
                    "bridge_type": "hive",
                },
            },
        }

    @app.get("/status")
    async def status():
        bridge = get_bridge()
        return bridge.get_status()

    @app.get("/health")
    async def health():
        bridge = get_bridge()
        return bridge.get_health()

    @app.post("/users/connect")
    async def connect_user(
        user_id: str,
        location: str = "infinity_portal",
        tier: int = 0,
        metadata: dict | None = None,
    ):
        bridge = get_bridge()
        ctx = bridge.connect_user(user_id, location, tier, metadata)
        return ctx.to_dict()

    @app.post("/users/{user_id}/disconnect")
    async def disconnect_user(user_id: str):
        bridge = get_bridge()
        ctx = bridge.disconnect_user(user_id)
        if ctx is None:
            return {"error": "User not found"}, 404
        return ctx.to_dict()

    @app.post("/users/{user_id}/transition")
    async def transition_user(user_id: str, target_location: str, transition_ms: float = 0.0):
        bridge = get_bridge()
        ctx = bridge.transition_user(user_id, target_location, transition_ms)
        if ctx is None:
            return {"error": "User not found"}, 404
        return ctx.to_dict()

    @app.post("/users/{user_id}/context")
    async def update_context(
        user_id: str,
        context_type: str = "session",
        updates: dict | None = None,
    ):
        bridge = get_bridge()
        ctx = bridge.update_context(user_id, context_type, updates)
        if ctx is None:
            return {"error": "User not found"}, 404
        return ctx.to_dict()

    @app.post("/users/{user_id}/presence")
    async def update_presence(user_id: str, status: str = "active"):
        bridge = get_bridge()
        success = bridge.update_presence(user_id, status)
        return {"success": success}

    @app.get("/users")
    async def list_users(location: str | None = None):
        bridge = get_bridge()
        if location:
            contexts = bridge.get_users_at_location(location)
        else:
            contexts = bridge.context_window.get_all()
        return [ctx.to_dict() for ctx in contexts]

    @app.get("/users/{user_id}")
    async def get_user(user_id: str):
        bridge = get_bridge()
        ctx = bridge.context_window.get(user_id)
        if ctx is None:
            return {"error": "User not found"}, 404
        return ctx.to_dict()

    @app.get("/paths")
    async def list_paths():
        bridge = get_bridge()
        return [p.to_dict() for p in bridge.paths.get_all_paths()]

    @app.post("/paths/open")
    async def open_path(source: str, target: str):
        bridge = get_bridge()
        path = bridge.open_bridge(source, target)
        return path.to_dict()

    @app.post("/paths/close")
    async def close_path(source: str, target: str):
        bridge = get_bridge()
        path = bridge.close_bridge(source, target)
        if path is None:
            return {"error": "Path not found"}, 404
        return path.to_dict()

    @app.get("/locations")
    async def list_locations():
        bridge = get_bridge()
        return bridge.context_window.get_location_counts()

    @app.get("/presence")
    async def get_presence():
        bridge = get_bridge()
        return bridge.presence.get_stats()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        _ws_connections.append(websocket)
        try:
            while True:
                await websocket.receive_text()
                # Keep connection alive
        except WebSocketDisconnect:
            _ws_connections.remove(websocket)

    return app


# Module-level app — used by tests and the __main__ entry point
app = create_bridge_app()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = get_bridge()

    # Set up default bridge paths
    locations = [
        "infinity_portal",
        "infinity_gate",
        "infinity_arcadia",
        "infinity_citadel",
        "infinity_admin",
    ]
    for i, source in enumerate(locations):
        for target in locations[i + 1 :]:
            bridge.open_bridge(source, target)

    logger.info(f"InfinityBridge worker starting on port {WORKER_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
