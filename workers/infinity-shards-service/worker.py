"""
Infinity Shards Service — Pluggable Entity Power-Ups (Port 8045)
================================================================
Infinity Shards are pluggable capability modules that attach to any
Trancendos platform entity to enhance and extend its powers — similar
to Gemini Gems but for AI entities.

Each Shard is a self-contained capability bundle:

  MEMORY    — Persistent long-term episodic memory (vector recall)
  VOICE     — TTS + speech recognition activation
  VISION    — Image / video processing capabilities
  SHIELD    — Enhanced security hardening + threat monitoring
  BOOST     — Rate limit elevation + performance tuning
  LINK      — Cross-entity communication bridge
  SENSE     — Data feed awareness (IoT, live streams, webhooks)
  SPARK     — MCP tool extension — additional tool slots for The Spark

Shards are activated per entity. An entity can hold multiple Shards.
The Shards service is consulted at entity startup and at runtime to
determine which capabilities are active.

Endpoints:
  GET  /health                        — service health
  GET  /shards                        — catalogue of all available Shard types
  GET  /entities/{entity_id}/shards   — which Shards are active for an entity
  POST /entities/{entity_id}/shards   — attach a Shard to an entity
  DELETE /entities/{entity_id}/shards/{shard_type} — detach a Shard
  GET  /entities/{entity_id}/shards/{shard_type}/config — Shard config
  PUT  /entities/{entity_id}/shards/{shard_type}/config — update Shard config
  GET  /entities/{entity_id}/power    — aggregate power score from active Shards
  POST /shards/{shard_type}/invoke    — invoke a Shard capability directly

Port: 8045
Zero-cost: FastAPI + SQLite. No external deps beyond core platform.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("INFINITY_SHARDS_PORT", "8045"))
DB_PATH = os.environ.get("INFINITY_SHARDS_DB_PATH", "data/infinity_shards.db")

# ── Shard Catalogue ──────────────────────────────────────────────────────────

SHARD_CATALOGUE: Dict[str, Dict[str, Any]] = {
    "memory": {
        "id": "memory",
        "name": "Memory Shard",
        "symbol": "🔮",
        "description": "Persistent long-term episodic memory. The entity remembers across sessions, recalls past interactions, and builds a personal knowledge base over time.",
        "tier": "core",
        "power_rating": 8,
        "capabilities": ["recall", "store", "forget", "summarise_history"],
        "config_schema": {
            "vector_backend": {"type": "string", "default": "qdrant", "options": ["qdrant", "faiss", "memory"]},
            "retention_days": {"type": "integer", "default": 90},
            "max_memories": {"type": "integer", "default": 10000},
        },
        "compatible_entities": "*",
    },
    "voice": {
        "id": "voice",
        "name": "Voice Shard",
        "symbol": "🎙️",
        "description": "Activates full voice capabilities: TTS synthesis via Kokoro, real-time speech recognition, and phoneme-level lip sync output for 3D avatar rendering.",
        "tier": "core",
        "power_rating": 7,
        "capabilities": ["speak", "listen", "lip_sync", "emote_voice"],
        "config_schema": {
            "tts_engine": {"type": "string", "default": "kokoro", "options": ["kokoro", "piper"]},
            "voice_id": {"type": "string", "default": "auto"},
            "speech_speed": {"type": "float", "default": 1.0},
            "lip_sync_enabled": {"type": "boolean", "default": True},
        },
        "compatible_entities": "*",
    },
    "vision": {
        "id": "vision",
        "name": "Vision Shard",
        "symbol": "👁️",
        "description": "Image and video processing. The entity can analyse screenshots, describe images, read documents visually, and process video frames.",
        "tier": "enhanced",
        "power_rating": 9,
        "capabilities": ["analyse_image", "describe_scene", "read_document", "detect_objects"],
        "config_schema": {
            "model": {"type": "string", "default": "ollama/llava", "options": ["ollama/llava", "ollama/bakllava"]},
            "max_image_size_mb": {"type": "integer", "default": 10},
        },
        "compatible_entities": "*",
    },
    "shield": {
        "id": "shield",
        "name": "Shield Shard",
        "symbol": "🛡️",
        "description": "Enhanced security hardening. Adds threat monitoring, anomaly detection, IP reputation checks, and automatic incident response to any entity.",
        "tier": "security",
        "power_rating": 9,
        "capabilities": ["threat_scan", "anomaly_detect", "ip_block", "incident_report"],
        "config_schema": {
            "threat_threshold": {"type": "float", "default": 0.7},
            "auto_block": {"type": "boolean", "default": False},
            "alert_channel": {"type": "string", "default": "sentinel_station"},
        },
        "compatible_entities": "*",
    },
    "boost": {
        "id": "boost",
        "name": "Boost Shard",
        "symbol": "⚡",
        "description": "Performance and rate limit elevation. Increases request throughput, reduces latency via caching, and grants elevated priority in the AI Gateway queue.",
        "tier": "performance",
        "power_rating": 6,
        "capabilities": ["rate_elevate", "cache_warm", "priority_queue", "response_compress"],
        "config_schema": {
            "rate_multiplier": {"type": "float", "default": 2.0},
            "cache_ttl_seconds": {"type": "integer", "default": 300},
            "priority_level": {"type": "integer", "default": 1},
        },
        "compatible_entities": "*",
    },
    "link": {
        "id": "link",
        "name": "Link Shard",
        "symbol": "🔗",
        "description": "Cross-entity communication bridge. Allows an entity to directly publish events to and subscribe from other platform entities via the Dimensional event bus.",
        "tier": "connectivity",
        "power_rating": 7,
        "capabilities": ["publish_event", "subscribe_entity", "relay_message", "broadcast"],
        "config_schema": {
            "allowed_targets": {"type": "array", "default": []},
            "max_subscribers": {"type": "integer", "default": 10},
            "relay_timeout_ms": {"type": "integer", "default": 5000},
        },
        "compatible_entities": "*",
    },
    "sense": {
        "id": "sense",
        "name": "Sense Shard",
        "symbol": "📡",
        "description": "Data feed awareness. Connects an entity to live data streams — webhooks, IoT sensors, RSS/Atom feeds, WebSocket streams — and triggers reactive behaviours.",
        "tier": "awareness",
        "power_rating": 8,
        "capabilities": ["webhook_receive", "feed_subscribe", "stream_monitor", "event_trigger"],
        "config_schema": {
            "feed_urls": {"type": "array", "default": []},
            "poll_interval_seconds": {"type": "integer", "default": 60},
            "max_feeds": {"type": "integer", "default": 5},
        },
        "compatible_entities": "*",
    },
    "spark": {
        "id": "spark",
        "name": "Spark Shard",
        "symbol": "✨",
        "description": "MCP tool extension via The Spark. Grants the entity access to additional registered tool slots beyond its default allocation — expanding what it can do and call.",
        "tier": "intelligence",
        "power_rating": 10,
        "capabilities": ["tool_register", "tool_invoke", "tool_discover", "rag_expand"],
        "config_schema": {
            "extra_tool_slots": {"type": "integer", "default": 10},
            "rag_enabled": {"type": "boolean", "default": True},
            "tool_categories": {"type": "array", "default": []},
        },
        "compatible_entities": "*",
    },
}

# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entity_shards (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                shard_type TEXT NOT NULL,
                config TEXT NOT NULL DEFAULT '{}',
                active INTEGER NOT NULL DEFAULT 1,
                attached_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(entity_id, shard_type)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_entity_shards_entity
            ON entity_shards(entity_id)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shard_invocations (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                shard_type TEXT NOT NULL,
                capability TEXT NOT NULL,
                input_summary TEXT,
                result_summary TEXT,
                duration_ms REAL,
                invoked_at TEXT NOT NULL
            )
        """)
        conn.commit()


