"""The Library — ACO pheromone router across 8 free wiki backends (Lead AI: Zimik)"""
from __future__ import annotations

import collections
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from models import (
    BackendStatus,
    DocumentCreate,
    DocumentFormat,
    DocumentResponse,
    LibraryBackend,
    LibraryStatus,
    SearchResponse,
    SearchResult,
)

import config
from database import LibraryDatabase

logger = logging.getLogger(config.WORKER_NAME)


# ── ThresholdGuard (per-backend quota + pheromone) ─────────────────────────────

class ThresholdGuard:
    def __init__(self, name: str, quota: int, window: int):
        self.name = name
        self.quota = quota
        self.window = window
        self.pheromone: float = 1.0
        self._ts: collections.deque = collections.deque()

    def can_allow(self) -> bool:
        self._evict()
        return len(self._ts) < self.quota

    def record(self) -> None:
        self._ts.append(time.monotonic())

    def allow(self) -> bool:
        if not self.can_allow():
            return False
        self.record()
        return True

    def reinforce(self) -> None:
        self.pheromone = min(1.0, self.pheromone + 0.1)

    def decay(self) -> None:
        self.pheromone = max(0.0, self.pheromone - config.PHEROMONE_DECAY)

    def calls_in_window(self) -> int:
        self._evict()
        return len(self._ts)

    def _evict(self) -> None:
        cutoff = time.monotonic() - self.window
        while self._ts and self._ts[0] < cutoff:
            self._ts.popleft()


# ── Backend registry ───────────────────────────────────────────────────────────

_BACKENDS: Dict[str, ThresholdGuard] = {
    LibraryBackend.outline: ThresholdGuard(LibraryBackend.outline, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS),
    LibraryBackend.bookstack: ThresholdGuard(LibraryBackend.bookstack, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS),
    LibraryBackend.wikijs: ThresholdGuard(LibraryBackend.wikijs, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS),
    LibraryBackend.gollum: ThresholdGuard(LibraryBackend.gollum, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS),
    LibraryBackend.dokuwiki: ThresholdGuard(LibraryBackend.dokuwiki, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS),
    LibraryBackend.mkdocs: ThresholdGuard(LibraryBackend.mkdocs, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS),
    LibraryBackend.gitea: ThresholdGuard(LibraryBackend.gitea, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS),
    LibraryBackend.tiddlywiki: ThresholdGuard(LibraryBackend.tiddlywiki, config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS),
}

_BACKEND_ORDER = [
    LibraryBackend.outline,
    LibraryBackend.bookstack,
    LibraryBackend.wikijs,
    LibraryBackend.gollum,
    LibraryBackend.dokuwiki,
    LibraryBackend.mkdocs,
    LibraryBackend.gitea,
    LibraryBackend.tiddlywiki,
]


def _choose_backend() -> Optional[str]:
    candidates = [
        (name, guard) for name, guard in _BACKENDS.items()
        if guard.can_allow() and guard.pheromone > 0.01
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[1].pheromone, reverse=True)
    return candidates[0][0]


# ── Per-backend adapters ───────────────────────────────────────────────────────

async def _probe_backend(name: str) -> bool:
    url_map = {
        LibraryBackend.outline: config.OUTLINE_URL,
        LibraryBackend.bookstack: config.BOOKSTACK_URL,
        LibraryBackend.wikijs: config.WIKIJS_URL,
        LibraryBackend.gollum: config.GOLLUM_URL,
        LibraryBackend.dokuwiki: config.DOKUWIKI_URL,
        LibraryBackend.mkdocs: config.MKDOCS_URL,
        LibraryBackend.gitea: config.GITEA_URL,
        LibraryBackend.tiddlywiki: config.TIDDLYWIKI_URL,
    }
    base = url_map.get(name)
    if not base:
        return False
    try:
        async with httpx.AsyncClient(verify=config.TLS_VERIFY, timeout=config.PROBE_TIMEOUT) as client:
            r = await client.get(base)
            return 200 <= r.status_code < 400
    except Exception:
        return False


