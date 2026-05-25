"""
Tests for The HIVE — Data Movement and Swarm System Coordination
=================================================================
Comprehensive test suite covering:
- FlowMonitor (throughput, latency, chunk tracking)
- SwarmCoordinator (swarm lifecycle, node management, task progress)
- PipelineManager (pipeline CRUD, chunk routing)
- The HIVE (full integration — data movement and swarm coordination)
- FastAPI endpoints

The HIVE is ONE of the three bridges through Sentinel Station:
    Bridge 1 — InfinityBridge : User context / human traffic (Light bridges)
    Bridge 2 — The Nexus      : AI, Agent, and Bot movement and traffic
    Bridge 3 — The HIVE (THIS): Data movement and swarm system coordination
"""

import os
import sys
import tempfile

import pytest

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Dimensional.hive.hive_core import (
    DataChunk,
    DataPriority,
    FlowMonitor,
    Hive,
    HiveDataSink,
    HiveDataSource,
    HiveEvent,
    HiveHealthSummary,
    PipelineManager,
    PipelineStatus,
    Swarm,
    SwarmCoordinator,
    SwarmNode,
    SwarmStatus,
    create_hive_app,
    get_hive,
)


# ---------------------------------------------------------------------------
# FlowMonitor Tests
# ---------------------------------------------------------------------------


class TestFlowMonitor:
    """Tests for the HIVE flow monitoring system."""

    def setup_method(self):
        self.db_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.db_dir, "test_hive.db")
        self.monitor = FlowMonitor(db_path=self.db_path)

    @pytest.mark.asyncio
    async def test_record_throughput(self):
        """Throughput samples are recorded and averaged."""
        await self.monitor.record_throughput("pipe-1", 100.0)
        await self.monitor.record_throughput("pipe-1", 200.0)
        avg = await self.monitor.get_throughput("pipe-1")
        assert avg == pytest.approx(150.0)

    @pytest.mark.asyncio
    async def test_record_latency(self):
        """Latency samples are recorded and averaged."""
        await self.monitor.record_latency("pipe-1", 10.0)
        await self.monitor.record_latency("pipe-1", 20.0)
        avg = await self.monitor.get_latency("pipe-1")
        assert avg == pytest.approx(15.0)

    @pytest.mark.asyncio
    async def test_chunk_status_tracking(self):
        """Chunk status changes are tracked correctly."""
        await self.monitor.record_chunk_status("pending")
        await self.monitor.record_chunk_status("pending")
        await self.monitor.record_chunk_status("delivered")
        await self.monitor.record_chunk_status("failed")
        summary = await self.monitor.get_summary()
        assert summary["chunks_delivered"] == 1
        assert summary["chunks_failed"] == 1

    @pytest.mark.asyncio
    async def test_no_throughput_for_unknown_pipeline(self):
        """Unknown pipeline returns 0 throughput."""
        avg = await self.monitor.get_throughput("nonexistent")
        assert avg == 0.0

    @pytest.mark.asyncio
    async def test_no_latency_for_unknown_pipeline(self):
        """Unknown pipeline returns 0 latency."""
        avg = await self.monitor.get_latency("nonexistent")
        assert avg == 0.0

    @pytest.mark.asyncio
    async def test_summary_empty(self):
        """Summary returns zeros when no data recorded."""
        summary = await self.monitor.get_summary()
        assert summary["total_throughput_mbps"] == 0.0
        assert summary["avg_latency_ms"] == 0.0
        assert summary["chunks_pending"] == 0


# ---------------------------------------------------------------------------
# SwarmCoordinator Tests
# ---------------------------------------------------------------------------


