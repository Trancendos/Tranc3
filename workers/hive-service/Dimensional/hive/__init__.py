"""
The HIVE — Data Movement and Swarm System Coordination
========================================================
The HIVE is one of the three bridges that route traffic through Sentinel Station:

    Bridge 1 — InfinityBridge : User context / human traffic (Light bridges)
    Bridge 2 — The Nexus      : AI, Agent, and Bot movement and traffic
    Bridge 3 — The HIVE       : Data movement and swarm system coordination

IMPORTANT: The HIVE ≠ Nexus ≠ InfinityBridge. Each bridge handles a specific
type of traffic through Sentinel Station:
    - InfinityBridge: Users and human context
    - Nexus: AI, Agent, and Bot traffic ONLY
    - HIVE: Data movement and swarm coordination ONLY

The Dimensional package provides core/shared services that all three bridges
can use, but Dimensional is a separate concept from any of the bridges.
"""

from Dimensional.hive.hive_core import (  # noqa: I001
    DataChunk,
    DataPipeline,
    DataPriority,
    FlowMonitor,
    Hive,
    HiveDataSink,
    HiveDataSource,
    HiveEvent,
    HiveHealthSummary,
    HiveWSManager,
    PipelineManager,
    PipelineStatus,
    Swarm,
    SwarmCoordinator,
    SwarmNode,
    SwarmStatus,
    create_hive_app,
    get_hive,
)
from Dimensional.hive.sentinel_bridge import (
    HiveSentinelBridge,
    get_bridge,
)

__all__ = [
    "Hive",
    "DataChunk",
    "DataPipeline",
    "DataPriority",
    "HiveDataSink",
    "HiveDataSource",
    "HiveEvent",
    "HiveHealthSummary",
    "HiveWSManager",
    "PipelineManager",
    "PipelineStatus",
    "Swarm",
    "SwarmCoordinator",
    "SwarmNode",
    "SwarmStatus",
    "FlowMonitor",
    "HiveSentinelBridge",
    "create_hive_app",
    "get_hive",
    "get_bridge",
]
