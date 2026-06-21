"""
src/gbrain/pipeline.py — GBrain knowledge-ingestion pipeline.

Ingests agent interactions into the GBrain knowledge graph via GBrainClient,
extracting concepts and relationships using the local extractor module.
Falls back gracefully when GBrain is unavailable.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.gbrain.client import GBrainClient  # noqa: E402 — needed for mock patching

log = logging.getLogger(__name__)

_GBRAIN_URL = "http://localhost:8030"
_PAGERANK_INTERVAL = 50
_pipeline: Optional["GBrainIngestionPipeline"] = None


@dataclass
class AgentInteraction:
    prompt: str
    response: str
    source: str = "tranc3-agent"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def content_hash(self) -> str:
        raw = f"{self.prompt}\n{self.response}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class IngestionResult:
    nodes_created: int = 0
    edges_created: int = 0
    nodes_skipped: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


async def _background_pagerank(url: str) -> None:
    try:
        async with GBrainClient(url) as client:
            await client.trigger_pagerank()
    except Exception as exc:
        log.debug("GBrain PageRank background task failed: %s", exc)


class GBrainIngestionPipeline:
    """
    Six-stage ingestion pipeline:
    1. Extract concepts from prompt + response
    2. Search existing nodes for duplicates
    3. Create new nodes for novel concepts
    4. Create edges between co-occurring concepts
    5. Update interaction counter
    6. Trigger PageRank at configured interval
    """

    def __init__(
        self,
        gbrain_url: str = _GBRAIN_URL,
        pagerank_interval: int = _PAGERANK_INTERVAL,
    ) -> None:
        self._gbrain_url = gbrain_url
        self._pagerank_interval = pagerank_interval
        self._interaction_count: int = 0
        self._total_nodes_created: int = 0
        self._total_edges_created: int = 0

    async def ingest(self, interaction: AgentInteraction) -> IngestionResult:
        t0 = time.monotonic()
        result = IngestionResult()
        try:
            from src.gbrain.extractor import extract as _extract

            result_ex = _extract(interaction.prompt, interaction.response)
            concepts = [c.text for c in result_ex.concepts]

            async with GBrainClient(self._gbrain_url) as client:
                # Stage 2: Find existing nodes
                existing: Dict[str, str] = {}
                for concept in concepts:
                    hits = await client.search(concept)
                    for hit in hits:
                        if hit.get("title", "").lower() == concept.lower():
                            existing[concept] = hit["node_id"]
                            break

                # Stage 3: Create new nodes
                node_ids: Dict[str, str] = dict(existing)
                for concept in concepts:
                    if concept in existing:
                        result.nodes_skipped += 1
                        continue
                    nid = await client.create_node(
                        concept, f"Concept: {concept}", interaction.source
                    )
                    if nid:
                        node_ids[concept] = nid
                        result.nodes_created += 1

                # Stage 4: Create edges between co-occurring concepts
                ids = list(node_ids.values())
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        eid = await client.create_edge(ids[i], ids[j], relation="co-occurs")
                        if eid:
                            result.edges_created += 1

        except Exception as exc:
            log.debug("GBrainIngestionPipeline.ingest error: %s", exc)
            result.error = str(exc)

        # Stage 5: Update counter
        self._interaction_count += 1
        self._total_nodes_created += result.nodes_created
        self._total_edges_created += result.edges_created

        # Stage 6: Trigger PageRank at interval
        if self._interaction_count % self._pagerank_interval == 0:
            asyncio.create_task(_background_pagerank(self._gbrain_url))

        result.duration_ms = (time.monotonic() - t0) * 1000
        return result

    async def ingest_batch(self, interactions: List[AgentInteraction]) -> List[IngestionResult]:
        if not interactions:
            return []
        return [await self.ingest(i) for i in interactions]

    def stats(self) -> Dict[str, Any]:
        return {
            "interactions_ingested": self._interaction_count,
            "total_nodes_created": self._total_nodes_created,
            "total_edges_created": self._total_edges_created,
        }


def get_pipeline(gbrain_url: str = _GBRAIN_URL) -> GBrainIngestionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = GBrainIngestionPipeline(gbrain_url=gbrain_url)
    return _pipeline