class TestSwarmCoordinator:
    """Tests for the HIVE swarm coordination system."""

    def setup_method(self):
        self.coordinator = SwarmCoordinator()

    @pytest.mark.asyncio
    async def test_create_swarm(self):
        """Swarm can be created with correct defaults."""
        swarm = await self.coordinator.create_swarm(
            name="etl-pipeline",
            purpose="ETL",
            data_type="dataset",
        )
        assert swarm.name == "etl-pipeline"
        assert swarm.purpose == "ETL"
        assert swarm.status == SwarmStatus.FORMING
        assert swarm.swarm_id.startswith("swarm-")

    @pytest.mark.asyncio
    async def test_add_node_activates_swarm(self):
        """Adding first node activates a forming swarm."""
        swarm = await self.coordinator.create_swarm(name="test", purpose="test")
        node = SwarmNode(node_id="node-1", role="worker")
        await self.coordinator.add_node(swarm.swarm_id, node)
        updated = await self.coordinator.get_swarm(swarm.swarm_id)
        assert updated.status == SwarmStatus.ACTIVE
        assert len(updated.nodes) == 1

    @pytest.mark.asyncio
    async def test_add_node_unknown_swarm(self):
        """Adding a node to a nonexistent swarm raises ValueError."""
        node = SwarmNode(node_id="node-1")
        with pytest.raises(ValueError, match="not found"):
            await self.coordinator.add_node("swarm-nonexistent", node)

    @pytest.mark.asyncio
    async def test_remove_node_drains_swarm(self):
        """Removing all nodes drains a swarm."""
        swarm = await self.coordinator.create_swarm(name="test", purpose="test")
        node = SwarmNode(node_id="node-1")
        await self.coordinator.add_node(swarm.swarm_id, node)
        await self.coordinator.remove_node(swarm.swarm_id, "node-1")
        updated = await self.coordinator.get_swarm(swarm.swarm_id)
        assert updated.status == SwarmStatus.DRAINING
        assert len(updated.nodes) == 0

    @pytest.mark.asyncio
    async def test_update_task_progress(self):
        """Task progress updates correctly on swarm nodes."""
        swarm = await self.coordinator.create_swarm(name="test", purpose="test", data_type="data")
        node = SwarmNode(node_id="node-1", current_load=10.0)
        await self.coordinator.add_node(swarm.swarm_id, node)
        await self.coordinator.update_task_progress(swarm.swarm_id, "node-1", tasks_completed=5)
        updated = await self.coordinator.get_swarm(swarm.swarm_id)
        assert updated.completed_tasks == 5

    @pytest.mark.asyncio
    async def test_list_swarms(self):
        """List swarms returns all swarms."""
        await self.coordinator.create_swarm(name="swarm-1", purpose="test")
        await self.coordinator.create_swarm(name="swarm-2", purpose="test")
        all_swarms = await self.coordinator.list_swarms()
        assert len(all_swarms) == 2

    @pytest.mark.asyncio
    async def test_list_swarms_by_status(self):
        """List swarms can filter by status."""
        _swarm = await self.coordinator.create_swarm(name="forming", purpose="test")
        # swarm is FORMING, not ACTIVE
        forming = await self.coordinator.list_swarms(status=SwarmStatus.FORMING)
        active = await self.coordinator.list_swarms(status=SwarmStatus.ACTIVE)
        assert len(forming) == 1
        assert len(active) == 0

    @pytest.mark.asyncio
    async def test_dissolve_swarm(self):
        """Dissolving a swarm removes it."""
        swarm = await self.coordinator.create_swarm(name="test", purpose="test")
        await self.coordinator.dissolve_swarm(swarm.swarm_id)
        result = await self.coordinator.get_swarm(swarm.swarm_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_swarm_completion(self):
        """Swarm completes when all tasks are done."""
        swarm = await self.coordinator.create_swarm(name="test", purpose="test")
        swarm.total_tasks = 5
        node = SwarmNode(node_id="node-1", current_load=5.0)
        await self.coordinator.add_node(swarm.swarm_id, node)
        await self.coordinator.update_task_progress(swarm.swarm_id, "node-1", tasks_completed=5)
        updated = await self.coordinator.get_swarm(swarm.swarm_id)
        assert updated.status == SwarmStatus.COMPLETED


# ---------------------------------------------------------------------------
# PipelineManager Tests
# ---------------------------------------------------------------------------


class TestPipelineManager:
    """Tests for the HIVE pipeline management system."""

    def setup_method(self):
        self.db_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.db_dir, "test_hive.db")
        self.monitor = FlowMonitor(db_path=self.db_path)
        self.manager = PipelineManager(self.monitor)

    @pytest.mark.asyncio
    async def test_create_pipeline(self):
        """Pipeline can be created with correct defaults."""
        pipeline = await self.manager.create_pipeline(
            name="data-sync",
            source_id="src-1",
            sink_ids=["sink-1", "sink-2"],
        )
        assert pipeline.name == "data-sync"
        assert pipeline.status == PipelineStatus.PENDING
        assert pipeline.pipeline_id.startswith("pipe-")

    @pytest.mark.asyncio
    async def test_start_pipeline(self):
        """Pipeline can be started."""
        pipeline = await self.manager.create_pipeline(
            name="test", source_id="src-1", sink_ids=["sink-1"]
        )
        await self.manager.start_pipeline(pipeline.pipeline_id)
        updated = await self.manager.get_pipeline(pipeline.pipeline_id)
        assert updated.status == PipelineStatus.RUNNING

    @pytest.mark.asyncio
    async def test_pause_pipeline(self):
        """Running pipeline can be paused."""
        pipeline = await self.manager.create_pipeline(
            name="test", source_id="src-1", sink_ids=["sink-1"]
        )
        await self.manager.start_pipeline(pipeline.pipeline_id)
        await self.manager.pause_pipeline(pipeline.pipeline_id)
        updated = await self.manager.get_pipeline(pipeline.pipeline_id)
        assert updated.status == PipelineStatus.PAUSED

    @pytest.mark.asyncio
    async def test_pause_non_running_pipeline(self):
        """Pausing a non-running pipeline raises ValueError."""
        pipeline = await self.manager.create_pipeline(
            name="test", source_id="src-1", sink_ids=["sink-1"]
        )
        with pytest.raises(ValueError, match="not running"):
            await self.manager.pause_pipeline(pipeline.pipeline_id)

    @pytest.mark.asyncio
    async def test_start_unknown_pipeline(self):
        """Starting unknown pipeline raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            await self.manager.start_pipeline("pipe-nonexistent")

    @pytest.mark.asyncio
    async def test_list_pipelines(self):
        """List pipelines returns all pipelines."""
        await self.manager.create_pipeline(name="p1", source_id="s1", sink_ids=["sk1"])
        await self.manager.create_pipeline(name="p2", source_id="s2", sink_ids=["sk2"])
        all_pipelines = await self.manager.list_pipelines()
        assert len(all_pipelines) == 2

    @pytest.mark.asyncio
    async def test_list_pipelines_by_status(self):
        """List pipelines can filter by status."""
        p1 = await self.manager.create_pipeline(name="p1", source_id="s1", sink_ids=["sk1"])
        await self.manager.start_pipeline(p1.pipeline_id)
        running = await self.manager.list_pipelines(status=PipelineStatus.RUNNING)
        pending = await self.manager.list_pipelines(status=PipelineStatus.PENDING)
        assert len(running) == 1
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_replication_factor_capped(self):
        """Replication factor is capped at HIVE_MAX_REPLICATION."""
        pipeline = await self.manager.create_pipeline(
            name="test", source_id="src-1", sink_ids=["sink-1"],
            replication_factor=100,
        )
        assert pipeline.replication_factor <= 5

    @pytest.mark.asyncio
    async def test_route_chunk(self):
        """Chunk routing delivers data and updates stats."""
        pipeline = await self.manager.create_pipeline(
            name="test", source_id="src-1", sink_ids=["sink-1"]
        )
        chunk = DataChunk(
            pipeline_id=pipeline.pipeline_id,
            source_id="src-1",
            sink_id="sink-1",
            size_bytes=1024,
        )
        delivered = await self.manager.route_chunk(chunk)
        assert delivered.status == "delivered"
        assert delivered.delivered_at is not None
        updated_pipeline = await self.manager.get_pipeline(pipeline.pipeline_id)
        assert updated_pipeline.delivered_chunks == 1


# ---------------------------------------------------------------------------
# HIVE Integration Tests
# ---------------------------------------------------------------------------


class TestHiveIntegration:
    """Tests for the full HIVE integration — data movement and swarm coordination."""

    def setup_method(self):
        self.db_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.db_dir, "test_hive.db")
        self.hive = Hive(db_path=self.db_path)

    @pytest.mark.asyncio
    async def test_register_source(self):
        """Data sources can be registered with the HIVE."""
        source = await self.hive.register_source(
            name="model-weights",
            data_type="model_weights",
            pillar="ai",
        )
        assert source.name == "model-weights"
        assert source.data_type == "model_weights"
        assert source.source_id.startswith("src-")

    @pytest.mark.asyncio
    async def test_register_sink(self):
        """Data sinks can be registered with the HIVE."""
        sink = await self.hive.register_sink(
            name="training-cluster",
            data_type="dataset",
            pillar="ai",
        )
        assert sink.name == "training-cluster"
        assert sink.data_type == "dataset"
        assert sink.sink_id.startswith("sink-")

    @pytest.mark.asyncio
    async def test_create_pipeline_via_hive(self):
        """Pipelines can be created through the HIVE."""
        source = await self.hive.register_source("src-1", "dataset", "ai")
        sink = await self.hive.register_sink("sink-1", "dataset", "ai")
        pipeline = await self.hive.create_pipeline(
            name="data-feed",
            source_id=source.source_id,
            sink_ids=[sink.sink_id],
        )
        assert pipeline.name == "data-feed"
        assert pipeline.status == PipelineStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_swarm_via_hive(self):
        """Swarms can be created through the HIVE."""
        swarm = await self.hive.create_swarm(
            name="etl-workers",
            purpose="ETL",
            data_type="dataset",
        )
        assert swarm.name == "etl-workers"
        assert swarm.status == SwarmStatus.FORMING

    @pytest.mark.asyncio
    async def test_route_data(self):
        """Data can be routed through the HIVE."""
        source = await self.hive.register_source("src-1", "dataset", "ai")
        sink = await self.hive.register_sink("sink-1", "dataset", "ai")
        pipeline = await self.hive.create_pipeline(
            name="test-pipe",
            source_id=source.source_id,
            sink_ids=[sink.sink_id],
        )
        chunk = await self.hive.route_data(
            pipeline_id=pipeline.pipeline_id,
            source_id=source.source_id,
            sink_id=sink.sink_id,
            size_bytes=4096,
            priority=DataPriority.HIGH,
        )
        assert chunk.status == "delivered"
        assert chunk.size_bytes == 4096
        assert chunk.priority == DataPriority.HIGH
        assert chunk.checksum != ""

    @pytest.mark.asyncio
    async def test_swarm_node_lifecycle(self):
        """Swarm nodes can be added and removed through the HIVE."""
        swarm = await self.hive.create_swarm("test", "processing")
        node = SwarmNode(node_id="worker-1", role="worker", capacity=2.0)
        await self.hive.add_swarm_node(swarm.swarm_id, node)
        updated = await self.hive.swarm_coordinator.get_swarm(swarm.swarm_id)
        assert updated.status == SwarmStatus.ACTIVE
        assert len(updated.nodes) == 1

        await self.hive.remove_swarm_node(swarm.swarm_id, "worker-1")
        updated = await self.hive.swarm_coordinator.get_swarm(swarm.swarm_id)
        assert updated.status == SwarmStatus.DRAINING

    @pytest.mark.asyncio
    async def test_dissolve_swarm(self):
        """Swarms can be dissolved through the HIVE."""
        swarm = await self.hive.create_swarm("test", "processing")
        await self.hive.dissolve_swarm(swarm.swarm_id)
        result = await self.hive.swarm_coordinator.get_swarm(swarm.swarm_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_emit_event(self):
        """HIVE events can be emitted."""
        event = await self.hive.emit_event(
            channel="HIVE",
            source="test-source",
            event_type="data_transfer_complete",
            payload={"bytes": 1024},
        )
        assert event.event_id.startswith("hevt-")
        assert event.event_type == "data_transfer_complete"

    @pytest.mark.asyncio
    async def test_subscribe_channel(self):
        """Subscribers can join HIVE channels."""
        await self.hive.subscribe_channel("HIVE", "subscriber-1")
        assert "subscriber-1" in self.hive._event_subscribers["HIVE"]
        await self.hive.unsubscribe_channel("HIVE", "subscriber-1")
        assert "subscriber-1" not in self.hive._event_subscribers["HIVE"]

    @pytest.mark.asyncio
    async def test_get_status(self):
        """HIVE status returns comprehensive information."""
        status = await self.hive.get_status()
        assert status["bridge_type"] == "hive"
        assert status["description"] == "Data movement and swarm system coordination"
        assert "three_bridges" in status
        assert status["three_bridges"]["hive"]["bridge_type"] == "hive"
        assert status["three_bridges"]["hive"]["status"] == "active"
        assert status["three_bridges"]["nexus"]["bridge_type"] == "nexus"
        assert status["three_bridges"]["infinity_bridge"]["bridge_type"] == "infinity"

    @pytest.mark.asyncio
    async def test_get_health(self):
        """HIVE health summary is returned correctly."""
        health = await self.hive.get_health()
        assert isinstance(health, HiveHealthSummary)
        assert health.status == "healthy"

    @pytest.mark.asyncio
    async def test_update_source_status(self):
        """Source status and throughput can be updated."""
        source = await self.hive.register_source("src-1", "dataset", "ai")
        await self.hive.update_source_status(source.source_id, "active", 50.0)
        assert self.hive._sources[source.source_id].status == "active"
        assert self.hive._sources[source.source_id].throughput_mbps == 50.0

    @pytest.mark.asyncio
    async def test_update_sink_status(self):
        """Sink status and consumption rate can be updated."""
        sink = await self.hive.register_sink("sink-1", "dataset", "ai")
        await self.hive.update_sink_status(sink.sink_id, "active", 30.0)
        assert self.hive._sinks[sink.sink_id].status == "active"
        assert self.hive._sinks[sink.sink_id].consumption_rate_mbps == 30.0


# ---------------------------------------------------------------------------
# HIVE Singleton Tests
# ---------------------------------------------------------------------------


class TestHiveSingleton:
    """Tests for the HIVE singleton."""

    def test_get_hive_returns_hive_instance(self):
        """get_hive returns a Hive instance."""
        # Reset singleton
        import Dimensional.hive.hive_core as _hc
        _hc._hive_instance = None
        hive = get_hive()
        assert isinstance(hive, Hive)
        _hc._hive_instance = None

    def test_get_hive_singleton(self):
        """get_hive returns the same instance on repeated calls."""
        import Dimensional.hive.hive_core as _hc
        _hc._hive_instance = None
        h1 = get_hive()
        h2 = get_hive()
        assert h1 is h2
        _hc._hive_instance = None


# ---------------------------------------------------------------------------
# HIVE Data Model Tests
# ---------------------------------------------------------------------------


class TestHiveDataModels:
    """Tests for HIVE data models."""

    def test_data_priority_enum(self):
        """DataPriority has all expected values."""
        assert DataPriority.CRITICAL.value == "critical"
        assert DataPriority.HIGH.value == "high"
        assert DataPriority.NORMAL.value == "normal"
        assert DataPriority.LOW.value == "low"
        assert DataPriority.BACKGROUND.value == "background"

    def test_swarm_status_enum(self):
        """SwarmStatus has all expected values."""
        assert SwarmStatus.FORMING.value == "forming"
        assert SwarmStatus.ACTIVE.value == "active"
        assert SwarmStatus.SCALING.value == "scaling"
        assert SwarmStatus.DRAINING.value == "draining"
        assert SwarmStatus.COMPLETED.value == "completed"
        assert SwarmStatus.FAILED.value == "failed"

    def test_pipeline_status_enum(self):
        """PipelineStatus has all expected values."""
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.RUNNING.value == "running"
        assert PipelineStatus.PAUSED.value == "paused"
        assert PipelineStatus.COMPLETED.value == "completed"
        assert PipelineStatus.FAILED.value == "failed"

    def test_hive_data_source_defaults(self):
        """HiveDataSource has correct defaults."""
        source = HiveDataSource(name="test", data_type="dataset", pillar="ai")
        assert source.source_id.startswith("src-")
        assert source.throughput_mbps == 0.0
        assert source.status == "unknown"

    def test_hive_data_sink_defaults(self):
        """HiveDataSink has correct defaults."""
        sink = HiveDataSink(name="test", data_type="dataset", pillar="ai")
        assert sink.sink_id.startswith("sink-")
        assert sink.consumption_rate_mbps == 0.0
        assert sink.status == "unknown"

    def test_data_chunk_defaults(self):
        """DataChunk has correct defaults."""
        chunk = DataChunk(pipeline_id="pipe-1", source_id="src-1", sink_id="sink-1")
        assert chunk.chunk_id.startswith("chk-")
        assert chunk.priority == DataPriority.NORMAL
        assert chunk.status == "pending"

    def test_swarm_node_defaults(self):
        """SwarmNode has correct defaults."""
        node = SwarmNode(node_id="node-1")
        assert node.role == "worker"
        assert node.capacity == 1.0
        assert node.current_load == 0.0

    def test_swarm_defaults(self):
        """Swarm has correct defaults."""
        swarm = Swarm(name="test", purpose="ETL")
        assert swarm.swarm_id.startswith("swarm-")
        assert swarm.status == SwarmStatus.FORMING
        assert swarm.nodes == []

    def test_hive_event_defaults(self):
        """HiveEvent has correct defaults."""
        event = HiveEvent(channel="HIVE", source="test", event_type="test")
        assert event.event_id.startswith("hevt-")
        assert event.priority == DataPriority.NORMAL

    def test_hive_health_summary_defaults(self):
        """HiveHealthSummary has correct defaults."""
        summary = HiveHealthSummary()
        assert summary.total_sources == 0
        assert summary.total_sinks == 0
        assert summary.active_pipelines == 0
        assert summary.active_swarms == 0
        assert summary.status == "unknown"


# ---------------------------------------------------------------------------
# HIVE FastAPI App Tests
# ---------------------------------------------------------------------------


class TestHiveApp:
    """Tests for the HIVE FastAPI application."""

    def test_create_hive_app(self):
        """HIVE app can be created."""
        app = create_hive_app()
        assert app.title == "Tranc3 HIVE"

    @pytest.mark.asyncio
    async def test_hive_root_endpoint(self):
        """HIVE root endpoint returns system info."""
        from httpx import AsyncClient, ASGITransport
        app = create_hive_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/")
            assert response.status_code == 200
            data = response.json()
            assert data["system"] == "The HIVE"
            assert data["bridge_type"] == "hive"
            assert "three_bridges" in data

    @pytest.mark.asyncio
    async def test_hive_status_endpoint(self):
        """HIVE status endpoint returns comprehensive status."""
        from httpx import AsyncClient, ASGITransport
        app = create_hive_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/status")
            assert response.status_code == 200
            data = response.json()
            assert data["bridge_type"] == "hive"

    @pytest.mark.asyncio
    async def test_hive_health_endpoint(self):
        """HIVE health endpoint returns health summary."""
        from httpx import AsyncClient, ASGITransport
        app = create_hive_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
