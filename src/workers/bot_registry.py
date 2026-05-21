# src/workers/bot_registry.py
# TRANC3 Bot Registry — typed bots built on the worker pool.
#
# Bots are thin, named wrappers around WorkerPool jobs.
# They give calling code a clean API:
#
#   registry = BotRegistry()
#   await registry.start()
#
#   gen_bot = registry.get("generate")
#   result  = await gen_bot.run(prompt="Hello world", personality="dorris-fontaine")
#
# Architecture:
#   BotRegistry      — manages bot lifecycle, shares one WorkerPool
#   Bot (base)       — async run(**kwargs) → dict, wraps a JobSpec
#   InferenceBot     — JobType.GENERATE
#   EmbeddingBot     — JobType.EMBED
#   EmotionBot       — JobType.EMOTION
#   TokenizeBot      — JobType.TOKENIZE
#   ConsciousnessBot — JobType.CONSCIOUSNESS
#   PersonalityBot   — JobType.PERSONALITY
#   PredictBot       — JobType.PREDICT

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from src.workers.pool import JobResult, JobSpec, JobType, WorkerPool, get_pool

logger = logging.getLogger(__name__)


# ─── Base Bot ─────────────────────────────────────────────────────────────────

class Bot(ABC):
    """Abstract base class for all TRANC3 worker bots."""

    name: str = "bot"
    job_type: str = ""
    timeout: float = 30.0

    def __init__(self, pool: WorkerPool):
        self._pool = pool

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Execute this bot with the given keyword arguments."""
        payload = self._build_payload(**kwargs)
        job     = JobSpec(job_type=self.job_type, payload=payload)
        result  = await self._pool.submit_and_wait(job, timeout=self.timeout)
        return self._unwrap(result)

    async def submit(self, **kwargs) -> str:
        """Submit without waiting. Returns job_id."""
        payload = self._build_payload(**kwargs)
        job     = JobSpec(job_type=self.job_type, payload=payload)
        return await self._pool.submit(job)

    @abstractmethod
    def _build_payload(self, **kwargs) -> Dict[str, Any]:
        """Convert keyword arguments into the job payload dict."""
        ...

    def _unwrap(self, result: JobResult) -> Dict[str, Any]:
        if result.result:
            return result.result
        return {
            "error":    result.error or "unknown error",
            "status":   result.status,
            "job_id":   result.job_id,
            "duration": result.duration_ms,
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} job_type={self.job_type}>"


# ─── Concrete Bots ────────────────────────────────────────────────────────────

class InferenceBot(Bot):
    """
    Text generation / chat bot.

    Usage:
        result = await bot.run(
            prompt="What is finance?",
            personality="dorris-fontaine",
            max_tokens=512,
            temperature=0.7,
        )
        print(result["response"])
    """
    name     = "generate"
    job_type = JobType.GENERATE
    timeout  = 60.0

    def _build_payload(self, **kw) -> dict:
        return {
            "prompt":       kw.get("prompt", ""),
            "personality":  kw.get("personality", "tranc3-base"),
            "system_prompt":kw.get("system_prompt"),
            "max_tokens":   kw.get("max_tokens", 256),
            "temperature":  kw.get("temperature", 0.8),
            "top_p":        kw.get("top_p", 0.9),
        }


class EmbeddingBot(Bot):
    """
    Vector embedding bot.

    Usage:
        result = await bot.run(text="Hello world", pooling="mean")
        vec = result["embedding"]   # List[float]
    """
    name     = "embed"
    job_type = JobType.EMBED
    timeout  = 10.0

    def _build_payload(self, **kw) -> dict:
        return {
            "text":    kw.get("text", ""),
            "pooling": kw.get("pooling", "mean"),  # mean | cls | max
            "dims":    kw.get("dims", 256),
        }


class EmotionBot(Bot):
    """
    Emotion detection bot.

    Usage:
        result = await bot.run(text="I am so excited!")
        print(result["dominant"])  # "joy"
        print(result["scores"])    # {"joy": 0.72, "sadness": 0.05, ...}
    """
    name     = "emotion"
    job_type = JobType.EMOTION
    timeout  = 15.0

    def _build_payload(self, **kw) -> dict:
        return {"text": kw.get("text", "")}


class TokenizeBot(Bot):
    """
    Tokenization bot.

    Usage:
        enc = await bot.run(action="encode", text="Hello world")
        dec = await bot.run(action="decode", ids=[1, 2, 3])
    """
    name     = "tokenize"
    job_type = JobType.TOKENIZE
    timeout  = 5.0

    def _build_payload(self, **kw) -> dict:
        return {
            "action":        kw.get("action", "encode"),
            "text":          kw.get("text", ""),
            "ids":           kw.get("ids", []),
            "skip_special":  kw.get("skip_special", True),
        }


class ConsciousnessBot(Bot):
    """
    Consciousness / awareness scoring bot.

    Usage:
        result = await bot.run(text="I think therefore I am")
        print(result["phi"])        # 0.74
        print(result["awareness"])  # "high"
    """
    name     = "consciousness"
    job_type = JobType.CONSCIOUSNESS
    timeout  = 20.0

    def _build_payload(self, **kw) -> dict:
        return {"text": kw.get("text", "")}


class PersonalityBot(Bot):
    """
    Personality vector lookup bot.

    Usage:
        result = await bot.run(profile="dorris-fontaine", dim=128)
        vec = result["vector"]  # List[float]
    """
    name     = "personality"
    job_type = JobType.PERSONALITY
    timeout  = 5.0

    def _build_payload(self, **kw) -> dict:
        return {
            "profile": kw.get("profile", "tranc3-base"),
            "dim":     kw.get("dim", 128),
        }


class PredictBot(Bot):
    """
    Next-token / intent prediction bot.

    Usage:
        result = await bot.run(text="The weather today is", top_k=5)
        print(result["prediction"])  # "sunny"
        print(result["top_k"])       # [{"token": "sunny", "prob": 0.34}, ...]
    """
    name     = "predict"
    job_type = JobType.PREDICT
    timeout  = 10.0

    def _build_payload(self, **kw) -> dict:
        return {
            "text":         kw.get("text", ""),
            "top_k":        kw.get("top_k", 5),
            "predict_type": kw.get("predict_type", "next_token"),
        }


# ─── Registry ─────────────────────────────────────────────────────────────────

_BOT_CLASSES = [
    InferenceBot,
    EmbeddingBot,
    EmotionBot,
    TokenizeBot,
    ConsciousnessBot,
    PersonalityBot,
    PredictBot,
]


class BotRegistry:
    """
    Central registry: creates and manages one instance of each bot type,
    all sharing a single WorkerPool.

    Usage:
        registry = BotRegistry()
        await registry.start()

        result = await registry.run("generate", prompt="Tell me about finance")
        result = await registry.run("emotion",  text="I love Tuesdays!")
    """

    def __init__(self, pool: Optional[WorkerPool] = None):
        self._pool: WorkerPool = pool or get_pool()
        self._bots: Dict[str, Bot] = {}

    async def start(self):
        """Initialise pool and register all bots."""
        await self._pool.start()
        for cls in _BOT_CLASSES:
            bot = cls(self._pool)
            self._bots[bot.name] = bot
            logger.info("Registered bot: %s (job_type=%s)", bot.name, bot.job_type)

    async def stop(self):
        await self._pool.stop()

    def get(self, name: str) -> Optional[Bot]:
        return self._bots.get(name)

    async def run(self, bot_name: str, **kwargs) -> Dict[str, Any]:
        """Run a named bot with keyword arguments."""
        bot = self._bots.get(bot_name)
        if bot is None:
            return {"error": f"Unknown bot: {bot_name}", "available": list(self._bots)}
        return await bot.run(**kwargs)

    def list_bots(self) -> list:
        return [
            {"name": b.name, "job_type": b.job_type, "timeout": b.timeout}
            for b in self._bots.values()
        ]

    async def health(self) -> Dict[str, Any]:
        pool_health = await self._pool.health()
        return {
            "bots":   self.list_bots(),
            "pool":   pool_health,
        }


# ─── Module-level singleton ───────────────────────────────────────────────────

_registry: Optional[BotRegistry] = None


def get_registry() -> BotRegistry:
    global _registry
    if _registry is None:
        _registry = BotRegistry()
    return _registry
