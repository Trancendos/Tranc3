"""
spark_knowledge_tools.py — Knowledge Brain tools for The Spark MCP server.

Registers 8 SparkTool instances exposing KnowledgeBrain (The Library) capabilities:

  Pages:
    - kb_put_page        — create or update a knowledge page
    - kb_get_page        — retrieve a page by ID
    - kb_delete_page     — delete a page by ID
    - kb_list_pages      — list pages with optional source filter

  Search:
    - kb_search          — hybrid BM25 + vector search (RRF fusion)
    - kb_graph_search    — graph-aware search with neighbourhood expansion

  Agent Memory:
    - kb_remember        — store an agent's observation/memory
    - kb_recall          — retrieve relevant memories for an agent

  Stats:
    - kb_stats           — knowledge brain statistics

All handlers are async. KnowledgeBrain is imported lazily so the server
starts cleanly when FAISS or sentence-transformers are absent.

Usage:
    from src.mcp.spark_knowledge_tools import register_knowledge_tools
    register_knowledge_tools(registry)   # registry: SparkToolRegistry
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------

_brain: Any = None


def _get_brain() -> Any:
    global _brain
    if _brain is None:
        from src.knowledge.knowledge_brain import get_brain  # codeql[py/cyclic-import]

        _brain = get_brain()
    return _brain


# ---------------------------------------------------------------------------
# Handler helpers
# ---------------------------------------------------------------------------


def _safe_error(exc: Exception) -> Dict[str, Any]:
    return {"error": str(exc), "ok": False}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _handle_kb_put_page(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create or update a knowledge page."""
    try:
        from src.knowledge.knowledge_brain import KBPage  # codeql[py/cyclic-import]

        brain = _get_brain()
        page_id = params.get("id")
        kwargs: Dict[str, Any] = {
            "title": params["title"],
            "content": params["content"],
            "tags": params.get("tags") or [],
            "source": params.get("source", "manual"),
            "metadata": params.get("metadata") or {},
        }
        if page_id:
            kwargs["id"] = page_id
        page = KBPage(**kwargs)
        stored_id = await brain.put_page(page)
        return {"ok": True, "id": stored_id}
    except Exception as exc:
        logger.exception("kb_put_page error")
        return _safe_error(exc)


