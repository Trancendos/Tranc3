"""
TRANC3 Worker Infrastructure — self-owned, zero-external-dependency compute.

No CF Workers AI. No Anthropic. No OpenAI. Pure TRANC3.

Components:
    pool.py             — Redis-backed asyncio task queue + worker pool manager
    inference_worker.py — Single worker process: loads Tranc3Engine, drains tasks
    bot_registry.py     — Bot registry: typed bots for inference, embedding, emotion
"""

from .bot_registry import BotRegistry, EmbeddingBot, EmotionBot, InferenceBot
from .pool import JobResult, JobSpec, JobStatus, WorkerPool

__all__ = [
    "WorkerPool",
    "JobSpec",
    "JobResult",
    "JobStatus",
    "BotRegistry",
    "InferenceBot",
    "EmbeddingBot",
    "EmotionBot",
]
