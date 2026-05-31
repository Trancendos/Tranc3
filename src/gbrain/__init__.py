"""GBrain — lightweight in-process knowledge ingestion pipeline.

The Library (Zimik) consumes agent interactions for later consolidation into
the knowledge graph served by the ``gbrain-bridge`` worker. This package
provides a fire-and-forget, SQLite-backed pipeline that api.py uses to capture
chat interactions without blocking the request path.
"""

from __future__ import annotations

from src.gbrain.pipeline import AgentInteraction, GBrainPipeline, get_pipeline

__all__ = ["AgentInteraction", "GBrainPipeline", "get_pipeline"]
