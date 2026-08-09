# src/library/bridge.py
# Best-effort fire-and-forget bridge from the in-process Library singleton
# (src/library/knowledge_base.py) to workers/library-service/'s durable
# document store.
#
# Fail-open by explicit product decision (2026-08-08), and deliberately
# narrow in scope: this bridge only forwards newly-created PUBLIC/INTERNAL
# articles for durability. It NEVER forwards CONFIDENTIAL, RESTRICTED, or
# TOP_SECRET articles, and it NEVER reads from the worker — the worker has
# no equivalent of src/library/routes.py's DataClassification-based
# _can_read() authorization (see MONOLITH-EXTRACTION-FINDINGS.md's
# `library` bullet: the worker is a generic pluggable wiki-backend facade
# with no classification/author/retention concept and no per-caller
# authorization at all — only a shared X-Internal-Secret that authenticates
# the bridge itself, not the end reader), so routing reads through it, or
# forwarding restricted content to it, would silently drop that
# access-control layer — the same failure class as the reverted Resonate
# removal. src/library/routes.py's in-process Library.get()/search()/
# by_tag()/etc. remain the sole authoritative read path for every
# classification level; this bridge only adds a second, durable write for
# content that was never access-restricted in the first place.
#
# CONFIDENTIAL was narrowed OUT of the forwardable set after review
# (2026-08-08): routes.py's _can_read() only gates RESTRICTED/TOP_SECRET,
# so CONFIDENTIAL is technically as readable in-process as PUBLIC/INTERNAL
# today — but "authenticated platform user" (the in-process bar) and "holds
# the shared X-Internal-Secret" (the worker's bar) are different *kinds* of
# trust, not the same bar in two places, and once something lands in the
# worker's store it's readable by anything holding that one secret forever,
# independent of whatever the in-process policy is or later becomes.
# CONFIDENTIAL content stays in-process only, same as RESTRICTED/TOP_SECRET.
#
# PII gate: classification label alone doesn't guarantee a PUBLIC/INTERNAL
# article is free of personal data — an author can put anything in the body.
# Every forward is additionally gated on src.security.log_redactor's
# contains_pii() heuristic (email/credit-card/UK-NI-number patterns); a hit
# skips the forward entirely, same as a non-forwardable classification.
#
# Hardening pass (post-implementation, same 2026-08-08 decision): a
# CircuitBreaker skips even *scheduling* a forward once the worker has been
# consistently unreachable, avoiding a pile-up of doomed connection attempts
# during a sustained outage — self-probes back to closed once recovered.
#
# Delete propagation: Library.delete() forwards a best-effort delete for any
# article this process previously forwarded, so a source-of-truth deletion
# doesn't leave an orphaned durable copy behind — see forward_delete().
# Article-id -> worker-doc-id mapping is in-process only (matches the
# best-effort character of everything else here); across a process restart
# a delete for a pre-restart forward has nothing to look up and is silently
# skipped, same fail-open posture as an unreachable worker.
#
# IP/provenance tagging: every forwarded document carries a SHA-256 content
# hash in its metadata (content_hash) and a fixed provenance marker
# (source_system) — cheap, tamper-evident fingerprinting that lets a leaked
# copy of forwarded content be matched back to its exact source article and
# confirms the worker's stored copy hasn't silently diverged from the
# original, without the engineering cost of full content watermarking.

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any

from Dimensional.sanitize import sanitize_for_log

from src.mesh.circuit_breaker import CircuitBreaker
from src.security.log_redactor import contains_pii

logger = logging.getLogger(__name__)

_LIBRARY_URL = os.environ.get("LIBRARY_SERVICE_URL", "http://library-service:8067")
_LIBRARY_INTERNAL_SECRET = os.environ.get("LIBRARY_SERVICE_INTERNAL_SECRET", "")

# CONFIDENTIAL deliberately excluded — see module docstring.
_FORWARDABLE_CLASSIFICATIONS = frozenset({"public", "internal"})

