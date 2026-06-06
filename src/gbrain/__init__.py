"""
GBrain — Graph-based AI reasoning pipeline (Luminous subsystem).

Provides AgentInteraction and pipeline orchestration.
"""

from .pipeline import AgentInteraction, get_pipeline

__all__ = ["AgentInteraction", "get_pipeline"]
