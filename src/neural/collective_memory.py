# src/neural/collective_memory.py
"""
Collective Working Memory for Tranc3 Nanoservices.

Provides a shared, decay-based working memory pool that all nanoservices
can read from and write to.  Unlike holographic_memory.py (which provides
tamper-proof, Merkle-tree event logging for audit trails), CollectiveMemory
focuses on *operational* shared state: recent decisions, intermediate
results, and cross-service context that has a natural half-life.

Key concepts
------------
- **MemoryEntry**: A tagged, timestamped value with a decay function.
- **CollectiveMemory**: A bounded LRU + time-decay store with topic-based
  retrieval and reinforcement (entries that are read get their TTL
  extended, mimicking how frequently accessed memories persist).

Zero-cost guarantees
--------------------
- In-process storage (no Redis, no Memcached).
- Configurable capacity with LRU eviction.
- All operations are O(log n) or better.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Data structures ────────────────────────────────────────────────

class MemoryPriority(str, Enum):
    """Priority levels for memory entries."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MemoryEntry:
    """A single entry in the collective working memory.

    Attributes
    ----------
    key : str
        Unique identifier for this memory entry.
    value : Any
        The stored value (must be serializable).
    topic : str
        Topic/category for retrieval filtering.
    priority : MemoryPriority
        Priority affects eviction order and TTL scaling.
    created_at : float
        Monotonic creation timestamp.
    last_accessed : float
        Monotonic last-access timestamp.
    access_count : int
        Number of times this entry has been read.
    ttl : float
        Time-to-live in seconds (0 = no expiry).
    source : str
        Nanoservice that created this entry.
    tags : Set[str]
        Additional tags for flexible retrieval.
    """
    key: str
    value: Any
    topic: str = "general"
    priority: MemoryPriority = MemoryPriority.NORMAL
    created_at: float = field(default_factory=time.monotonic)
    last_accessed: float = field(default_factory=time.monotonic)
    access_count: int = 0
    ttl: float = 3600.0  # 1 hour default
    source: str = ""
    tags: Set[str] = field(default_factory=set)
    # Tracks the original TTL so reinforce() can cap relative to it, not the
    # current (already-extended) TTL which would make the cap drift upward.
    _original_ttl: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        # Store the original TTL for use by reinforce() cap calculation.
        self._original_ttl = self.ttl

    @property
    def is_expired(self) -> bool:
        """Check if this entry has exceeded its effective (priority-scaled) TTL."""
        eff = self.effective_ttl
        if eff <= 0:
            return False
        return (time.monotonic() - self.created_at) > eff

    @property
    def effective_ttl(self) -> float:
        """TTL scaled by priority (higher priority = longer life)."""
        multipliers = {
            MemoryPriority.LOW: 0.5,
            MemoryPriority.NORMAL: 1.0,
            MemoryPriority.HIGH: 2.0,
            MemoryPriority.CRITICAL: 5.0,
        }
        return self.ttl * multipliers.get(self.priority, 1.0)

    @property
    def reinforcement_score(self) -> float:
        """Score based on access frequency and recency.

        Frequently accessed recent entries score higher, mimicking
        how repeatedly recalled memories persist longer.
        """
        age = time.monotonic() - self.created_at
        if age == 0:
            age = 1e-9
        recency = 1.0 / (1.0 + age / 60.0)  # Decay over minutes
        frequency = min(1.0, self.access_count / 10.0)
        return 0.6 * recency + 0.4 * frequency

    def touch(self) -> None:
        """Record an access and extend TTL via reinforcement."""
        self.access_count += 1
        self.last_accessed = time.monotonic()

    def reinforce(self, extension: float = 60.0) -> None:
        """Extend TTL when the entry is reinforced (read/referenced).

        Each reinforcement adds a limited TTL extension, but never
        more than 3x the *original* TTL (not the current mutable TTL,
        which would let the cap drift upward with each reinforcement).
        """
        if self.ttl > 0:
            # Cap is based on the immutable original TTL, not self.ttl
            max_ttl = (self._original_ttl or self.ttl) * 3.0
            self.ttl = min(max_ttl, self.ttl + extension)


