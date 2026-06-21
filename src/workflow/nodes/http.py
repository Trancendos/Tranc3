"""
src/workflow/nodes/http.py — HTTP and vector search nodes for The Digital Grid.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict

import httpx

from Dimensional.error_handlers import safe_error_detail

from .base import BaseNode, NodeResult


class HTTPNode(BaseNode):
    """Makes HTTP requests (GET/POST/PUT/DELETE/PATCH) and returns parsed JSON or text."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config
        method = cfg.get("method", "GET").upper()
        url = cfg.get("url", inputs.get("url", ""))
        headers = {**cfg.get("headers", {}), **inputs.get("headers", {})}
        params = {**cfg.get("params", {}), **inputs.get("params", {})}
        body = inputs.get("body", cfg.get("body"))
        timeout = self.config.timeout_sec

        async def _request() -> Any:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers, params=params)
                elif method == "POST":
                    resp = await client.post(url, headers=headers, params=params, json=body)
                elif method == "PUT":
                    resp = await client.put(url, headers=headers, params=params, json=body)
                elif method == "DELETE":
                    resp = await client.delete(url, headers=headers, params=params)
                elif method == "PATCH":
                    resp = await client.patch(url, headers=headers, params=params, json=body)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "application/json" in content_type:
                    return {"status_code": resp.status_code, "body": resp.json()}
                return {"status_code": resp.status_code, "body": resp.text}

        try:
            output = await self._retry(
                lambda: self._with_timeout(_request(), timeout),
                self.config.retry_count,
            )
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(output, duration_ms, metadata={"method": method, "url": url})
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error=safe_error_detail(exc, 500)
            )


class VectorSearchNode(BaseNode):
    """Performs a nearest-neighbour search against a Qdrant collection."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config
        qdrant_url = cfg.get("qdrant_url") or os.environ.get("QDRANT_URL", "http://localhost:6333")
        collection = cfg.get("collection", inputs.get("collection", "default"))
        top_k = int(cfg.get("top_k", 5))
        vector = inputs.get("vector") or cfg.get("vector")
        score_threshold = cfg.get("score_threshold", 0.0)
        with_payload = cfg.get("with_payload", True)

        if not vector:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error="No query vector provided in inputs"
            )

        payload: Dict[str, Any] = {
            "vector": vector,
            "limit": top_k,
            "with_payload": with_payload,
            "score_threshold": score_threshold,
        }
        url = f"{qdrant_url.rstrip('/')}/collections/{collection}/points/search"

        async def _search() -> Any:
            async with httpx.AsyncClient(timeout=self.config.timeout_sec) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json().get("result", [])

        try:
            results = await self._retry(
                lambda: self._with_timeout(_search(), self.config.timeout_sec),
                self.config.retry_count,
            )
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                {"results": results, "count": len(results)},
                duration_ms,
                metadata={"collection": collection, "top_k": top_k},
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error=safe_error_detail(exc, 500)
            )


__all__ = ["HTTPNode", "VectorSearchNode"]