# ── Pydantic Models ───────────────────────────────────────────────────────────

class AttachShardRequest(BaseModel):
    shard_type: str
    config: Dict[str, Any] = Field(default_factory=dict)


class UpdateShardConfigRequest(BaseModel):
    config: Dict[str, Any]


class InvokeShardRequest(BaseModel):
    entity_id: str
    capability: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ShardRecord(BaseModel):
    id: str
    entity_id: str
    shard_type: str
    shard_name: str
    shard_symbol: str
    power_rating: int
    config: Dict[str, Any]
    capabilities: List[str]
    active: bool
    attached_at: str
    updated_at: str


class EntityPower(BaseModel):
    entity_id: str
    active_shards: int
    total_power: int
    shards: List[str]
    capabilities: List[str]


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Infinity Shards service starting on port %d", PORT)
    yield
    logger.info("Infinity Shards service shutting down")


app = FastAPI(
    title="Infinity Shards",
    description="Pluggable entity power-up modules for the Trancendos Universe",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_shard_record(row: sqlite3.Row) -> ShardRecord:
    meta = SHARD_CATALOGUE.get(row["shard_type"], {})
    config = json.loads(row["config"])
    # Merge defaults for any missing keys
    schema = meta.get("config_schema", {})
    merged = {k: v["default"] for k, v in schema.items()}
    merged.update(config)
    return ShardRecord(
        id=row["id"],
        entity_id=row["entity_id"],
        shard_type=row["shard_type"],
        shard_name=meta.get("name", row["shard_type"]),
        shard_symbol=meta.get("symbol", "◆"),
        power_rating=meta.get("power_rating", 0),
        config=merged,
        capabilities=meta.get("capabilities", []),
        active=bool(row["active"]),
        attached_at=row["attached_at"],
        updated_at=row["updated_at"],
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "infinity-shards",
        "port": PORT,
        "shard_types_available": len(SHARD_CATALOGUE),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/shards")
async def list_shards():
    """Return the full catalogue of available Shard types."""
    return {
        "shards": list(SHARD_CATALOGUE.values()),
        "total": len(SHARD_CATALOGUE),
    }


@app.get("/shards/{shard_type}")
async def get_shard_type(shard_type: str):
    """Return details for a specific Shard type."""
    shard = SHARD_CATALOGUE.get(shard_type)
    if not shard:
        raise HTTPException(status_code=404, detail=f"Shard type '{shard_type}' not found")
    return shard


@app.get("/entities/{entity_id}/shards")
async def get_entity_shards(entity_id: str):
    """List all Shards attached to an entity."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM entity_shards WHERE entity_id = ? ORDER BY attached_at",
            (entity_id,),
        ).fetchall()
    shards = [_row_to_shard_record(r) for r in rows]
    return {
        "entity_id": entity_id,
        "shards": [s.model_dump() for s in shards],
        "active_count": sum(1 for s in shards if s.active),
    }


@app.post("/entities/{entity_id}/shards", status_code=201)
async def attach_shard(entity_id: str, req: AttachShardRequest):
    """Attach a Shard to an entity."""
    if req.shard_type not in SHARD_CATALOGUE:
        raise HTTPException(status_code=400, detail=f"Unknown shard type: {req.shard_type}")

    meta = SHARD_CATALOGUE[req.shard_type]
    schema = meta.get("config_schema", {})
    defaults = {k: v["default"] for k, v in schema.items()}
    config = {**defaults, **req.config}

    now = datetime.now(timezone.utc).isoformat()
    record_id = str(uuid.uuid4())

    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO entity_shards (id, entity_id, shard_type, config, active, attached_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (record_id, entity_id, req.shard_type, json.dumps(config), now, now),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=f"Shard '{req.shard_type}' is already attached to entity '{entity_id}'",
        )

    return {
        "message": f"{meta['name']} {meta['symbol']} attached to {entity_id}",
        "shard_type": req.shard_type,
        "entity_id": entity_id,
        "power_added": meta["power_rating"],
        "capabilities_unlocked": meta["capabilities"],
        "config": config,
    }


@app.delete("/entities/{entity_id}/shards/{shard_type}")
async def detach_shard(entity_id: str, shard_type: str):
    """Detach a Shard from an entity."""
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM entity_shards WHERE entity_id = ? AND shard_type = ?",
            (entity_id, shard_type),
        )
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Shard '{shard_type}' not attached to entity '{entity_id}'",
        )
    meta = SHARD_CATALOGUE.get(shard_type, {})
    return {
        "message": f"{meta.get('name', shard_type)} detached from {entity_id}",
        "entity_id": entity_id,
        "shard_type": shard_type,
    }


@app.get("/entities/{entity_id}/shards/{shard_type}/config")
async def get_shard_config(entity_id: str, shard_type: str):
    """Get the configuration for a specific Shard on an entity."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM entity_shards WHERE entity_id = ? AND shard_type = ?",
            (entity_id, shard_type),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Shard not found on this entity")
    return {"entity_id": entity_id, "shard_type": shard_type, "config": json.loads(row["config"])}


@app.put("/entities/{entity_id}/shards/{shard_type}/config")
async def update_shard_config(entity_id: str, shard_type: str, req: UpdateShardConfigRequest):
    """Update the configuration for a Shard on an entity."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM entity_shards WHERE entity_id = ? AND shard_type = ?",
            (entity_id, shard_type),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Shard not found on this entity")
        existing = json.loads(row["config"])
        existing.update(req.config)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE entity_shards SET config = ?, updated_at = ? WHERE entity_id = ? AND shard_type = ?",
            (json.dumps(existing), now, entity_id, shard_type),
        )
        conn.commit()
    return {"entity_id": entity_id, "shard_type": shard_type, "config": existing}


@app.get("/entities/{entity_id}/power")
async def get_entity_power(entity_id: str) -> EntityPower:
    """Return the aggregate power score from all active Shards on an entity."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM entity_shards WHERE entity_id = ? AND active = 1",
            (entity_id,),
        ).fetchall()

    total_power = 0
    shard_names = []
    all_capabilities: List[str] = []

    for row in rows:
        meta = SHARD_CATALOGUE.get(row["shard_type"], {})
        total_power += meta.get("power_rating", 0)
        shard_names.append(row["shard_type"])
        all_capabilities.extend(meta.get("capabilities", []))

    return EntityPower(
        entity_id=entity_id,
        active_shards=len(rows),
        total_power=total_power,
        shards=shard_names,
        capabilities=list(set(all_capabilities)),
    )


@app.post("/shards/{shard_type}/invoke")
async def invoke_shard(shard_type: str, req: InvokeShardRequest):
    """
    Invoke a Shard capability directly.

    This is the runtime hook — when an entity needs to use a Shard capability
    (e.g. recall a memory, speak text, check a threat) it calls this endpoint.
    The Shards service routes the invocation to the appropriate backend service.
    """
    if shard_type not in SHARD_CATALOGUE:
        raise HTTPException(status_code=400, detail=f"Unknown shard type: {shard_type}")

    meta = SHARD_CATALOGUE[shard_type]
    if req.capability not in meta["capabilities"]:
        raise HTTPException(
            status_code=400,
            detail=f"Capability '{req.capability}' not available in {meta['name']}. Available: {meta['capabilities']}",
        )

    # Verify the entity has this Shard attached
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM entity_shards WHERE entity_id = ? AND shard_type = ? AND active = 1",
            (req.entity_id, shard_type),
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=403,
            detail=f"Entity '{req.entity_id}' does not have the {meta['name']} attached",
        )

    config = json.loads(row["config"])

    # Route to the appropriate backend based on shard type + capability
    result = _dispatch_capability(shard_type, req.capability, req.payload, config)

    # Log the invocation
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO shard_invocations
               (id, entity_id, shard_type, capability, input_summary, result_summary, invoked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                req.entity_id,
                shard_type,
                req.capability,
                str(req.payload)[:200],
                str(result)[:200],
                now,
            ),
        )
        conn.commit()

    return {
        "entity_id": req.entity_id,
        "shard_type": shard_type,
        "capability": req.capability,
        "result": result,
        "timestamp": now,
    }


