"""
memory_stream.py — Episodic Agent Memory for Tranc3 Platform (Phase 5)

Provides a time-ordered stream of episodic memories for an autonomous agent,
with three-factor scoring for retrieval:

  1. Recency:  exponential decay based on time elapsed since the memory
               was created. Recent memories score higher.
  2. Relevance: keyword / tag overlap between the query and the memory's
               content and tags. Topically related memories score higher.
  3. Importance: a fixed score (0.0–1.0) assigned when the memory is created,
               reflecting the agent's assessment of the memory's significance.

The combined score determines retrieval order. This mirrors the generative
agents architecture (Park et al., 2023) adapted for in-process use.

Capacity-bounded: when the stream exceeds capacity, the oldest, lowest-
importance memories are evicted first.

Zero-cost: pure Python, no external dependencies or vector databases.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recency decay constant
# ---------------------------------------------------------------------------

# Exponential decay half-life in seconds. After this much time, a memory's
# recency score drops to 50%. Default: 1 hour.
_RECENCY_HALF_LIFE_SEC = 3600.0


# ---------------------------------------------------------------------------
# Episodic memory entry
# ---------------------------------------------------------------------------


@dataclass
class EpisodicMemory:
    """
    A single episodic memory entry in an agent's memory stream.

    Each memory has:
      - content: the textual description of what happened
      - tags: categorical tags for relevance matching
      - importance: fixed significance score (0.0–1.0)
      - timestamp: when the memory was created
      - metadata: arbitrary structured data attached to the memory
    """

    memory_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    content: str = ""
    tags: Set[str] = field(default_factory=set)
    importance: float = 0.5
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    access_count: int = 0
    last_accessed: Optional[float] = None

    def recency_score(self, now: Optional[float] = None) -> float:
        """
        Compute the recency score using exponential decay.
        Returns a value in [0, 1] where 1 = just created, 0 = infinitely old.
        """
        now = now or time.time()
        elapsed = now - self.timestamp
        # exponential decay: score = 0.5^(elapsed / half_life)
        return 0.5 ** (elapsed / _RECENCY_HALF_LIFE_SEC)

    def relevance_score(self, query: str, query_tags: Optional[Set[str]] = None) -> float:
        """
        Compute relevance based on keyword overlap and tag overlap.
        Returns a value in [0, 1].
        """
        if not query and not query_tags:
            return 0.0

        scores: List[float] = []

        # Keyword overlap: tokenize query and content, compute Jaccard
        if query:
            query_tokens = set(query.lower().split())
            content_tokens = set(self.content.lower().split())
            if query_tokens and content_tokens:
                intersection = query_tokens & content_tokens
                union = query_tokens | content_tokens
                scores.append(len(intersection) / len(union))

        # Tag overlap
        if query_tags and self.tags:
            intersection = query_tags & self.tags
            union = query_tags | self.tags
            scores.append(len(intersection) / len(union))

        return max(scores) if scores else 0.0

    def combined_score(
        self,
        query: str = "",
        query_tags: Optional[Set[str]] = None,
        now: Optional[float] = None,
        w_recency: float = 1.0,
        w_relevance: float = 1.0,
        w_importance: float = 1.0,
    ) -> float:
        """
        Weighted combination of recency, relevance, and importance.
        Default weights give equal consideration to all three factors.
        """
        r = self.recency_score(now)
        rel = self.relevance_score(query, query_tags)
        imp = max(0.0, min(1.0, self.importance))
        total_weight = w_recency + w_relevance + w_importance
        if total_weight == 0:
            return 0.0
        return (w_recency * r + w_relevance * rel + w_importance * imp) / total_weight

    def touch(self) -> None:
        """Mark this memory as accessed (increment access count, update last_accessed)."""
        self.access_count += 1
        self.last_accessed = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the memory to a plain dict."""
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "tags": sorted(self.tags),
            "importance": self.importance,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "recency": round(self.recency_score(), 4),
        }


# ---------------------------------------------------------------------------
# Memory Stream
# ---------------------------------------------------------------------------