# ── Collective Memory ──────────────────────────────────────────────

class CollectiveMemory:
    """Shared, decay-based working memory for nanoservice coordination.

    Parameters
    ----------
    max_entries : int
        Maximum number of entries before LRU eviction kicks in.
    default_ttl : float
        Default time-to-live for new entries (seconds).
    gc_interval : float
        Seconds between garbage-collection sweeps for expired entries.
    reinforcement_extension : float
        Seconds added to TTL when an entry is reinforced.
    """

    def __init__(
        self,
        max_entries: int = 10_000,
        default_ttl: float = 3600.0,
        gc_interval: float = 60.0,
        reinforcement_extension: float = 60.0,
    ) -> None:
        self._entries: OrderedDict[str, MemoryEntry] = OrderedDict()
        self._topic_index: Dict[str, Set[str]] = {}  # topic -> set of keys
        self._tag_index: Dict[str, Set[str]] = {}    # tag -> set of keys
        self._source_index: Dict[str, Set[str]] = {}  # source -> set of keys
        self._max_entries = max_entries
        self._default_ttl = default_ttl
        self._gc_interval = gc_interval
        self._reinforcement_extension = reinforcement_extension
        self._lock = asyncio.Lock()
        self._running = False
        self._gc_task: Optional[asyncio.Task] = None
        self._subscribers: Dict[str, List[Callable]] = {}

    # ── Core operations ────────────────────────────────────────────

    async def store(
        self,
        key: str,
        value: Any,
        topic: str = "general",
        priority: MemoryPriority = MemoryPriority.NORMAL,
        ttl: Optional[float] = None,
        source: str = "",
        tags: Optional[Set[str]] = None,
    ) -> MemoryEntry:
        """Store a value in collective memory.

        If the key already exists, the entry is updated (moved to the
        end of the LRU order).

        Returns
        -------
        MemoryEntry
            The stored entry.
        """
        entry = MemoryEntry(
            key=key,
            value=value,
            topic=topic,
            priority=priority,
            ttl=ttl if ttl is not None else self._default_ttl,
            source=source,
            tags=tags or set(),
        )

        async with self._lock:
            # Remove old entry from indices if overwriting
            if key in self._entries:
                await self._remove_from_indices(key)

            # Evict if at capacity.  Guard against an infinite loop when all
            # remaining entries are CRITICAL (evict_one() is a no-op for them).
            # Collect eviction events to fire *outside* the lock to avoid
            # deadlocking subscriber callbacks that re-acquire the lock.
            eviction_events: list = []  # [(event_type, evicted_entry), ...]
            eviction_attempts = 0
            max_evictions = len(self._entries) + 1
            while len(self._entries) >= self._max_entries:
                prev_size = len(self._entries)
                evicted = await self._evict_one()
                eviction_attempts += 1
                if evicted is not None:
                    # Determine whether it was an expiry or a capacity eviction.
                    eviction_events.append(("evict", evicted))
                if len(self._entries) >= prev_size or eviction_attempts >= max_evictions:
                    # evict_one() did nothing (all CRITICAL) — stop to avoid loop
                    logger.warning(
                        "collective_memory: cannot evict; all %d entries are CRITICAL",
                        len(self._entries),
                    )
                    break

            self._entries[key] = entry
            await self._add_to_indices(entry)

        # Fire eviction notifications outside the lock to avoid deadlocks
        for evt_type, evicted_entry in eviction_events:
            await self._notify(evt_type, evicted_entry)

        # Notify subscribers of the store event
        await self._notify("store", entry)

        logger.debug(
            "collective_memory: stored key=%s topic=%s source=%s",
            key, topic, source,
        )
        return entry

    async def retrieve(self, key: str, reinforce: bool = True) -> Optional[MemoryEntry]:
        """Retrieve an entry by key.

        Parameters
        ----------
        key : str
            The entry key.
        reinforce : bool
            If True, extend the entry's TTL (reinforcement learning).

        Returns
        -------
        MemoryEntry or None
            The entry, or None if not found or expired.
        """
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.is_expired:
                await self._remove_entry(key)
                return None
            # Move to end of LRU
            self._entries.move_to_end(key)
            entry.touch()
            if reinforce:
                entry.reinforce(self._reinforcement_extension)

        return entry

    async def query_by_topic(
        self,
        topic: str,
        limit: int = 50,
    ) -> List[MemoryEntry]:
        """Retrieve all entries for a given topic, sorted by reinforcement score."""
        keys = self._topic_index.get(topic, set())
        entries: List[MemoryEntry] = []
        async with self._lock:
            for key in keys:
                entry = self._entries.get(key)
                if entry and not entry.is_expired:
                    entries.append(entry)
        entries.sort(key=lambda e: -e.reinforcement_score)
        return entries[:limit]

    async def query_by_tag(
        self,
        tag: str,
        limit: int = 50,
    ) -> List[MemoryEntry]:
        """Retrieve all entries with a given tag."""
        keys = self._tag_index.get(tag, set())
        entries: List[MemoryEntry] = []
        async with self._lock:
            for key in keys:
                entry = self._entries.get(key)
                if entry and not entry.is_expired:
                    entries.append(entry)
        entries.sort(key=lambda e: -e.reinforcement_score)
        return entries[:limit]

    async def query_by_source(
        self,
        source: str,
        limit: int = 50,
    ) -> List[MemoryEntry]:
        """Retrieve all entries from a given source nanoservice."""
        keys = self._source_index.get(source, set())
        entries: List[MemoryEntry] = []
        async with self._lock:
            for key in keys:
                entry = self._entries.get(key)
                if entry and not entry.is_expired:
                    entries.append(entry)
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries[:limit]

    async def delete(self, key: str) -> bool:
        """Delete an entry by key. Returns True if the entry existed."""
        async with self._lock:
            if key in self._entries:
                await self._remove_entry(key)
                return True
            return False

    async def clear(self, topic: Optional[str] = None) -> int:
        """Clear entries, optionally filtered by topic.

        Returns the number of entries removed.
        """
        removed = 0
        async with self._lock:
            if topic:
                keys = list(self._topic_index.get(topic, set()))
                for key in keys:
                    await self._remove_entry(key)
                    removed += 1
            else:
                count = len(self._entries)
                self._entries.clear()
                self._topic_index.clear()
                self._tag_index.clear()
                self._source_index.clear()
                removed = count
        return removed

    # ── Subscription / notification ────────────────────────────────

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe to memory events ('store', 'evict', 'expire').

        Handler signature: async handler(event_type: str, entry: MemoryEntry)
        """
        self._subscribers.setdefault(event_type, []).append(handler)

    async def _notify(self, event_type: str, entry: MemoryEntry) -> None:
        """Notify subscribers of a memory event."""
        for handler in self._subscribers.get(event_type, []):
            try:
                result = handler(event_type, entry)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.error("collective_memory: subscriber error: %s", exc)

    # ── Index management ───────────────────────────────────────────

    async def _add_to_indices(self, entry: MemoryEntry) -> None:
        """Add entry to all indices. Must be called under lock."""
        self._topic_index.setdefault(entry.topic, set()).add(entry.key)
        for tag in entry.tags:
            self._tag_index.setdefault(tag, set()).add(entry.key)
        if entry.source:
            self._source_index.setdefault(entry.source, set()).add(entry.key)

    async def _remove_from_indices(self, key: str) -> None:
        """Remove entry from all indices. Must be called under lock."""
        entry = self._entries.get(key)
        if entry is None:
            return
        topic_keys = self._topic_index.get(entry.topic)
        if topic_keys:
            topic_keys.discard(key)
            if not topic_keys:
                del self._topic_index[entry.topic]
        for tag in entry.tags:
            tag_keys = self._tag_index.get(tag)
            if tag_keys:
                tag_keys.discard(key)
                if not tag_keys:
                    del self._tag_index[tag]
        if entry.source:
            src_keys = self._source_index.get(entry.source)
            if src_keys:
                src_keys.discard(key)
                if not src_keys:
                    del self._source_index[entry.source]

    async def _remove_entry(self, key: str) -> None:
        """Remove an entry and its indices. Must be called under lock."""
        await self._remove_from_indices(key)
        del self._entries[key]

    # ── Eviction ───────────────────────────────────────────────────

    async def _evict_one(self) -> Optional["MemoryEntry"]:
        """Evict the lowest-priority, least-recently-used entry.

        Must be called under lock.  Returns the evicted entry (with its event
        type) so the caller can fire subscriber notifications *outside* the lock,
        avoiding potential deadlocks.  Returns None when nothing was evicted
        (e.g. only CRITICAL entries remain).

        Entries are evicted in order:
        1. Expired entries (oldest first)
        2. LOW priority LRU
        3. NORMAL priority LRU
        4. HIGH priority LRU
        CRITICAL entries are never auto-evicted.
        """
        # First pass: evict any expired entry
        for key, entry in self._entries.items():
            if entry.is_expired:
                await self._remove_entry(key)
                return entry  # Caller will fire "expire" notification

        # Second pass: evict by priority (LOW first) then LRU
        for priority in (MemoryPriority.LOW, MemoryPriority.NORMAL, MemoryPriority.HIGH):
            for key, entry in self._entries.items():
                if entry.priority == priority:
                    await self._remove_entry(key)
                    return entry  # Caller will fire "evict" notification

        # If only CRITICAL entries remain, do not evict
        logger.warning("collective_memory: at capacity with only CRITICAL entries")
        return None

    # ── Garbage collection ─────────────────────────────────────────

    async def start(self) -> None:
        """Start the background GC task."""
        if self._running:
            return
        self._running = True
        self._gc_task = asyncio.create_task(self._gc_loop())
        logger.info("collective_memory: started (max=%d, ttl=%.0fs)", self._max_entries, self._default_ttl)

    async def stop(self) -> None:
        """Stop the background GC task."""
        self._running = False
        if self._gc_task and not self._gc_task.done():
            self._gc_task.cancel()
        logger.info("collective_memory: stopped")

    async def _gc_loop(self) -> None:
        """Periodically remove expired entries."""
        while self._running:
            await asyncio.sleep(self._gc_interval)
            await self.collect_garbage()

    async def collect_garbage(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        removed = 0
        expired_entries: list = []
        async with self._lock:
            expired_keys = [k for k, e in self._entries.items() if e.is_expired]
            for key in expired_keys:
                entry = self._entries[key]
                await self._remove_entry(key)
                expired_entries.append(entry)
                removed += 1
        # Fire notifications outside the lock to prevent subscriber deadlocks
        for entry in expired_entries:
            await self._notify("expire", entry)
        if removed:
            logger.debug("collective_memory: GC removed %d expired entries", removed)
        return removed

    # ── Statistics ─────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Return statistics about the collective memory."""
        active = sum(1 for e in self._entries.values() if not e.is_expired)
        by_priority: Dict[str, int] = {}
        by_topic: Dict[str, int] = {}
        for entry in self._entries.values():
            if entry.is_expired:
                continue
            by_priority[entry.priority.value] = by_priority.get(entry.priority.value, 0) + 1
            by_topic[entry.topic] = by_topic.get(entry.topic, 0) + 1
        return {
            "total_entries": len(self._entries),
            "active_entries": active,
            "topics": by_topic,
            "priorities": by_priority,
            "max_entries": self._max_entries,
            "utilization": len(self._entries) / self._max_entries if self._max_entries else 0,
        }

    def fingerprint(self, entry: MemoryEntry) -> str:
        """Compute a content fingerprint for deduplication checks."""
        content = f"{entry.key}:{entry.topic}:{entry.value}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
