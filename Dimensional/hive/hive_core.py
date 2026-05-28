"""
The HIVE — Data Movement and Swarm System Coordination
========================================================
The HIVE is the dedicated routing and coordination system for data movement
and swarm systems within the Tranc3 platform. It is ONE of the three bridges
that route traffic through Sentinel Station:

    Bridge 1 — InfinityBridge : User context / human traffic (Light bridges)
    Bridge 2 — The Nexus      : AI, Agent, and Bot movement and traffic
    Bridge 3 — The HIVE (THIS): Data movement and swarm system coordination

The HIVE provides:
    - Data pipeline registration and lifecycle management
    - Swarm coordination for distributed data processing
    - Data replication and distribution across the platform
    - Flow monitoring with throughput and latency tracking
    - Data chunk routing with priority and acknowledgment
    - Cross-Hive event routing via Sentinel Station channels
    - Topology mapping of data sources, sinks, and processing nodes

The HIVE handles ALL data traffic — dataset transfers, model weight
distributions, configuration propagation, log aggregation, metric streams,
and any other data that needs to move around the platform. Swarm systems
use the HIVE to coordinate distributed data processing tasks.

Tier Hierarchy (Mandatory Custom Definitions):
    Tier 0: HUMAN — Override authority, maximum access
    Tier 1: ORCHESTRATOR — System-level coordination
    Tier 2: PRIME — Strategic decision-making
    Tier 3: AI — The overarching ML/LLM Complex
    Tier 4: AGENT — Lower-level autonomous AI
    Tier 5: BOT — Stateless service worker/function

IMPORTANT: The HIVE is NOT for AI/Agent/Bot traffic (that is The Nexus).
The HIVE is NOT for user traffic (that is InfinityBridge). The HIVE is
specifically and exclusively for data movement and swarm coordination.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from Dimensional.infinity.nomenclature import (
    SentinelChannel,
)

logger = logging.getLogger("hive")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HIVE_DB_PATH = os.environ.get("HIVE_DB_PATH", "data/hive.db")
HIVE_PORT = int(os.environ.get("HIVE_PORT", "8060"))
HIVE_HEALTH_INTERVAL = int(os.environ.get("HIVE_HEALTH_INTERVAL", "30"))
HIVE_CHUNK_BUFFER_SIZE = int(os.environ.get("HIVE_CHUNK_BUFFER_SIZE", "10000"))
HIVE_MAX_REPLICATION = int(os.environ.get("HIVE_MAX_REPLICATION", "5"))

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class DataPriority(str, Enum):
    """Priority levels for data chunks moving through the HIVE."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


