"""Cellular automata for service health propagation.

CA models spread of failure states across the platform service graph.
Each service is a cell; its state is influenced by its neighbours.
This predicts cascading failures before they propagate.
"""
from .automata import ServiceHealthCA

__all__ = ["ServiceHealthCA"]
