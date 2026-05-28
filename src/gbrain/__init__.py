# FID: TRANC3-GBRAIN-001 | Version: 1.0.0 | Module: gbrain
"""
src/gbrain — Integration layer between Tranc3 agents and The Library (GBrain).

Exports the high-level pipeline API used by API routes and the event bus.
"""
from src.gbrain.client import GBrainClient
from src.gbrain.pipeline import AgentInteraction, GBrainIngestionPipeline

__all__ = ["GBrainClient", "AgentInteraction", "GBrainIngestionPipeline"]
