"""
src/workflow/nodes/ai.py — AI/ML inference nodes for The Digital Grid.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict

import httpx

from Dimensional.error_handlers import safe_error_detail

from .base import BaseNode, NodeResult


class LLMNode(BaseNode):
    """Generates text using the local TRANC3 model. No external API required."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config

        personality = cfg.get("personality", "tranc3-base")
        system_prompt = cfg.get("system_prompt", "")
        max_tokens = int(cfg.get("max_tokens", 512))
        temperature = float(cfg.get("temperature", 0.8))

        user_message = cfg.get("prompt", "")
        if not user_message:
            user_message = str(next(iter(inputs.values()), "")) if inputs else ""
        for k, v in inputs.items():
            user_message = user_message.replace(f"{{{{{k}}}}}", str(v))

        try:
            from src.core.tranc3_inference import get_engine

            engine = get_engine()
            gen = await engine.generate(
                prompt=user_message,
                personality=personality,
                system_prompt=system_prompt or None,
                max_new_tokens=max_tokens,
                temperature=temperature,
            )
            result_text = gen.get("response", "")
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                result_text,
                duration_ms,
                metadata={
                    "model": gen.get("model", "tranc3-local"),
                    "personality": personality,
                    "tokens": gen.get("tokens", 0),
                    "trained": gen.get("trained", True),
                },
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error=safe_error_detail(exc, 500)
            )


class MLPredictNode(BaseNode):
    """Calls the Tranc3 model inference endpoint for ML predictions."""

    _DEFAULT_ENDPOINT = "http://localhost:8080/predict"

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config
        endpoint = cfg.get("endpoint") or os.environ.get(
            "TRANC3_MODEL_ENDPOINT", self._DEFAULT_ENDPOINT
        )
        model_name = cfg.get("model_name", "tranc3-base")
        payload = {
            "model": model_name,
            "inputs": {**cfg.get("static_inputs", {}), **inputs},
        }
        headers = {"Content-Type": "application/json"}
        api_key = cfg.get("api_key") or os.environ.get("TRANC3_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async def _infer() -> Any:
            async with httpx.AsyncClient(timeout=self.config.timeout_sec) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()

        try:
            result = await self._retry(
                lambda: self._with_timeout(_infer(), self.config.timeout_sec),
                self.config.retry_count,
            )
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                result,
                duration_ms,
                metadata={"model_name": model_name, "endpoint": endpoint},
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error=safe_error_detail(exc, 500)
            )


__all__ = ["LLMNode", "MLPredictNode"]