class SwarmStatus(str, Enum):
    """Status of a data-processing swarm."""

    FORMING = "forming"
    ACTIVE = "active"
    SCALING = "scaling"
    DRAINING = "draining"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStatus(str, Enum):
    """Status of a data pipeline."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class HiveDataSource(BaseModel):
    """A data source registered with the HIVE."""

    source_id: str = Field(default_factory=lambda: f"src-{uuid.uuid4().hex[:8]}")
    name: str
    data_type: str = Field(
        description="Type of data: dataset, model_weights, config, logs, metrics, etc."
    )
    pillar: str = Field(description="Which pillar this source belongs to")
    throughput_mbps: float = 0.0
    status: str = "unknown"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    registered_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HiveDataSink(BaseModel):
    """A data sink (destination) registered with the HIVE."""

    sink_id: str = Field(default_factory=lambda: f"sink-{uuid.uuid4().hex[:8]}")
    name: str
    data_type: str
    pillar: str
    consumption_rate_mbps: float = 0.0
    status: str = "unknown"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    registered_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DataChunk(BaseModel):
    """A chunk of data moving through the HIVE."""

    chunk_id: str = Field(default_factory=lambda: f"chk-{uuid.uuid4().hex[:8]}")
    pipeline_id: str
    source_id: str
    sink_id: str
    priority: DataPriority = DataPriority.NORMAL
    size_bytes: int = 0
    checksum: str = ""
    status: str = "pending"
    hops: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    delivered_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SwarmNode(BaseModel):
    """A node participating in a data-processing swarm."""

    node_id: str
    role: str = "worker"
    capacity: float = 1.0
    current_load: float = 0.0
    status: str = "idle"
    tasks_completed: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Swarm(BaseModel):
    """A data-processing swarm coordinated by the HIVE."""

    swarm_id: str = Field(default_factory=lambda: f"swarm-{uuid.uuid4().hex[:8]}")
    name: str
    purpose: str = Field(
        description="What this swarm processes: ETL, aggregation, replication, etc."
    )
    status: SwarmStatus = SwarmStatus.FORMING
    nodes: List[SwarmNode] = Field(default_factory=list)
    data_type: str = ""
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DataPipeline(BaseModel):
    """A data pipeline managed by the HIVE."""

    pipeline_id: str = Field(default_factory=lambda: f"pipe-{uuid.uuid4().hex[:8]}")
    name: str
    source_id: str
    sink_ids: List[str] = Field(default_factory=list)
    status: PipelineStatus = PipelineStatus.PENDING
    priority: DataPriority = DataPriority.NORMAL
    replication_factor: int = 1
    total_chunks: int = 0
    delivered_chunks: int = 0
    failed_chunks: int = 0
    throughput_mbps: float = 0.0
    latency_ms: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HiveEvent(BaseModel):
    """An event in the HIVE data flow."""

    event_id: str = Field(default_factory=lambda: f"hevt-{uuid.uuid4().hex[:8]}")
    channel: str
    source: str
    event_type: str
    priority: DataPriority = DataPriority.NORMAL
    payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HiveHealthSummary(BaseModel):
    """Aggregate health of the HIVE data movement system."""

    total_sources: int = 0
    total_sinks: int = 0
    active_pipelines: int = 0
    active_swarms: int = 0
    pending_chunks: int = 0
    delivered_chunks: int = 0
    failed_chunks: int = 0
    total_throughput_mbps: float = 0.0
    avg_latency_ms: float = 0.0
    status: str = "unknown"


# ---------------------------------------------------------------------------
# Flow Monitor — tracks data throughput and latency
# ---------------------------------------------------------------------------


class FlowMonitor:
    """
    Monitors data flow through the HIVE.

    Tracks throughput, latency, chunk delivery rates, and error rates
    for all data pipelines and swarm operations.
    """

    def __init__(self, db_path: str = HIVE_DB_PATH):
        self.db_path = db_path
        self._throughput_samples: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
        self._latency_samples: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
        self._chunks_pending: int = 0
        self._chunks_delivered: int = 0
        self._chunks_failed: int = 0
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self):
        """Initialize SQLite tables for persistent flow data."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hive_flow_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pipeline_id TEXT,
                    metric_type TEXT,
                    value REAL,
                    timestamp REAL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.commit()

    async def record_throughput(self, pipeline_id: str, mbps: float) -> None:
        """Record a throughput sample for a pipeline."""
        now = time.time()
        async with self._lock:
            self._throughput_samples[pipeline_id].append((now, mbps))
            # Keep last 1000 samples per pipeline
            if len(self._throughput_samples[pipeline_id]) > 1000:
                self._throughput_samples[pipeline_id] = self._throughput_samples[pipeline_id][-500:]

    async def record_latency(self, pipeline_id: str, latency_ms: float) -> None:
        """Record a latency sample for a pipeline."""
        now = time.time()
        async with self._lock:
            self._latency_samples[pipeline_id].append((now, latency_ms))
            if len(self._latency_samples[pipeline_id]) > 1000:
                self._latency_samples[pipeline_id] = self._latency_samples[pipeline_id][-500:]

    async def record_chunk_status(self, status: str) -> None:
        """Record a chunk status change."""
        async with self._lock:
            if status == "pending":
                self._chunks_pending += 1
            elif status == "delivered":
                self._chunks_delivered += 1
                self._chunks_pending = max(0, self._chunks_pending - 1)
            elif status == "failed":
                self._chunks_failed += 1
                self._chunks_pending = max(0, self._chunks_pending - 1)

    async def get_throughput(self, pipeline_id: str) -> float:
        """Get average throughput for a pipeline over the last 60s."""
        cutoff = time.time() - 60
        async with self._lock:
            samples = [
                (t, v) for t, v in self._throughput_samples.get(pipeline_id, []) if t > cutoff
            ]
            if not samples:
                return 0.0
            return sum(v for _, v in samples) / len(samples)

    async def get_latency(self, pipeline_id: str) -> float:
        """Get average latency for a pipeline over the last 60s."""
        cutoff = time.time() - 60
        async with self._lock:
            samples = [(t, v) for t, v in self._latency_samples.get(pipeline_id, []) if t > cutoff]
            if not samples:
                return 0.0
            return sum(v for _, v in samples) / len(samples)

    async def get_summary(self) -> Dict[str, Any]:
        """Get flow monitoring summary."""
        async with self._lock:
            all_throughputs = []
            all_latencies = []
            for samples in self._throughput_samples.values():
                cutoff = time.time() - 60
                recent = [v for t, v in samples if t > cutoff]
                all_throughputs.extend(recent)
            for samples in self._latency_samples.values():
                cutoff = time.time() - 60
                recent = [v for t, v in samples if t > cutoff]
                all_latencies.extend(recent)

            return {
                "total_throughput_mbps": sum(all_throughputs) if all_throughputs else 0.0,
                "avg_latency_ms": sum(all_latencies) / len(all_latencies) if all_latencies else 0.0,
                "chunks_pending": self._chunks_pending,
                "chunks_delivered": self._chunks_delivered,
                "chunks_failed": self._chunks_failed,
                "pipelines_monitored": len(self._throughput_samples),
            }


