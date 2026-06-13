# src/neural/__init__.py
"""Neural & Intelligence layer for Tranc3 zero-cost nanoservice platform."""

from src.neural.attention_router import AttentionRouter, ServiceAttention
from src.neural.collective_memory import CollectiveMemory, MemoryEntry
from src.neural.meta_learner import MetaLearner, TaskPrototype
from src.neural.neural_mesh import MeshNode, NeuralMesh

__all__ = [
    "NeuralMesh",
    "MeshNode",
    "CollectiveMemory",
    "MemoryEntry",
    "MetaLearner",
    "TaskPrototype",
    "AttentionRouter",
    "ServiceAttention",
]