def _dispatch_capability(
    shard_type: str,
    capability: str,
    payload: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route a Shard capability invocation to the appropriate backend.

    Each Shard delegates to an existing platform service:
      memory  → Qdrant / vector store
      voice   → turings-hub-service (Kokoro TTS + Rhubarb)
      vision  → infinity-ai (Ollama LLaVA)
      shield  → Dimensional security layer
      boost   → cache-service / rate-limit-service
      link    → Dimensional event bus
      sense   → External feed poller
      spark   → The Spark MCP server
    """
    # Phase 1: return capability acknowledgement with routing info
    # Phase 2: add real httpx calls to each backend service
    ROUTING = {
        "memory":  {"backend": "qdrant / vector store",    "endpoint": "/memory"},
        "voice":   {"backend": "turings-hub-service:8035", "endpoint": "/entities/{entity_id}/speak"},
        "vision":  {"backend": "infinity-ai:8009",         "endpoint": "/v1/chat/completions (vision)"},
        "shield":  {"backend": "Dimensional security",     "endpoint": "/security/scan"},
        "boost":   {"backend": "cache-service:8018",       "endpoint": "/cache/warm"},
        "link":    {"backend": "Dimensional event bus",    "endpoint": "/bus/publish"},
        "sense":   {"backend": "feed poller",              "endpoint": "/feeds/trigger"},
        "spark":   {"backend": "mcp-server:8000/mcp",      "endpoint": "/mcp/rpc"},
    }
    routing = ROUTING.get(shard_type, {})
    return {
        "status": "dispatched",
        "capability": capability,
        "backend": routing.get("backend", "unknown"),
        "endpoint": routing.get("endpoint", ""),
        "payload_keys": list(payload.keys()),
        "note": "Phase 1: routing layer active. Phase 2 will add live backend calls.",
    }


@app.get("/entities/{entity_id}/shards/{shard_type}/invocations")
async def get_shard_invocations(entity_id: str, shard_type: str, limit: int = 50):
    """Return recent invocations for a Shard on an entity."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM shard_invocations
               WHERE entity_id = ? AND shard_type = ?
               ORDER BY invoked_at DESC LIMIT ?""",
            (entity_id, shard_type, limit),
        ).fetchall()
    return {
        "entity_id": entity_id,
        "shard_type": shard_type,
        "invocations": [dict(r) for r in rows],
    }


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