async def _create_outline(doc: DocumentCreate) -> Optional[Dict[str, Any]]:
    if not config.OUTLINE_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(verify=config.TLS_VERIFY, timeout=10.0) as client:
            headers = {"Authorization": f"Bearer {config.OUTLINE_API_KEY}", "Content-Type": "application/json"}
            payload: Dict[str, Any] = {"title": doc.title, "text": doc.content, "publish": True}
            if doc.collection:
                payload["collectionId"] = doc.collection
            r = await client.post(f"{config.OUTLINE_URL}/api/documents.create", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json().get("data", {})
            return {"doc_id": data.get("id", str(uuid.uuid4())), "url": data.get("url")}
    except Exception as exc:
        logger.debug("Outline create failed: %s", exc)
        return None


async def _search_outline(query: str, collection: Optional[str], limit: int) -> Optional[List[Dict[str, Any]]]:
    if not config.OUTLINE_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(verify=config.TLS_VERIFY, timeout=10.0) as client:
            headers = {"Authorization": f"Bearer {config.OUTLINE_API_KEY}", "Content-Type": "application/json"}
            payload: Dict[str, Any] = {"query": query, "limit": limit}
            if collection:
                payload["collectionId"] = collection
            r = await client.post(f"{config.OUTLINE_URL}/api/documents.search", json=payload, headers=headers)
            r.raise_for_status()
            items = r.json().get("data", [])
            return [
                {
                    "doc_id": i.get("document", {}).get("id", ""),
                    "title": i.get("document", {}).get("title", ""),
                    "excerpt": i.get("context", "")[:300],
                    "collection": i.get("document", {}).get("collectionId"),
                    "url": i.get("document", {}).get("url"),
                }
                for i in items
            ]
    except Exception as exc:
        logger.debug("Outline search failed: %s", exc)
        return None


async def _create_bookstack(doc: DocumentCreate) -> Optional[Dict[str, Any]]:
    if not config.BOOKSTACK_TOKEN_ID or not config.BOOKSTACK_TOKEN_SECRET:
        return None
    try:
        async with httpx.AsyncClient(verify=config.TLS_VERIFY, timeout=10.0) as client:
            headers = {
                "Authorization": f"Token {config.BOOKSTACK_TOKEN_ID}:{config.BOOKSTACK_TOKEN_SECRET}",
                "Content-Type": "application/json",
            }
            payload: Dict[str, Any] = {"name": doc.title, "markdown": doc.content}
            if doc.collection:
                payload["book_id"] = int(doc.collection) if doc.collection.isdigit() else 1
            r = await client.post(f"{config.BOOKSTACK_URL}/api/pages", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            return {"doc_id": str(data.get("id", uuid.uuid4())), "url": data.get("url")}
    except Exception as exc:
        logger.debug("BookStack create failed: %s", exc)
        return None


async def _search_bookstack(query: str, limit: int) -> Optional[List[Dict[str, Any]]]:
    if not config.BOOKSTACK_TOKEN_ID or not config.BOOKSTACK_TOKEN_SECRET:
        return None
    try:
        async with httpx.AsyncClient(verify=config.TLS_VERIFY, timeout=10.0) as client:
            headers = {"Authorization": f"Token {config.BOOKSTACK_TOKEN_ID}:{config.BOOKSTACK_TOKEN_SECRET}"}
            r = await client.get(
                f"{config.BOOKSTACK_URL}/api/search",
                params={"query": query, "count": limit},
                headers=headers,
            )
            r.raise_for_status()
            items = r.json().get("data", [])
            return [
                {
                    "doc_id": str(i.get("id", "")),
                    "title": i.get("name", ""),
                    "excerpt": i.get("preview_html", "")[:300],
                    "collection": str(i.get("book_id", "")),
                    "url": i.get("url"),
                }
                for i in items
            ]
    except Exception as exc:
        logger.debug("BookStack search failed: %s", exc)
        return None


async def _create_wikijs(doc: DocumentCreate) -> Optional[Dict[str, Any]]:
    if not config.WIKIJS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(verify=config.TLS_VERIFY, timeout=10.0) as client:
            headers = {"Authorization": f"Bearer {config.WIKIJS_API_KEY}", "Content-Type": "application/json"}
            path = f"/library/{doc.title.lower().replace(' ', '-')}"
            mutation = """
            mutation($content: String!, $description: String!, $editor: String!, $isPrivate: Boolean!,
                     $isPublished: Boolean!, $locale: String!, $path: String!, $tags: [String]!, $title: String!) {
              pages { create(content: $content, description: $description, editor: $editor,
                             isPrivate: $isPrivate, isPublished: $isPublished, locale: $locale,
                             path: $path, tags: $tags, title: $title) {
                responseResult { succeeded errorCode message }
                page { id path }
              }}
            }"""
            variables = {
                "content": doc.content, "description": "", "editor": "markdown",
                "isPrivate": False, "isPublished": True, "locale": "en",
                "path": path, "tags": doc.tags, "title": doc.title,
            }
            r = await client.post(
                f"{config.WIKIJS_URL}/graphql",
                json={"query": mutation, "variables": variables},
                headers=headers,
            )
            r.raise_for_status()
            page = r.json().get("data", {}).get("pages", {}).get("create", {}).get("page", {})
            return {"doc_id": str(page.get("id", uuid.uuid4())), "url": page.get("path")}
    except Exception as exc:
        logger.debug("Wiki.js create failed: %s", exc)
        return None


async def _offline_create(doc: DocumentCreate) -> Dict[str, Any]:
    """Fallback — store locally only, no external backend."""
    return {"doc_id": str(uuid.uuid4()), "url": None}


# ── LibraryRouter ──────────────────────────────────────────────────────────────

class LibraryRouter:
    def __init__(self, db: LibraryDatabase):
        self._db = db

    async def create_document(self, doc: DocumentCreate) -> DocumentResponse:
        backend_name = _choose_backend() or LibraryBackend.offline
        guard = _BACKENDS.get(backend_name)
        if guard:
            guard.record()

        ext_result: Optional[Dict[str, Any]] = None
        if backend_name == LibraryBackend.outline:
            ext_result = await _create_outline(doc)
        elif backend_name == LibraryBackend.bookstack:
            ext_result = await _create_bookstack(doc)
        elif backend_name == LibraryBackend.wikijs:
            ext_result = await _create_wikijs(doc)
        else:
            # gollum / dokuwiki / mkdocs / gitea / tiddlywiki / offline
            ext_result = await _offline_create(doc)

        if ext_result is None:
            # backend failed — decay and try next
            if guard:
                guard.decay()
            backend_name = LibraryBackend.offline
            ext_result = await _offline_create(doc)
        else:
            if guard:
                guard.reinforce()

        self._db.record_event(backend_name, ext_result is not None)

        saved = self._db.save_document({
            "doc_id": ext_result["doc_id"],
            "title": doc.title,
            "content": doc.content,
            "format": doc.format.value,
            "collection": doc.collection,
            "tags": doc.tags,
            "metadata": doc.metadata,
            "backend": backend_name,
            "url": ext_result.get("url"),
        })

        return DocumentResponse(
            doc_id=saved["doc_id"],
            title=saved["title"],
            content=saved["content"],
            format=DocumentFormat(saved["format"]),
            collection=saved["collection"],
            tags=saved["tags"],
            metadata=saved["metadata"],
            backend=LibraryBackend(saved["backend"]),
            url=saved.get("url"),
            created_at=saved.get("created_at"),
            updated_at=saved.get("updated_at"),
        )

    async def get_document(self, doc_id: str) -> Optional[DocumentResponse]:
        saved = self._db.get_document(doc_id)
        if not saved:
            return None
        return DocumentResponse(
            doc_id=saved["doc_id"],
            title=saved["title"],
            content=saved["content"],
            format=DocumentFormat(saved["format"]),
            collection=saved["collection"],
            tags=saved["tags"],
            metadata=saved["metadata"],
            backend=LibraryBackend(saved["backend"]),
            url=saved.get("url"),
            created_at=saved.get("created_at"),
            updated_at=saved.get("updated_at"),
        )

    async def search(self, query: str, collection: Optional[str] = None, limit: int = 20) -> SearchResponse:
        backend_name = _choose_backend() or LibraryBackend.offline

        ext_results: Optional[List[Dict[str, Any]]] = None
        if backend_name == LibraryBackend.outline:
            ext_results = await _search_outline(query, collection, limit)
        elif backend_name == LibraryBackend.bookstack:
            ext_results = await _search_bookstack(query, limit)

        if ext_results is not None:
            guard = _BACKENDS.get(backend_name)
            if guard:
                guard.reinforce()
                guard.record()
            results = [
                SearchResult(
                    doc_id=r["doc_id"],
                    title=r["title"],
                    excerpt=r["excerpt"],
                    collection=r.get("collection"),
                    url=r.get("url"),
                    backend=LibraryBackend(backend_name),
                )
                for r in ext_results
            ]
            return SearchResponse(results=results, total=len(results), backend=LibraryBackend(backend_name))

        # Fallback to local SQLite FTS
        local = self._db.search_documents(query, collection, limit)
        results = [
            SearchResult(
                doc_id=r["doc_id"],
                title=r["title"],
                excerpt=r["content"][:300],
                collection=r.get("collection"),
                url=r.get("url"),
                backend=LibraryBackend(r["backend"]),
            )
            for r in local
        ]
        return SearchResponse(results=results, total=len(results), backend=LibraryBackend.offline)

    def status(self) -> LibraryStatus:
        active = _choose_backend() or LibraryBackend.offline
        backend_statuses = []
        for name, guard in _BACKENDS.items():
            calls = guard.calls_in_window()
            backend_statuses.append(BackendStatus(
                name=LibraryBackend(name),
                healthy=guard.pheromone > 0.01,
                pheromone=round(guard.pheromone, 3),
                calls_in_window=calls,
                quota_remaining=max(0, guard.quota - calls),
            ))
        return LibraryStatus(active_backend=LibraryBackend(active), backends=backend_statuses)
