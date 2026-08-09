# src/library/bridge.py
# Best-effort fire-and-forget bridge from the in-process Library singleton
# (src/library/knowledge_base.py) to workers/library-service/'s durable
# document store.
#
# Fail-open by explicit product decision (2026-08-08), and deliberately
# narrow in scope: this bridge only forwards newly-created PUBLIC/INTERNAL/
# CONFIDENTIAL articles for durability. It NEVER forwards RESTRICTED or
# TOP_SECRET articles, and it NEVER reads from the worker — the worker has
# no equivalent of src/library/routes.py's DataClassification-based
# _can_read() authorization (see MONOLITH-EXTRACTION-FINDINGS.md's
# `library` bullet: the worker is a generic pluggable wiki-backend facade
# with no classification/author/retention concept and no per-caller
# authorization at all), so routing reads through it, or forwarding
# restricted content to it, would silently drop that access-control layer —
# the same failure class as the reverted Resonate removal.
# src/library/routes.py's in-process Library.get()/search()/by_tag()/etc.
# remain the sole authoritative read path for every classification level;
# this bridge only adds a second, durable write for content that was never
# access-restricted in the first place.

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

_LIBRARY_URL = os.environ.get("LIBRARY_SERVICE_URL", "http://library-service:8067")
_LIBRARY_INTERNAL_SECRET = os.environ.get("LIBRARY_SERVICE_INTERNAL_SECRET", "")

_FORWARDABLE_CLASSIFICATIONS = frozenset({"public", "internal", "confidential"})

_FORWARD_CONCURRENCY = int(os.environ.get("LIBRARY_FORWARD_CONCURRENCY", "10"))
_forward_inflight = 0


def forward_article(article: Any) -> None:
    """Schedule a fire-and-forget durable-store write for a newly-created
    Article. Skipped entirely (not just redacted) for RESTRICTED/TOP_SECRET
    content — see module docstring. No-op if there's no running event loop
    or the in-flight cap is already reached.
    """
    global _forward_inflight
    classification = getattr(article, "classification", None)
    classification_value = getattr(classification, "value", str(classification))
    if classification_value not in _FORWARDABLE_CLASSIFICATIONS:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _forward_inflight >= _FORWARD_CONCURRENCY:
        return
    _forward_inflight += 1
    loop.create_task(_post_document(article))


async def _post_document(article: Any) -> None:
    global _forward_inflight
    try:
        import httpx

        headers = (
            {"X-Internal-Secret": _LIBRARY_INTERNAL_SECRET} if _LIBRARY_INTERNAL_SECRET else {}
        )
        classification = getattr(article, "classification", None)
        payload = {
            "title": article.title,
            "content": article.body,
            "collection": "trancendos-library",
            "tags": list(article.tags or []),
            "metadata": {
                "source_article_id": article.id,
                "author": article.author,
                "classification": getattr(classification, "value", str(classification)),
            },
        }
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{_LIBRARY_URL}/library/documents",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
    except Exception as exc:
        safe_id = str(getattr(article, "id", "")).replace("\r", "").replace("\n", "")
        logger.debug(
            "library: durable document forward skipped (article_id=%s): %s",
            safe_id,
            sanitize_for_log(exc),
        )  # codeql[py/cleartext-logging]
    finally:
        _forward_inflight -= 1
