# FID: TRANC3-GBRAIN-004 | Version: 1.0.0 | Module: gbrain
"""
src/gbrain/pipeline.py — GBrain ingestion pipeline.

Consumes agent interactions (prompt + response) and syncs extracted knowledge
into the GBrain bridge (The Library / Zimik).  Designed to run as a background
task in FastAPI so the hot path (inference) is never blocked.

Pipeline stages:
  1. Extract — pull concepts, entities, edges from the text pair
  2. Deduplicate — search GBrain for existing similar nodes; skip duplicates
  3. Ingest — create new nodes + edges via GBrainClient
  4. Consolidate — periodically trigger knowledge consolidation + PageRank

Zero-cost: pure Python extraction, httpx for GBrain calls.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.gbrain.client import GBrainClient
from src.gbrain.extractor import ExtractionResult, extract

logger = logging.getLogger(__name__)

# Minimum salience for a concept to be promoted to a GBrain node
_MIN_NODE_SALIENCE = 0.4

# Minimum co-occurrence weight for an edge to be persisted
_MIN_EDGE_WEIGHT = 0.3

# How many interactions between automatic PageRank recomputes
_PAGERANK_RECOMPUTE_INTERVAL = 50


@dataclass
class AgentInteraction:
    """Represents a single agent prompt/response pair to be ingested."""

    prompt: str
    response: str
    source: str = "tranc3-agent"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def content_hash(self) -> str:
        """Stable hash of the interaction content for deduplication."""
        raw = f"{self.prompt.strip()}\n{self.response.strip()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class IngestionResult:
    """Result of a single ingestion run."""

    nodes_created: int = 0
    edges_created: int = 0
    nodes_skipped: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


class GBrainIngestionPipeline:
    """
    Background pipeline that ingests agent interactions into GBrain.

    Thread-safe: all mutations go through the async GBrainClient.
    The pipeline is designed to be fire-and-forget from route handlers::

        pipeline = GBrainIngestionPipeline()

        @app.post("/generate")
        async def generate(body: GenerateRequest):
            result = await engine.generate(body.prompt)
            asyncio.create_task(
                pipeline.ingest(AgentInteraction(
                    prompt=body.prompt,
                    response=result,
                    source="luminous-generate",
                ))
            )
            return result
    """

    def __init__(
        self,
        gbrain_url: str = "http://localhost:8030",
        min_node_salience: float = _MIN_NODE_SALIENCE,
        min_edge_weight: float = _MIN_EDGE_WEIGHT,
        pagerank_interval: int = _PAGERANK_RECOMPUTE_INTERVAL,
    ) -> None:
        self._gbrain_url = gbrain_url
        self._min_node_salience = min_node_salience
        self._min_edge_weight = min_edge_weight
        self._pagerank_interval = pagerank_interval
        self._interaction_count = 0
        self._total_nodes = 0
        self._total_edges = 0

    # ── Public API ────────────────────────────────────────────────────────────

    async def ingest(self, interaction: AgentInteraction) -> IngestionResult:
        """
        Ingest a single agent interaction into GBrain.

        Safe to call from asyncio.create_task() — all exceptions are caught
        and returned in IngestionResult.error so the caller is never disrupted.
        """
        t0 = time.monotonic()
        result = IngestionResult()
        try:
            async with GBrainClient(self._gbrain_url) as client:
                result = await self._run(client, interaction)
        except Exception as exc:
            logger.warning("gbrain.pipeline ingest error: %s", exc)
            result.error = str(exc)
        result.duration_ms = round((time.monotonic() - t0) * 1000, 2)
        if result.ok:
            logger.debug(
                "gbrain.pipeline ingested interaction nodes=%d edges=%d skipped=%d ms=%.1f",
                result.nodes_created,
                result.edges_created,
                result.nodes_skipped,
                result.duration_ms,
            )
        return result

    async def ingest_batch(self, interactions: List[AgentInteraction]) -> List[IngestionResult]:
        """Ingest a batch of interactions concurrently."""
        return list(await asyncio.gather(*[self.ingest(i) for i in interactions]))

    def stats(self) -> Dict[str, Any]:
        """Return pipeline statistics."""
        return {
            "interactions_ingested": self._interaction_count,
            "total_nodes_created": self._total_nodes,
            "total_edges_created": self._total_edges,
        }

    # ── Internal pipeline stages ──────────────────────────────────────────────

    async def _run(self, client: GBrainClient, interaction: AgentInteraction) -> IngestionResult:
        result = IngestionResult()

        # Stage 1: Extract
        extraction: ExtractionResult = extract(interaction.prompt, interaction.response)
        if not extraction.concepts:
            return result  # nothing to ingest

        # Stage 2: Filter by salience
        worthy_concepts = [c for c in extraction.concepts if c.score >= self._min_node_salience]
        if not worthy_concepts:
            return result

        # Stage 3: Deduplicate — search for existing nodes
        seen_titles: Dict[str, str] = {}  # title.lower() → existing node_id

        dedup_query = " ".join(c.text for c in worthy_concepts[:5])
        existing = await client.search(dedup_query, max_results=20, use_graph_expansion=False)
        for node in existing:
            title_key = node.get("title", "").lower().strip()
            if title_key:
                seen_titles[title_key] = node.get("node_id", "")

        # Stage 4: Create nodes for new concepts
        node_ids: Dict[str, str] = {}  # concept_text → node_id

        interaction_meta = {
            "content_hash": interaction.content_hash(),
            "source": interaction.source,
            **({"user_id": interaction.user_id} if interaction.user_id else {}),
            **({"session_id": interaction.session_id} if interaction.session_id else {}),
            **interaction.metadata,
        }

        for concept in worthy_concepts:
            key = concept.text.lower().strip()
            if key in seen_titles:
                node_ids[concept.text] = seen_titles[key]
                result.nodes_skipped += 1
                continue

            # Build node content from surrounding sentences
            content_sentences = [
                extraction.summary,
                concept.text,
            ]
            content = " — ".join(dict.fromkeys(content_sentences))[:500]

            node_id = await client.create_node(
                title=concept.text,
                content=content,
                source=interaction.source,
                tags=extraction.tags[:3],
                metadata=interaction_meta,
                importance=concept.score,
            )
            if node_id:
                node_ids[concept.text] = node_id
                seen_titles[key] = node_id
                result.nodes_created += 1

        # Stage 5: Create edges from co-occurrence + prompt→response relationship
        for edge in extraction.edges:
            if edge.weight < self._min_edge_weight:
                continue
            src_id = node_ids.get(edge.source)
            tgt_id = node_ids.get(edge.target)
            if src_id and tgt_id and src_id != tgt_id:
                eid = await client.create_edge(
                    src_id, tgt_id, relation=edge.relation, weight=edge.weight
                )
                if eid:
                    result.edges_created += 1

        # Stage 6: Trigger PageRank recompute periodically
        self._interaction_count += 1
        self._total_nodes += result.nodes_created
        self._total_edges += result.edges_created

        if self._interaction_count % self._pagerank_interval == 0:
            asyncio.create_task(_background_pagerank(self._gbrain_url))

        return result


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------


async def _background_pagerank(gbrain_url: str) -> None:
    """Fire-and-forget PageRank recompute triggered after N interactions."""
    try:
        async with GBrainClient(gbrain_url) as client:
            ok = await client.recompute_pagerank()
            if ok:
                logger.info("gbrain.pipeline: background PageRank recompute complete")
    except Exception as exc:
        logger.debug("gbrain.pipeline: background PageRank failed: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton (lazy, created on first use)
# ---------------------------------------------------------------------------

_pipeline: Optional[GBrainIngestionPipeline] = None


def get_pipeline(gbrain_url: str = "http://localhost:8030") -> GBrainIngestionPipeline:
    """Return the module-level pipeline singleton, creating it on first call."""
    global _pipeline
    if _pipeline is None:
        _pipeline = GBrainIngestionPipeline(gbrain_url=gbrain_url)
    return _pipeline
