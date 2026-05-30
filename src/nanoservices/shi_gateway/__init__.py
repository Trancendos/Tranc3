"""
SHI — Self-Hosted Inference Gateway Package
============================================
Zero-cost local inference using Ollama, vLLM, or llama.cpp.
Eliminates API costs and third-party uptime reliance.
"""

from .shi_gateway import (
    InferenceBackend,
    InferenceMetrics,
    InferenceRequest,
    InferenceResponse,
    ModelInfo,
    ModelStatus,
    OllamaBackend,
    SHIGateway,
)

__all__ = [
    "InferenceBackend",
    "ModelStatus",
    "ModelInfo",
    "InferenceRequest",
    "InferenceResponse",
    "InferenceMetrics",
    "OllamaBackend",
    "SHIGateway",
]