_FORWARD_CONCURRENCY = int(os.environ.get("LIBRARY_FORWARD_CONCURRENCY", "10"))
_forward_inflight = 0

_circuit = CircuitBreaker("library-service")

# article_id -> worker doc_id, populated on a successful forward, consulted
# by forward_delete(). In-process only — see module docstring.
_article_to_doc_id: dict[str, str] = {}


def _headers() -> dict[str, str]:
    return {"X-Internal-Secret": _LIBRARY_INTERNAL_SECRET} if _LIBRARY_INTERNAL_SECRET else {}


def _is_forwardable(article: Any) -> bool:
    classification = getattr(article, "classification", None)
    classification_value = getattr(classification, "value", str(classification))
    if classification_value not in _FORWARDABLE_CLASSIFICATIONS:
        return False
    # Content-level gate, independent of the classification label — see
    # module docstring's "PII gate" note.
    if contains_pii(article.title or "") or contains_pii(article.body or ""):
        return False
    return True


def forward_article(article: Any) -> None:
    """Schedule a fire-and-forget durable-store write for a newly-created
    Article. Skipped entirely (not just redacted) for CONFIDENTIAL/
    RESTRICTED/TOP_SECRET content or content that looks like it carries PII
    — see module docstring. No-op if there's no running event loop, the
    in-flight cap is already reached, or the circuit breaker is open.
    """
    global _forward_inflight
    if not _is_forwardable(article):
        return
    if not _circuit.can_execute():
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

        classification = getattr(article, "classification", None)
        body = article.body or ""
        payload = {
            "title": article.title,
            "content": body,
            "collection": "trancendos-library",
            "tags": list(article.tags or []),
            "metadata": {
                "source_article_id": article.id,
                "author": article.author,
                "classification": getattr(classification, "value", str(classification)),
                "source_system": "trancendos-library-bridge",
                "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            },
        }
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{_LIBRARY_URL}/library/documents",
                json=payload,
                headers=_headers(),
            )
            response.raise_for_status()
            doc_id = response.json().get("doc_id")
        if doc_id:
            _article_to_doc_id[article.id] = doc_id
        _circuit.record_success()
    except Exception as exc:
        _circuit.record_failure()
        safe_id = str(getattr(article, "id", "")).replace("\r", "").replace("\n", "")
        logger.debug(
            "library: durable document forward skipped (article_id=%s): %s",
            safe_id,
            sanitize_for_log(exc),
        )  # codeql[py/cleartext-logging]
    finally:
        _forward_inflight -= 1


def forward_delete(article_id: str) -> None:
    """Schedule a fire-and-forget delete of the durable copy (if any) for a
    source article that was just deleted in-process. A no-op if this
    article was never forwarded (never became forwardable, the process
    restarted since it was forwarded, or the forward itself failed) — there
    is nothing to delete in that case, and that's fine: fail-open applies
    to deletes the same way it applies to creates.
    """
    global _forward_inflight
    doc_id = _article_to_doc_id.pop(article_id, None)
    if not doc_id:
        return
    if not _circuit.can_execute():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _forward_inflight >= _FORWARD_CONCURRENCY:
        return
    _forward_inflight += 1
    loop.create_task(_delete_document(doc_id))


async def _delete_document(doc_id: str) -> None:
    global _forward_inflight
    try:
        import httpx

        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.delete(
                f"{_LIBRARY_URL}/library/documents/{doc_id}",
                headers=_headers(),
            )
            if response.status_code != 404:
                response.raise_for_status()
        _circuit.record_success()
    except Exception as exc:
        _circuit.record_failure()
        safe_doc_id = str(doc_id).replace("\r", "").replace("\n", "")
        logger.debug(
            "library: durable document delete skipped (doc_id=%s): %s",
            safe_doc_id,
            sanitize_for_log(exc),
        )  # codeql[py/cleartext-logging]
    finally:
        _forward_inflight -= 1