# ---------------------------------------------------------------------------
# Swarm Coordinator — manages data-processing swarms
# ---------------------------------------------------------------------------


class SwarmCoordinator:
    """
    Coordinates data-processing swarms in the HIVE.

    Manages swarm lifecycle: formation, task distribution, scaling,
    and completion. Each swarm is a group of nodes processing a
    shared data task (ETL, aggregation, replication, etc.).
    """

    def __init__(self):
        self._swarms: Dict[str, Swarm] = {}
        self._lock = asyncio.Lock()
        logger.info("SwarmCoordinator initialized")

    async def create_swarm(
        self,
        name: str,
        purpose: str,
        data_type: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Swarm:
        """Create a new data-processing swarm."""
        swarm = Swarm(
            name=name,
            purpose=purpose,
            data_type=data_type,
            status=SwarmStatus.FORMING,
            metadata=metadata or {},
        )
        async with self._lock:
            self._swarms[swarm.swarm_id] = swarm
        logger.info(f"Swarm created: {name} ({swarm.swarm_id}) — {purpose}")
        return swarm

    async def add_node(self, swarm_id: str, node: SwarmNode) -> None:
        """Add a processing node to a swarm."""
        async with self._lock:
            if swarm_id not in self._swarms:
                raise ValueError(f"Swarm {swarm_id} not found")
            self._swarms[swarm_id].nodes.append(node)
            # Auto-activate swarm if it has at least one node
            if self._swarms[swarm_id].status == SwarmStatus.FORMING:
                self._swarms[swarm_id].status = SwarmStatus.ACTIVE
                logger.info(f"Swarm {swarm_id} activated with first node")

    async def remove_node(self, swarm_id: str, node_id: str) -> None:
        """Remove a processing node from a swarm."""
        async with self._lock:
            if swarm_id not in self._swarms:
                raise ValueError(f"Swarm {swarm_id} not found")
            swarm = self._swarms[swarm_id]
            swarm.nodes = [n for n in swarm.nodes if n.node_id != node_id]
            if not swarm.nodes and swarm.status == SwarmStatus.ACTIVE:
                swarm.status = SwarmStatus.DRAINING
                logger.info(f"Swarm {swarm_id} draining — no nodes remaining")

    async def update_task_progress(
        self,
        swarm_id: str,
        node_id: str,
        tasks_completed: int = 0,
        tasks_failed: int = 0,
    ) -> None:
        """Update task progress for a swarm node."""
        async with self._lock:
            if swarm_id not in self._swarms:
                raise ValueError(f"Swarm {swarm_id} not found")
            swarm = self._swarms[swarm_id]
            for node in swarm.nodes:
                if node.node_id == node_id:
                    node.tasks_completed += tasks_completed
                    node.current_load = max(0, node.current_load - (tasks_completed + tasks_failed))
                    break
            swarm.completed_tasks += tasks_completed
            swarm.failed_tasks += tasks_failed
            # Check completion
            if (
                swarm.total_tasks > 0
                and swarm.completed_tasks + swarm.failed_tasks >= swarm.total_tasks
            ):
                swarm.status = (
                    SwarmStatus.COMPLETED if swarm.failed_tasks == 0 else SwarmStatus.FAILED
                )
                logger.info(
                    f"Swarm {swarm_id} completed: {swarm.completed_tasks} done, {swarm.failed_tasks} failed"
                )

    async def get_swarm(self, swarm_id: str) -> Optional[Swarm]:
        """Get a swarm by ID."""
        async with self._lock:
            return self._swarms.get(swarm_id)

    async def list_swarms(self, status: Optional[SwarmStatus] = None) -> List[Swarm]:
        """List all swarms, optionally filtered by status."""
        async with self._lock:
            swarms = list(self._swarms.values())
            if status:
                swarms = [s for s in swarms if s.status == status]
            return swarms

    async def dissolve_swarm(self, swarm_id: str) -> None:
        """Dissolve a swarm — release all nodes."""
        async with self._lock:
            if swarm_id in self._swarms:
                self._swarms[swarm_id].status = SwarmStatus.DRAINING
                self._swarms[swarm_id].nodes = []
                del self._swarms[swarm_id]
                logger.info(f"Swarm {swarm_id} dissolved")


# ---------------------------------------------------------------------------
# Pipeline Manager — manages data pipelines
# ---------------------------------------------------------------------------


class PipelineManager:
    """
    Manages data pipelines in the HIVE.

    Handles pipeline creation, chunk routing, replication,
    delivery tracking, and status management.
    """

    def __init__(self, flow_monitor: FlowMonitor):
        self.flow_monitor = flow_monitor
        self._pipelines: Dict[str, DataPipeline] = {}
        self._chunks: Dict[str, DataChunk] = defaultdict(lambda: [])  # type: ignore[arg-type,return-value]
        self._lock = asyncio.Lock()
        logger.info("PipelineManager initialized")

    async def create_pipeline(
        self,
        name: str,
        source_id: str,
        sink_ids: List[str],
        priority: DataPriority = DataPriority.NORMAL,
        replication_factor: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DataPipeline:
        """Create a new data pipeline."""
        pipeline = DataPipeline(
            name=name,
            source_id=source_id,
            sink_ids=sink_ids,
            status=PipelineStatus.PENDING,
            priority=priority,
            replication_factor=min(replication_factor, HIVE_MAX_REPLICATION),
            metadata=metadata or {},
        )
        async with self._lock:
            self._pipelines[pipeline.pipeline_id] = pipeline
        logger.info(f"Pipeline created: {name} ({pipeline.pipeline_id})")
        return pipeline

    async def start_pipeline(self, pipeline_id: str) -> None:
        """Start a pipeline."""
        async with self._lock:
            if pipeline_id not in self._pipelines:
                raise ValueError(f"Pipeline {pipeline_id} not found")
            self._pipelines[pipeline_id].status = PipelineStatus.RUNNING
            logger.info(f"Pipeline {pipeline_id} started")

    async def pause_pipeline(self, pipeline_id: str) -> None:
        """Pause a running pipeline."""
        async with self._lock:
            if pipeline_id not in self._pipelines:
                raise ValueError(f"Pipeline {pipeline_id} not found")
            if self._pipelines[pipeline_id].status != PipelineStatus.RUNNING:
                raise ValueError(f"Pipeline {pipeline_id} is not running")
            self._pipelines[pipeline_id].status = PipelineStatus.PAUSED
            logger.info(f"Pipeline {pipeline_id} paused")

    async def route_chunk(self, chunk: DataChunk) -> DataChunk:
        """Route a data chunk through its pipeline."""
        chunk.status = "in_transit"
        chunk.hops.append(f"hive-{uuid.uuid4().hex[:6]}")

        # Simulate delivery for each sink
        for _sink_id in chunk.sink_id.split(","):
            # In production, this would route through the actual data transport
            pass

        chunk.status = "delivered"
        chunk.delivered_at = datetime.now(timezone.utc).isoformat()

        # Update pipeline stats
        async with self._lock:
            if chunk.pipeline_id in self._pipelines:
                pipeline = self._pipelines[chunk.pipeline_id]
                pipeline.delivered_chunks += 1
                pipeline.total_chunks = max(pipeline.total_chunks, pipeline.delivered_chunks)

        await self.flow_monitor.record_chunk_status("delivered")
        logger.debug(f"Chunk {chunk.chunk_id} delivered via pipeline {chunk.pipeline_id}")
        return chunk

    async def fail_chunk(self, chunk_id: str, pipeline_id: str, reason: str = "") -> None:
        """Mark a chunk as failed."""
        async with self._lock:
            if pipeline_id in self._pipelines:
                self._pipelines[pipeline_id].failed_chunks += 1
        await self.flow_monitor.record_chunk_status("failed")
        logger.warning(f"Chunk {chunk_id} failed on pipeline {pipeline_id}: {reason}")

    async def get_pipeline(self, pipeline_id: str) -> Optional[DataPipeline]:
        """Get a pipeline by ID."""
        async with self._lock:
            return self._pipelines.get(pipeline_id)

    async def list_pipelines(self, status: Optional[PipelineStatus] = None) -> List[DataPipeline]:
        """List all pipelines, optionally filtered by status."""
        async with self._lock:
            pipelines = list(self._pipelines.values())
            if status:
                pipelines = [p for p in pipelines if p.status == status]
            return pipelines


# ---------------------------------------------------------------------------
# The HIVE — Main Coordinator
# ---------------------------------------------------------------------------


class Hive:
    """
    The HIVE — dedicated coordinator for data movement and swarm systems.

    The HIVE is ONE of the three bridges through Sentinel Station:
        - InfinityBridge: User context / human traffic
        - The Nexus: AI, Agent, and Bot movement and traffic
        - The HIVE (THIS): Data movement and swarm system coordination

    The HIVE provides a unified API surface for data operations:
    - Data source and sink registration
    - Data pipeline creation and management
    - Swarm coordination for distributed data processing
    - Flow monitoring with throughput and latency tracking
    - Data chunk routing with priority and replication
    - Cross-Hive event routing via Sentinel Station channels

    IMPORTANT: The HIVE is NOT for AI/Agent/Bot traffic (that is The Nexus).
    The HIVE is NOT for user traffic (that is InfinityBridge). The HIVE is
    specifically and exclusively for data movement and swarm coordination.
    """

    def __init__(self, db_path: str = HIVE_DB_PATH):
        self.node_id = f"hive-{uuid.uuid4().hex[:8]}"
        self.db_path = db_path
        self.flow_monitor = FlowMonitor(db_path)
        self.swarm_coordinator = SwarmCoordinator()
        self.pipeline_manager = PipelineManager(self.flow_monitor)
        self._sources: Dict[str, HiveDataSource] = {}
        self._sinks: Dict[str, HiveDataSink] = {}
        self._event_subscribers: Dict[str, Set[str]] = defaultdict(set)
        self._started_at = time.time()
        self._lock = asyncio.Lock()
        logger.info(f"HIVE initialized: {self.node_id}")

    # -- Data Source Management --

    async def register_source(
        self,
        name: str,
        data_type: str,
        pillar: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HiveDataSource:
        """Register a data source with the HIVE."""
        source = HiveDataSource(
            name=name,
            data_type=data_type,
            pillar=pillar,
            metadata=metadata or {},
        )
        async with self._lock:
            self._sources[source.source_id] = source
        logger.info(f"HIVE source registered: {name} ({source.source_id}) — {data_type}")
        return source

    async def update_source_status(
        self, source_id: str, status: str, throughput_mbps: float = 0.0
    ) -> None:
        """Update a data source's status and throughput."""
        async with self._lock:
            if source_id in self._sources:
                self._sources[source_id].status = status
                self._sources[source_id].throughput_mbps = throughput_mbps
                await self.flow_monitor.record_throughput(source_id, throughput_mbps)

    # -- Data Sink Management --

    async def register_sink(
        self,
        name: str,
        data_type: str,
        pillar: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HiveDataSink:
        """Register a data sink with the HIVE."""
        sink = HiveDataSink(
            name=name,
            data_type=data_type,
            pillar=pillar,
            metadata=metadata or {},
        )
        async with self._lock:
            self._sinks[sink.sink_id] = sink
        logger.info(f"HIVE sink registered: {name} ({sink.sink_id}) — {data_type}")
        return sink

    async def update_sink_status(
        self, sink_id: str, status: str, consumption_rate_mbps: float = 0.0
    ) -> None:
        """Update a data sink's status and consumption rate."""
        async with self._lock:
            if sink_id in self._sinks:
                self._sinks[sink_id].status = status
                self._sinks[sink_id].consumption_rate_mbps = consumption_rate_mbps

    # -- Pipeline Operations --

    async def create_pipeline(
        self,
        name: str,
        source_id: str,
        sink_ids: List[str],
        priority: DataPriority = DataPriority.NORMAL,
        replication_factor: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DataPipeline:
        """Create a data pipeline in the HIVE."""
        return await self.pipeline_manager.create_pipeline(
            name=name,
            source_id=source_id,
            sink_ids=sink_ids,
            priority=priority,
            replication_factor=replication_factor,
            metadata=metadata,
        )

    async def start_pipeline(self, pipeline_id: str) -> None:
        """Start a data pipeline."""
        await self.pipeline_manager.start_pipeline(pipeline_id)

    async def pause_pipeline(self, pipeline_id: str) -> None:
        """Pause a running data pipeline."""
        await self.pipeline_manager.pause_pipeline(pipeline_id)

    # -- Swarm Operations --

    async def create_swarm(
        self,
        name: str,
        purpose: str,
        data_type: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Swarm:
        """Create a data-processing swarm in the HIVE."""
        return await self.swarm_coordinator.create_swarm(
            name=name,
            purpose=purpose,
            data_type=data_type,
            metadata=metadata,
        )

    async def add_swarm_node(self, swarm_id: str, node: SwarmNode) -> None:
        """Add a processing node to a swarm."""
        await self.swarm_coordinator.add_node(swarm_id, node)

    async def remove_swarm_node(self, swarm_id: str, node_id: str) -> None:
        """Remove a processing node from a swarm."""
        await self.swarm_coordinator.remove_node(swarm_id, node_id)

    async def dissolve_swarm(self, swarm_id: str) -> None:
        """Dissolve a data-processing swarm."""
        await self.swarm_coordinator.dissolve_swarm(swarm_id)

    # -- Data Chunk Routing --

    async def route_data(
        self,
        pipeline_id: str,
        source_id: str,
        sink_id: str,
        size_bytes: int,
        priority: DataPriority = DataPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DataChunk:
        """Route a data chunk through the HIVE."""
        chunk = DataChunk(
            pipeline_id=pipeline_id,
            source_id=source_id,
            sink_id=sink_id,
            priority=priority,
            size_bytes=size_bytes,
            metadata=metadata or {},
        )
        # Compute checksum (placeholder — in production this would hash actual data)
        chunk.checksum = hashlib.sha256(f"{chunk.chunk_id}:{size_bytes}".encode()).hexdigest()[:16]

        await self.flow_monitor.record_chunk_status("pending")
        delivered_chunk = await self.pipeline_manager.route_chunk(chunk)
        logger.info(
            f"HIVE data routed: {chunk.chunk_id} ({size_bytes} bytes, {priority.value}) "
            f"from {source_id} → {sink_id}"
        )
        return delivered_chunk

    # -- Event Routing --

    async def emit_event(
        self,
        channel: str,
        source: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: DataPriority = DataPriority.NORMAL,
        correlation_id: Optional[str] = None,
    ) -> HiveEvent:
        """Emit a data-flow event through the HIVE."""
        event = HiveEvent(
            channel=channel,
            source=source,
            event_type=event_type,
            priority=priority,
            payload=payload or {},
            correlation_id=correlation_id,
        )
        logger.info(f"HIVE event: {event_type} on {channel} from {source}")
        return event

    async def subscribe_channel(self, channel: str, subscriber_id: str) -> None:
        """Subscribe to a HIVE data channel."""
        self._event_subscribers[channel].add(subscriber_id)
        logger.info(f"HIVE subscriber {subscriber_id} joined channel {channel}")

    async def unsubscribe_channel(self, channel: str, subscriber_id: str) -> None:
        """Unsubscribe from a HIVE data channel."""
        self._event_subscribers[channel].discard(subscriber_id)

    # -- Status and Health --

    async def get_status(self) -> Dict[str, Any]:
        """Get the comprehensive HIVE status."""
        flow_summary = await self.flow_monitor.get_summary()
        active_swarms = await self.swarm_coordinator.list_swarms(status=SwarmStatus.ACTIVE)
        active_pipelines = await self.pipeline_manager.list_pipelines(status=PipelineStatus.RUNNING)

        return {
            "hive_id": self.node_id,
            "bridge_type": "hive",
            "description": "Data movement and swarm system coordination",
            "uptime_seconds": round(time.time() - self._started_at, 1),
            "flow": flow_summary,
            "active_swarms": len(active_swarms),
            "active_pipelines": len(active_pipelines),
            "registered_sources": len(self._sources),
            "registered_sinks": len(self._sinks),
            "three_bridges": {
                "infinity_bridge": {
                    "name": "InfinityBridge",
                    "role": "User Context & Human Traffic",
                    "description": "User Context & Human Traffic (Light Bridge)",
                    "status": "see_infinity_bridge_status",
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
                    "status": "active",
                    "bridge_type": "hive",
                },
            },
            "data_types": list(set(s.data_type for s in self._sources.values())),
            "pillar_distribution": dict(
                defaultdict(
                    int,
                    {
                        s.pillar: sum(1 for src in self._sources.values() if src.pillar == s.pillar)
                        for s in self._sources.values()
                    },
                )
            )
            if self._sources
            else {},
            "sentinel_channels": [ch.value for ch in SentinelChannel],
        }

    async def get_health(self) -> HiveHealthSummary:
        """Get the HIVE health summary."""
        flow = await self.flow_monitor.get_summary()
        active_pipelines = await self.pipeline_manager.list_pipelines(status=PipelineStatus.RUNNING)
        active_swarms = await self.swarm_coordinator.list_swarms(status=SwarmStatus.ACTIVE)

        return HiveHealthSummary(
            total_sources=len(self._sources),
            total_sinks=len(self._sinks),
            active_pipelines=len(active_pipelines),
            active_swarms=len(active_swarms),
            pending_chunks=flow.get("chunks_pending", 0),
            delivered_chunks=flow.get("chunks_delivered", 0),
            failed_chunks=flow.get("chunks_failed", 0),
            total_throughput_mbps=flow.get("total_throughput_mbps", 0.0),
            avg_latency_ms=flow.get("avg_latency_ms", 0.0),
            status="healthy" if flow.get("chunks_failed", 0) == 0 else "degraded",
        )


# ---------------------------------------------------------------------------
# Singleton HIVE Instance
# ---------------------------------------------------------------------------

_hive_instance: Optional[Hive] = None


def get_hive() -> Hive:
    """Get or create the singleton HIVE instance."""
    global _hive_instance
    if _hive_instance is None:
        _hive_instance = Hive()
    return _hive_instance


# ---------------------------------------------------------------------------
# WebSocket Manager for Dashboard Streaming
# ---------------------------------------------------------------------------


class HiveWSManager:
    """WebSocket connection manager for HIVE dashboard streaming."""

    def __init__(self):
        self._connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"HIVE dashboard connected: {ws.client}")

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, event: HiveEvent) -> None:
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(event.model_dump_json())
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


_ws_manager = HiveWSManager()


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("HIVE API starting up")
    yield
    logger.info("HIVE API shutting down")


def create_hive_app() -> FastAPI:
    """Create the HIVE FastAPI application."""
    app = FastAPI(
        title="Tranc3 HIVE",
        description="The HIVE — Data Movement and Swarm System Coordination",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.get("/", tags=["hive"])
    async def hive_root():
        """HIVE root — system overview."""
        hive = get_hive()
        status = await hive.get_status()
        return {
            "system": "The HIVE",
            "bridge_type": "hive",
            "description": "Data movement and swarm system coordination",
            "version": "0.1.0",
            "three_bridges": status["three_bridges"],
            "status": status,
        }

    @app.get("/status", tags=["hive"])
    async def hive_status():
        """Get comprehensive HIVE status."""
        hive = get_hive()
        return await hive.get_status()

    @app.get("/health", tags=["hive"])
    async def hive_health():
        """Get HIVE health summary."""
        hive = get_hive()
        return (await hive.get_health()).model_dump()

    # -- Source endpoints --

    @app.post("/sources", tags=["sources"])
    async def register_source(
        name: str, data_type: str, pillar: str, metadata: Optional[str] = None
    ):
        """Register a data source with the HIVE."""
        hive = get_hive()
        meta = json.loads(metadata) if metadata else {}
        source = await hive.register_source(
            name=name, data_type=data_type, pillar=pillar, metadata=meta
        )
        return source.model_dump()

    @app.get("/sources", tags=["sources"])
    async def list_sources():
        """List all registered data sources."""
        hive = get_hive()
        return {sid: src.model_dump() for sid, src in hive._sources.items()}

    # -- Sink endpoints --

    @app.post("/sinks", tags=["sinks"])
    async def register_sink(name: str, data_type: str, pillar: str, metadata: Optional[str] = None):
        """Register a data sink with the HIVE."""
        hive = get_hive()
        meta = json.loads(metadata) if metadata else {}
        sink = await hive.register_sink(
            name=name, data_type=data_type, pillar=pillar, metadata=meta
        )
        return sink.model_dump()

    @app.get("/sinks", tags=["sinks"])
    async def list_sinks():
        """List all registered data sinks."""
        hive = get_hive()
        return {sid: sink.model_dump() for sid, sink in hive._sinks.items()}

    # -- Pipeline endpoints --

    @app.post("/pipelines", tags=["pipelines"])
    async def create_pipeline(
        name: str,
        source_id: str,
        sink_ids: str,
        priority: DataPriority = DataPriority.NORMAL,
        replication_factor: int = 1,
    ):
        """Create a data pipeline."""
        hive = get_hive()
        pipeline = await hive.create_pipeline(
            name=name,
            source_id=source_id,
            sink_ids=sink_ids.split(","),
            priority=priority,
            replication_factor=replication_factor,
        )
        return pipeline.model_dump()

    @app.post("/pipelines/{pipeline_id}/start", tags=["pipelines"])
    async def start_pipeline(pipeline_id: str):
        """Start a data pipeline."""
        hive = get_hive()
        await hive.start_pipeline(pipeline_id)
        return {"status": "started", "pipeline_id": pipeline_id}

    @app.post("/pipelines/{pipeline_id}/pause", tags=["pipelines"])
    async def pause_pipeline(pipeline_id: str):
        """Pause a running data pipeline."""
        hive = get_hive()
        await hive.pause_pipeline(pipeline_id)
        return {"status": "paused", "pipeline_id": pipeline_id}

    @app.get("/pipelines", tags=["pipelines"])
    async def list_pipelines(status: Optional[PipelineStatus] = None):
        """List all data pipelines."""
        hive = get_hive()
        pipelines = await hive.pipeline_manager.list_pipelines(status=status)
        return [p.model_dump() for p in pipelines]

    # -- Swarm endpoints --

    @app.post("/swarms", tags=["swarms"])
    async def create_swarm(name: str, purpose: str, data_type: str = ""):
        """Create a data-processing swarm."""
        hive = get_hive()
        swarm = await hive.create_swarm(name=name, purpose=purpose, data_type=data_type)
        return swarm.model_dump()

    @app.get("/swarms", tags=["swarms"])
    async def list_swarms(status: Optional[SwarmStatus] = None):
        """List all data-processing swarms."""
        hive = get_hive()
        swarms = await hive.swarm_coordinator.list_swarms(status=status)
        return [s.model_dump() for s in swarms]

    @app.post("/swarms/{swarm_id}/nodes", tags=["swarms"])
    async def add_swarm_node(
        swarm_id: str, node_id: str, role: str = "worker", capacity: float = 1.0
    ):
        """Add a processing node to a swarm."""
        hive = get_hive()
        node = SwarmNode(node_id=node_id, role=role, capacity=capacity)
        await hive.add_swarm_node(swarm_id, node)
        return {"status": "added", "swarm_id": swarm_id, "node_id": node_id}

    @app.delete("/swarms/{swarm_id}/nodes/{node_id}", tags=["swarms"])
    async def remove_swarm_node(swarm_id: str, node_id: str):
        """Remove a processing node from a swarm."""
        hive = get_hive()
        await hive.remove_swarm_node(swarm_id, node_id)
        return {"status": "removed", "swarm_id": swarm_id, "node_id": node_id}

    @app.delete("/swarms/{swarm_id}", tags=["swarms"])
    async def dissolve_swarm(swarm_id: str):
        """Dissolve a data-processing swarm."""
        hive = get_hive()
        await hive.dissolve_swarm(swarm_id)
        return {"status": "dissolved", "swarm_id": swarm_id}

    # -- Data routing endpoint --

    @app.post("/route", tags=["routing"])
    async def route_data(
        pipeline_id: str,
        source_id: str,
        sink_id: str,
        size_bytes: int,
        priority: DataPriority = DataPriority.NORMAL,
    ):
        """Route a data chunk through the HIVE."""
        hive = get_hive()
        chunk = await hive.route_data(
            pipeline_id=pipeline_id,
            source_id=source_id,
            sink_id=sink_id,
            size_bytes=size_bytes,
            priority=priority,
        )
        return chunk.model_dump()

    # -- Flow monitoring endpoint --

    @app.get("/flow", tags=["monitoring"])
    async def flow_summary():
        """Get flow monitoring summary."""
        hive = get_hive()
        return await hive.flow_monitor.get_summary()

    # -- WebSocket endpoint --

    @app.websocket("/ws")
    async def hive_websocket(ws: WebSocket):
        """WebSocket endpoint for live HIVE event streaming."""
        await _ws_manager.connect(ws)
        try:
            while True:
                _ = await ws.receive_text()
                # Echo back for keepalive
                await ws.send_text(json.dumps({"type": "pong", "hive_id": get_hive().node_id}))
        except WebSocketDisconnect:
            _ws_manager.disconnect(ws)

    return app