async def _handle_kb_get_page(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        brain = _get_brain()
        page = await brain.get_page(params["id"])
        if page is None:
            return {"ok": False, "error": "page not found"}
        return {
            "ok": True,
            "page": {
                "id": page.id,
                "title": page.title,
                "content": page.content,
                "tags": page.tags,
                "source": page.source,
                "created_at": page.created_at,
                "updated_at": page.updated_at,
                "metadata": page.metadata,
            },
        }
    except Exception as exc:
        return _safe_error(exc)


async def _handle_kb_delete_page(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        brain = _get_brain()
        deleted = await brain.delete_page(params["id"])
        return {"ok": deleted, "id": params["id"]}
    except Exception as exc:
        return _safe_error(exc)


async def _handle_kb_list_pages(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        brain = _get_brain()
        source = params.get("source")
        limit = int(params.get("limit", 50))
        pages = await brain.list_pages(source=source, limit=limit)
        return {
            "ok": True,
            "total": len(pages),
            "pages": [
                {
                    "id": p.id,
                    "title": p.title,
                    "tags": p.tags,
                    "source": p.source,
                    "updated_at": p.updated_at,
                }
                for p in pages
            ],
        }
    except Exception as exc:
        return _safe_error(exc)


async def _handle_kb_search(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        brain = _get_brain()
        results = await brain.search(
            query=params["query"],
            top_k=int(params.get("top_k", 10)),
            use_vector=bool(params.get("use_vector", True)),
        )
        return {
            "ok": True,
            "total": len(results),
            "results": [
                {
                    "id": r.page.id,
                    "title": r.page.title,
                    "score": round(r.score, 4),
                    "excerpt": r.excerpt,
                    "tags": r.page.tags,
                }
                for r in results
            ],
        }
    except Exception as exc:
        return _safe_error(exc)


async def _handle_kb_graph_search(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        brain = _get_brain()
        results = await brain.graph_search(
            query=params["query"],
            top_k=int(params.get("top_k", 5)),
            expansion_hops=int(params.get("expansion_hops", 1)),
        )
        return {
            "ok": True,
            "total": len(results),
            "results": [
                {
                    "id": r.page.id,
                    "title": r.page.title,
                    "score": round(r.score, 4),
                    "excerpt": r.excerpt,
                    "tags": r.page.tags,
                }
                for r in results
            ],
        }
    except Exception as exc:
        return _safe_error(exc)


async def _handle_kb_remember(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        brain = _get_brain()
        page_id = await brain.remember(
            agent_id=params["agent_id"],
            content=params["content"],
            tags=params.get("tags"),
            metadata=params.get("metadata"),
        )
        return {"ok": True, "id": page_id}
    except Exception as exc:
        return _safe_error(exc)


async def _handle_kb_recall(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        brain = _get_brain()
        results = await brain.recall(
            agent_id=params["agent_id"],
            query=params["query"],
            top_k=int(params.get("top_k", 5)),
        )
        return {
            "ok": True,
            "total": len(results),
            "memories": [
                {
                    "id": r.page.id,
                    "content": r.page.content,
                    "score": round(r.score, 4),
                    "created_at": r.page.created_at,
                    "metadata": r.page.metadata,
                }
                for r in results
            ],
        }
    except Exception as exc:
        return _safe_error(exc)


async def _handle_kb_stats(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        brain = _get_brain()
        return {"ok": True, **brain.stats()}
    except Exception as exc:
        return _safe_error(exc)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_knowledge_tools(registry: Any) -> int:
    """Register all KnowledgeBrain tools into *registry*. Returns count added."""
    from src.mcp.tools import SparkTool  # codelab[py/cyclic-import]

    tools: List[SparkTool] = [
        SparkTool(
            name="kb_put_page",
            description=(
                "Create or update a page in the Knowledge Brain (The Library). "
                "Supports wikilink syntax [[Target|Label]] in content for automatic "
                "graph edge creation. Returns the stored page ID."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Optional page ID — provide to update an existing page.",
                    },
                    "title": {"type": "string", "description": "Page title."},
                    "content": {
                        "type": "string",
                        "description": "Page content (Markdown supported; [[wikilinks]] auto-wired).",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of tags for categorisation.",
                    },
                    "source": {
                        "type": "string",
                        "description": "Provenance: 'manual' | 'agent' | 'ingestion' | 'dream'.",
                        "default": "manual",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional arbitrary metadata key/value pairs.",
                    },
                },
                "required": ["title", "content"],
            },
            handler=_handle_kb_put_page,
            category="knowledge",
        ),
        SparkTool(
            name="kb_get_page",
            description="Retrieve a Knowledge Brain page by its ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Page ID to retrieve."},
                },
                "required": ["id"],
            },
            handler=_handle_kb_get_page,
            category="knowledge",
        ),
        SparkTool(
            name="kb_delete_page",
            description="Delete a Knowledge Brain page and its associated graph edges.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Page ID to delete."},
                },
                "required": ["id"],
            },
            handler=_handle_kb_delete_page,
            category="knowledge",
        ),
        SparkTool(
            name="kb_list_pages",
            description=(
                "List pages in the Knowledge Brain, optionally filtered by source. "
                "Returns id, title, tags, source, and updated_at for each page."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Filter by source: 'manual', 'agent', 'ingestion', 'dream'.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum pages to return (default 50).",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 500,
                    },
                },
                "required": [],
            },
            handler=_handle_kb_list_pages,
            category="knowledge",
        ),
        SparkTool(
            name="kb_search",
            description=(
                "Hybrid knowledge search using BM25 + FAISS vector retrieval fused via "
                "Reciprocal Rank Fusion (RRF). Returns ranked pages with excerpts. "
                "Set use_vector=false to use BM25 only (faster, no FAISS dependency)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language or keyword query."},
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 10).",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100,
                    },
                    "use_vector": {
                        "type": "boolean",
                        "description": "Whether to include FAISS vector search (default true).",
                        "default": True,
                    },
                },
                "required": ["query"],
            },
            handler=_handle_kb_search,
            category="knowledge",
        ),
        SparkTool(
            name="kb_graph_search",
            description=(
                "Graph-aware knowledge search. Performs hybrid search then expands "
                "results by following knowledge-graph edges for richer context. "
                "expansion_hops controls how many link hops to follow."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language or keyword query."},
                    "top_k": {
                        "type": "integer",
                        "description": "Seed results before expansion (default 5).",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "expansion_hops": {
                        "type": "integer",
                        "description": "Graph hops to expand from seed results (default 1).",
                        "default": 1,
                        "minimum": 0,
                        "maximum": 3,
                    },
                },
                "required": ["query"],
            },
            handler=_handle_kb_graph_search,
            category="knowledge",
        ),
        SparkTool(
            name="kb_remember",
            description=(
                "Store an agent's observation or memory in the Knowledge Brain. "
                "The memory is tagged with agent_id for scoped recall. "
                "Returns the page ID of the stored memory."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier (e.g. 'NXS-01', 'AGT-dorris').",
                    },
                    "content": {
                        "type": "string",
                        "description": "Observation, insight, or fact to remember.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional additional tags.",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional arbitrary metadata (context, task_id, etc.).",
                    },
                },
                "required": ["agent_id", "content"],
            },
            handler=_handle_kb_remember,
            category="knowledge",
        ),
        SparkTool(
            name="kb_recall",
            description=(
                "Retrieve an agent's stored memories relevant to a query. "
                "Scoped to the given agent_id — agents cannot access each other's "
                "private memories unless explicitly tagged cross-agent."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier whose memories to search.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Query to find relevant memories.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of memories to return (default 5).",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["agent_id", "query"],
            },
            handler=_handle_kb_recall,
            category="knowledge",
        ),
        SparkTool(
            name="kb_stats",
            description=(
                "Return statistics for the Knowledge Brain: page count, link count, "
                "BM25 index size, vector index size, dream cycle status, and uptime."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_handle_kb_stats,
            category="knowledge",
        ),
    ]

    for tool in tools:
        registry.register(tool)

    logger.info("Knowledge Brain Spark tools loaded: %d tools registered", len(tools))
    return len(tools)