class MemoryStream:
    """
    Time-ordered stream of episodic memories for an autonomous agent.

    Supports:
      - Adding new memories with importance scores
      - Retrieving memories by combined recency/relevance/importance
      - Capacity-bounded eviction (LRU + low-importance first)
      - Time-range queries
      - Tag-based filtering

    Usage:
        stream = MemoryStream(capacity=500)
        mid = await stream.add("Completed code review", tags={"code", "review"}, importance=0.7)
        relevant = await stream.retrieve("code review", top_k=5)
    """

    def __init__(
        self,
        capacity: int = 500,
        recency_half_life_sec: float = _RECENCY_HALF_LIFE_SEC,
    ) -> None:
        self._memories: Dict[str, EpisodicMemory] = {}
        self._time_index: List[str] = []  # ordered by timestamp
        self._capacity = capacity
        self._recency_half_life = recency_half_life_sec
        self._lock = asyncio.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def count(self) -> int:
        return len(self._memories)

    # -------------------------------------------------------------------
    # Add / Remove
    # -------------------------------------------------------------------

    async def add(
        self,
        content: str,
        tags: Optional[Set[str]] = None,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add a new episodic memory. Returns the memory ID.

        If the stream exceeds capacity, the oldest low-importance memories
        are evicted to make room.
        """
        async with self._lock:
            memory = EpisodicMemory(
                content=content,
                tags=tags or set(),
                importance=max(0.0, min(1.0, importance)),
                metadata=metadata or {},
            )
            self._memories[memory.memory_id] = memory
            self._time_index.append(memory.memory_id)

            # Evict if over capacity
            while len(self._memories) > self._capacity:
                self._evict_one()

            logger.debug(
                "Memory added: %s (importance=%.2f, tags=%s)",
                content[:60], importance, tags,
            )
            return memory.memory_id

    async def remove(self, memory_id: str) -> bool:
        """Remove a specific memory by ID."""
        async with self._lock:
            if memory_id in self._memories:
                del self._memories[memory_id]
                self._time_index = [m for m in self._time_index if m != memory_id]
                return True
            return False

    # -------------------------------------------------------------------
    # Retrieval
    # -------------------------------------------------------------------

    async def retrieve(
        self,
        query: str = "",
        query_tags: Optional[Set[str]] = None,
        top_k: int = 10,
        w_recency: float = 1.0,
        w_relevance: float = 1.0,
        w_importance: float = 1.0,
    ) -> List[EpisodicMemory]:
        """
        Retrieve the top-k most relevant memories based on combined scoring.

        If no query or tags are provided, returns the most recent memories.
        """
        async with self._lock:
            if not self._memories:
                return []

            now = time.time()

            # Score all memories
            scored: List[tuple[float, EpisodicMemory]] = []
            for memory in self._memories.values():
                score = memory.combined_score(
                    query=query,
                    query_tags=query_tags,
                    now=now,
                    w_recency=w_recency,
                    w_relevance=w_relevance,
                    w_importance=w_importance,
                )
                scored.append((score, memory))

            # Sort by score descending
            scored.sort(key=lambda x: -x[0])

            # Return top-k, touching each for access tracking
            results = []
            for score, memory in scored[:top_k]:
                memory.touch()
                results.append(memory)

            return results

    async def get_by_tags(self, tags: Set[str], top_k: int = 20) -> List[EpisodicMemory]:
        """Retrieve memories that match any of the given tags, sorted by recency."""
        async with self._lock:
            matching = [
                m for m in self._memories.values()
                if m.tags & tags
            ]
            matching.sort(key=lambda m: -m.timestamp)
            return matching[:top_k]

    async def get_by_time_range(
        self,
        start: float,
        end: Optional[float] = None,
        top_k: int = 50,
    ) -> List[EpisodicMemory]:
        """Retrieve memories within a time range [start, end], sorted by timestamp."""
        async with self._lock:
            end = end or time.time()
            matching = [
                m for m in self._memories.values()
                if start <= m.timestamp <= end
            ]
            matching.sort(key=lambda m: -m.timestamp)
            return matching[:top_k]

    async def get_recent(self, count: int = 10) -> List[EpisodicMemory]:
        """Return the N most recent memories."""
        async with self._lock:
            sorted_memories = sorted(
                self._memories.values(), key=lambda m: -m.timestamp
            )
            return sorted_memories[:count]

    async def get(self, memory_id: str) -> Optional[EpisodicMemory]:
        """Get a specific memory by ID."""
        return self._memories.get(memory_id)

    # -------------------------------------------------------------------
    # Reflection
    # -------------------------------------------------------------------

    async def reflect(self, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Generate a reflection over recent high-importance memories.
        Returns the top-k memories by combined score, serialized.
        This is used by the agent's REFLECTING state to synthesize insights.
        """
        memories = await self.retrieve(
            query="",
            top_k=top_k,
            w_recency=1.5,   # weight recency more for reflection
            w_relevance=0.5,
            w_importance=2.0, # weight importance more for reflection
        )
        return [m.to_dict() for m in memories]

    # -------------------------------------------------------------------
    # Queries
    # -------------------------------------------------------------------

    async def get_summary(self) -> Dict[str, Any]:
        """Return a summary of the memory stream."""
        async with self._lock:
            if not self._memories:
                return {
                    "total": 0,
                    "capacity": self._capacity,
                    "utilization": 0.0,
                    "tag_counts": {},
                }

            tag_counts: Dict[str, int] = {}
            for memory in self._memories.values():
                for tag in memory.tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

            return {
                "total": len(self._memories),
                "capacity": self._capacity,
                "utilization": round(len(self._memories) / self._capacity, 4),
                "avg_importance": round(
                    sum(m.importance for m in self._memories.values()) / len(self._memories), 4
                ),
                "tag_counts": dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:20]),
                "oldest_timestamp": min(m.timestamp for m in self._memories.values()),
                "newest_timestamp": max(m.timestamp for m in self._memories.values()),
            }

    async def get_all(self) -> List[Dict[str, Any]]:
        """Return serialized representations of all memories, sorted by timestamp."""
        async with self._lock:
            sorted_memories = sorted(
                self._memories.values(), key=lambda m: m.timestamp
            )
            return [m.to_dict() for m in sorted_memories]

    # -------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------

    def _evict_one(self) -> None:
        """
        Evict the oldest, lowest-importance memory.
        Prioritizes evicting: least important → oldest.
        """
        if not self._memories:
            return

        # Find candidate: lowest importance, oldest timestamp
        candidates = list(self._memories.values())
        candidates.sort(key=lambda m: (m.importance, m.timestamp))
        victim = candidates[0]
        del self._memories[victim.memory_id]
        self._time_index = [m for m in self._time_index if m != victim.memory_id]
        logger.debug("Evicted memory: %s (importance=%.2f)", victim.memory_id, victim.importance)
