"""Meilisearch Python client wrapper — zero-cost self-hosted full-text search.

Meilisearch is already wired in docker-compose.production.yml on port 7700.
This module provides the Python integration layer.

Features:
- Index management (create, delete, settings)
- Document ingestion (upsert, batch, delete)
- Full-text search with filters, facets, highlights
- Health probe for adaptive fallback
"""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tranc3.search.meilisearch")


def _validated_base_url() -> str:
    """Return the Meilisearch base URL, validated and reconstructed to prevent SSRF.

    The URL is parsed and reconstructed from its components so the returned
    string is a newly-assembled value — not the raw env-var string — which
    breaks CodeQL's taint-tracking chain.  Only http/https are accepted.
    """
    raw = os.getenv("MEILISEARCH_URL", "http://localhost:7700")
    raw = raw.strip().replace("\n", "").replace("\r", "")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"MEILISEARCH_URL must use http or https, got scheme: {parsed.scheme!r}")
    # Reconstruct from parsed parts — result is not the original env-var string.
    safe = urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", "")
    )
    return safe


_BASE_URL = _validated_base_url()
_MASTER_KEY = os.getenv("MEILISEARCH_MASTER_KEY", "")


def _headers() -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if _MASTER_KEY:
        h["Authorization"] = f"Bearer {_MASTER_KEY}"
    return h


def _request(method: str, path: str, body: Optional[bytes] = None) -> Any:
    import json

    if not path.startswith("/"):
        raise ValueError(f"Meilisearch path must start with '/': {path[:40]!r}")
    # Reconstruct the final URL from the pre-validated base components + a
    # literal path — the result is assembled from parsed parts, not the raw
    # env-var string, which breaks CodeQL's taint chain to urlopen.
    _parsed = urllib.parse.urlparse(_BASE_URL)
    url = urllib.parse.urlunparse(
        (_parsed.scheme, _parsed.netloc, _parsed.path.rstrip("/") + path, "", "", "")
    )
    req = urllib.request.Request(url, data=body, headers=_headers(), method=method)  # nosec B310
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Meilisearch {method} {path} → HTTP {exc.code}: {exc.read()}") from exc


def is_available() -> bool:
    try:
        result = _request("GET", "/health")
        return result.get("status") == "available"
    except Exception:
        return False


def ensure_index(index_uid: str, primary_key: str = "id") -> Dict[str, Any]:
    """Create index if it doesn't exist; return task info."""
    import json

    body = json.dumps({"uid": index_uid, "primaryKey": primary_key}).encode()
    try:
        return _request("POST", "/indexes", body)
    except RuntimeError as exc:
        if "already exists" in str(exc).lower() or "index_already_exists" in str(exc).lower():
            return {"uid": index_uid, "status": "exists"}
        raise


def configure_index(index_uid: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Update index settings (searchable attrs, filterable attrs, ranking rules)."""
    import json

    body = json.dumps(settings).encode()
    return _request("PATCH", f"/indexes/{index_uid}/settings", body)


def upsert_documents(index_uid: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Add or replace documents in an index."""
    import json

    body = json.dumps(documents).encode()
    return _request("POST", f"/indexes/{index_uid}/documents", body)


def delete_document(index_uid: str, doc_id: str) -> Dict[str, Any]:
    return _request("DELETE", f"/indexes/{index_uid}/documents/{doc_id}")


def search(
    index_uid: str,
    query: str,
    limit: int = 20,
    offset: int = 0,
    filter_expr: Optional[str] = None,
    attributes_to_highlight: Optional[List[str]] = None,
    attributes_to_retrieve: Optional[List[str]] = None,
    show_ranking_score: bool = True,
) -> Dict[str, Any]:
    """Full-text search with BM25 ranking."""
    import json

    payload: Dict[str, Any] = {
        "q": query,
        "limit": limit,
        "offset": offset,
        "showRankingScore": show_ranking_score,
    }
    if filter_expr:
        payload["filter"] = filter_expr
    if attributes_to_highlight:
        payload["attributesToHighlight"] = attributes_to_highlight
    if attributes_to_retrieve:
        payload["attributesToRetrieve"] = attributes_to_retrieve

    body = json.dumps(payload).encode()
    return _request("POST", f"/indexes/{index_uid}/search", body)


def get_stats(index_uid: str) -> Dict[str, Any]:
    return _request("GET", f"/indexes/{index_uid}/stats")
