#!/usr/bin/env python3
# src/workers/inference_worker.py
# TRANC3 Inference Worker — standalone process that drains the task queue.
#
# Run N copies to scale horizontally:
#   TRANC3_WORKER_ID=0 python -m src.workers.inference_worker
#   TRANC3_WORKER_ID=1 python -m src.workers.inference_worker
#
# Each worker loads Tranc3Engine ONCE, then processes jobs from Redis in a loop.
# Zero external inference APIs. Zero cost beyond your own hardware.

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from typing import Any, Dict, Optional

from src.workers.pool import (
    _QUEUE_KEY,
    _RESULT_PREFIX,
    _RESULT_TTL,
    JobResult,
    JobSpec,
    JobStatus,
    JobType,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("tranc3.worker")

_WORKER_ID = os.getenv("TRANC3_WORKER_ID", "0")
_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
_CONCURRENCY = int(os.getenv("TRANC3_CONCURRENCY", "1"))  # tasks in parallel per process


class InferenceWorker:
    """
    Single worker process: loads Tranc3Engine + handles all job types.

    Supported job types:
        generate        — text generation / chat
        embed           — vector embeddings from token representations
        emotion         — emotion detection on input text
        tokenize        — tokenize/decode text
        consciousness   — consciousness/awareness scoring
        personality     — personality vector lookup
        predict         — next-token prediction / intent
    """

    def __init__(self):
        self._engine = None
        self._tokenizer = None
        self._redis = None
        self._running = False
        self._sem = asyncio.Semaphore(_CONCURRENCY)

    # ─── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        logger.info("Worker %s starting…", _WORKER_ID)
        self._redis = await self._connect_redis()
        self._engine = await self._load_engine()
        self._running = True
        logger.info("Worker %s ready", _WORKER_ID)

    async def stop(self):
        self._running = False
        if self._redis:
            await self._redis.aclose()
        logger.info("Worker %s stopped", _WORKER_ID)

    # ─── Main loop ─────────────────────────────────────────────────────────────

    async def run(self):
        await self.start()
        assert self._redis is not None  # noqa: S101 — set by start()
        assert self._engine is not None  # noqa: S101 — set by start()
        while self._running:
            try:
                item = await self._redis.brpop(_QUEUE_KEY, timeout=2)
                if item is None:
                    continue
                _, raw = item
                job = JobSpec.from_json(raw)
                asyncio.create_task(self._handle(job))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Queue read error: %s", exc)
                await asyncio.sleep(1)
        await self.stop()

    async def _handle(self, job: JobSpec):
        async with self._sem:
            t0 = time.monotonic()
            result_data: Optional[Dict[str, Any]] = None
            error: Optional[str] = None
            status = JobStatus.DONE

            try:
                result_data = await self._dispatch(job)
            except Exception as exc:
                error = str(exc)
                status = JobStatus.FAILED
                logger.exception("Job %s failed: %s", job.job_id, exc)

            result = JobResult(
                job_id=job.job_id,
                status=status,
                result=result_data,
                error=error,
                duration_ms=(time.monotonic() - t0) * 1000,
                worker_id=f"inference-{_WORKER_ID}",
            )
            key = f"{_RESULT_PREFIX}{job.job_id}"
            assert self._redis is not None  # noqa: S101 — always set before _handle is called
            await self._redis.set(key, result.to_json(), ex=_RESULT_TTL)
            logger.info(
                "Job %s [%s] done in %.1f ms",
                job.job_id,
                job.job_type,
                result.duration_ms,
            )

    # ─── Dispatch ──────────────────────────────────────────────────────────────

    async def _dispatch(self, job: JobSpec) -> Dict[str, Any]:
        jt = job.job_type
        p = job.payload

        if jt == JobType.GENERATE:
            return await self._do_generate(p)
        elif jt == JobType.EMBED:
            return await self._do_embed(p)
        elif jt == JobType.EMOTION:
            return await self._do_emotion(p)
        elif jt == JobType.TOKENIZE:
            return await self._do_tokenize(p)
        elif jt == JobType.CONSCIOUSNESS:
            return await self._do_consciousness(p)
        elif jt == JobType.PERSONALITY:
            return await self._do_personality(p)
        elif jt == JobType.PREDICT:
            return await self._do_predict(p)
        else:
            raise ValueError(f"Unknown job type: {jt}")

    # ─── Task implementations ──────────────────────────────────────────────────

    async def _do_generate(self, p: dict) -> dict:
        prompt = p.get("prompt", "")
        personality = p.get("personality", "tranc3-base")
        system = p.get("system_prompt")
        max_tokens = p.get("max_tokens", 256)
        temperature = p.get("temperature", 0.8)
        top_p = p.get("top_p", 0.9)

        assert self._engine is not None  # noqa: S101 — always set before _dispatch routes here
        return await self._engine.generate(
            prompt=prompt,
            personality=personality,
            system_prompt=system,
            max_new_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )

    async def _do_embed(self, p: dict) -> dict:
        import torch

        text = p.get("text", "")
        pooling = p.get("pooling", "mean")  # "mean" | "cls" | "max"

        assert self._engine is not None  # noqa: S101 — always set before _dispatch routes here
        if self._engine._bootstrap_mode or not self._engine._loaded:
            # Bootstrap: return a deterministic pseudo-embedding
            import hashlib

            h = int(hashlib.sha256(text.encode()).hexdigest(), 16)
            dims = p.get("dims", 256)
            vec = [((h >> i) & 0xFF) / 255.0 - 0.5 for i in range(dims)]
            return {"embedding": vec, "dims": dims, "model": "tranc3-bootstrap"}

        tok = self._engine._tokenizer
        ids = tok.encode(text, max_length=512)
        t = torch.tensor([ids], dtype=torch.long, device=self._engine._device)

        model = self._engine._model
        with torch.no_grad():
            hidden = model.get_embeddings(t)  # (1, seq, hidden)

        if pooling == "cls":
            vec = hidden[0, 0, :]
        elif pooling == "max":
            vec, _ = hidden[0].max(dim=0)
        else:  # mean
            vec = hidden[0].mean(dim=0)

        return {
            "embedding": vec.cpu().tolist(),
            "dims": vec.shape[0],
            "model": "tranc3-local",
            "pooling": pooling,
        }

    async def _do_emotion(self, p: dict) -> dict:
        text = p.get("text", "")

        if self._engine._bootstrap_mode or not self._engine._loaded:
            # Rule-based fallback
            text_lower = text.lower()
            emotions = {
                "joy": any(
                    w in text_lower
                    for w in ["happy", "great", "excellent", "wonderful", "love", "yay"]
                ),
                "sadness": any(
                    w in text_lower for w in ["sad", "unhappy", "terrible", "awful", "cry", "miss"]
                ),
                "anger": any(
                    w in text_lower for w in ["angry", "furious", "hate", "rage", "frustrated"]
                ),
                "fear": any(
                    w in text_lower for w in ["scared", "afraid", "fear", "worried", "anxious"]
                ),
                "surprise": any(
                    w in text_lower
                    for w in ["wow", "amazing", "unexpected", "shocked", "unbelievable"]
                ),
                "disgust": any(
                    w in text_lower
                    for w in ["disgusting", "horrible", "gross", "nasty", "repulsive"]
                ),
            }
            scores = {k: 0.7 if v else 0.05 for k, v in emotions.items()}
            # normalise
            total = sum(scores.values()) or 1.0
            scores = {k: round(v / total, 4) for k, v in scores.items()}
            dominant = max(scores, key=scores.get)
            return {
                "dominant": dominant,
                "scores": scores,
                "model": "tranc3-rule-based",
            }

        # Model-based: embed → lightweight classifier head
        embed_result = await self._do_embed({"text": text, "pooling": "mean"})
        import torch

        vec = torch.tensor(embed_result["embedding"])

        # Project to 6-class emotion space via a simple learned projection
        # (In production this head is trained alongside the main model)
        # For now: cosine sim against emotion anchors derived from training phrases
        EMOTION_ANCHORS = {
            "joy": "I feel wonderful and happy today",
            "sadness": "I feel sad and unhappy",
            "anger": "I am so angry and frustrated",
            "fear": "I am scared and afraid",
            "surprise": "I am completely shocked and amazed",
            "disgust": "This is utterly disgusting",
        }
        scores = {}
        for emotion, anchor_text in EMOTION_ANCHORS.items():
            anchor_emb = await self._do_embed({"text": anchor_text, "pooling": "mean"})
            av = torch.tensor(anchor_emb["embedding"])
            sim = torch.nn.functional.cosine_similarity(vec.unsqueeze(0), av.unsqueeze(0)).item()
            scores[emotion] = round(max(0.0, sim), 4)

        total = sum(scores.values()) or 1.0
        scores = {k: round(v / total, 4) for k, v in scores.items()}
        dominant = max(scores, key=scores.get)
        return {"dominant": dominant, "scores": scores, "model": "tranc3-local"}

    async def _do_tokenize(self, p: dict) -> dict:
        action = p.get("action", "encode")  # "encode" | "decode"
        text = p.get("text", "")

        if self._engine._bootstrap_mode or not self._engine._loaded:
            # Whitespace tokenizer fallback
            if action == "encode":
                tokens = text.split()
                return {
                    "tokens": tokens,
                    "ids": list(range(len(tokens))),
                    "model": "fallback",
                }
            else:
                ids = p.get("ids", [])
                return {"text": f"[decoded {len(ids)} tokens]", "model": "fallback"}

        tok = self._engine._tokenizer
        if action == "encode":
            ids = tok.encode(text)
            tokens = [tok.id_to_token(i) for i in ids]
            return {
                "tokens": tokens,
                "ids": ids,
                "count": len(ids),
                "model": "tranc3-bpe",
            }
        else:
            ids = p.get("ids", [])
            text = tok.decode(ids, skip_special_tokens=p.get("skip_special", True))
            return {"text": text, "model": "tranc3-bpe"}

    async def _do_consciousness(self, p: dict) -> dict:
        text = p.get("text", "")
        try:
            from src.core.consciousness_integration import ConsciousnessIntegration

            ci = ConsciousnessIntegration()
            phi = await ci.compute_phi(text)
        except Exception:
            # Fallback: heuristic phi estimate based on text complexity
            words = text.split()
            vocab = len(set(words))
            phi = min(1.0, vocab / max(len(words), 1) * 2.0)

        return {
            "phi": round(phi, 4),
            "awareness": "high" if phi > 0.7 else "medium" if phi > 0.4 else "low",
            "model": "tranc3-consciousness",
        }

    async def _do_personality(self, p: dict) -> dict:
        import torch

        profile = p.get("profile", "tranc3-base")
        dim = p.get("dim", 128)

        try:
            from src.personality.personality_engine import PersonalityEngine

            pe = PersonalityEngine()
            vec = pe.get_vector(profile)
            return {
                "profile": profile,
                "vector": vec.tolist(),
                "dims": len(vec),
                "model": "tranc3-personality",
            }
        except Exception:
            # Deterministic pseudo-vector from profile name hash
            import hashlib

            seed = int(hashlib.sha256(profile.encode()).hexdigest(), 16) % (2**32)
            gen = torch.manual_seed(seed)
            vec = torch.randn(dim, generator=gen)
            vec = (vec / vec.norm()).tolist()
            return {
                "profile": profile,
                "vector": vec,
                "dims": dim,
                "model": "tranc3-hash-personality",
            }

    async def _do_predict(self, p: dict) -> dict:
        text = p.get("text", "")
        top_k = p.get("top_k", 5)
        p.get("predict_type", "next_token")

        if self._engine._bootstrap_mode or not self._engine._loaded:
            return {
                "prediction": "continue",
                "confidence": 0.5,
                "top_k": [{"token": "the", "prob": 0.1}] * top_k,  # nosec B105 — false positive: not a password
                "model": "tranc3-bootstrap",
            }

        import torch

        tok = self._engine._tokenizer
        ids = tok.encode(text, max_length=500)
        t = torch.tensor([ids], dtype=torch.long, device=self._engine._device)

        with torch.no_grad():
            logits = self._engine._model(t)  # (1, seq, vocab)
        next_logits = logits[0, -1, :]  # last position
        probs = torch.softmax(next_logits, dim=-1)
        topk_probs, topk_ids = probs.topk(top_k)

        top_k_result = [
            {"token": tok.id_to_token(int(i)), "prob": round(float(p), 4)}
            for i, p in zip(topk_ids.tolist(), topk_probs.tolist(), strict=False)
        ]
        return {
            "prediction": top_k_result[0]["token"] if top_k_result else "",
            "confidence": top_k_result[0]["prob"] if top_k_result else 0.0,
            "top_k": top_k_result,
            "model": "tranc3-local",
        }

    # ─── Engine + Redis ─────────────────────────────────────────────────────────

    @staticmethod
    async def _load_engine():
        from src.core.tranc3_inference import Tranc3Engine

        engine = Tranc3Engine()
        # Load is synchronous (torch.load) — run in executor so we don't block the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, engine.load)
        logger.info("Tranc3Engine ready: %s", engine.status())
        return engine

    @staticmethod
    async def _connect_redis():
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(_REDIS_URL, decode_responses=True)
            await client.ping()
            logger.info("Redis connected: %s", _REDIS_URL)
            return client
        except Exception as exc:
            logger.warning("Redis unavailable: %s — using memory queue", exc)
            from src.workers.pool import _MemoryQueue

            return _MemoryQueue()


# ─── Entry point ─────────────────────────────────────────────────────────────


async def _main():
    worker = InferenceWorker()

    loop = asyncio.get_running_loop()

    def _shutdown(*_):
        logger.info("Shutdown signal received")
        worker._running = False

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())
