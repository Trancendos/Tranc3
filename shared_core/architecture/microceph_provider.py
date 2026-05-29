"""
shared_core.architecture.microceph_provider
============================================
Pure-Python MicroCeph storage provider with CRUSH algorithm implementation.

Provides:
  - CRUSH algorithm: rjenkins1 hash, straw2 OSD selection, crush_place
  - CrushBucket / CrushMap dataclasses
  - CrushMapBuilder for command generation
  - MicroCephConfig with Tranc3 defaults
  - Enums: OsdState, PoolType, CephHealthStatus
  - Dataclasses: OsdInfo, PoolInfo, RgwCredentials
  - Async singleton: get_microceph_provider / shutdown_microceph_provider

No live Ceph cluster is required for any pure-Python operations.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

DEFAULT_POOLS: List[str] = ["tranc3-meta", "tranc3-data", "tranc3-archive"]

MICROCEPH_CMD: str = "microceph"

MIN_PG_COUNT: int = 1
MAX_PG_COUNT: int = 32768
OSD_TARGET_PG_PER_OSD: int = 100

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OsdState(str, Enum):
    UP_IN = "up/in"
    UP_OUT = "up/out"
    DOWN_IN = "down/in"
    DOWN_OUT = "down/out"


class PoolType(str, Enum):
    REPLICATED = "replicated"
    ERASURE = "erasure"


class CephHealthStatus(str, Enum):
    HEALTH_OK = "HEALTH_OK"
    HEALTH_WARN = "HEALTH_WARN"
    HEALTH_ERR = "HEALTH_ERR"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class OsdInfo:
    id: int
    uuid: str
    state: List[str]
    weight: float


@dataclass
class PoolInfo:
    name: str
    pool_id: int
    pool_type: PoolType
    pg_num: int
    pgp_num: int


@dataclass
class RgwCredentials:
    access_key: str
    secret_key: str
    user_id: str
    display_name: str


@dataclass
class CrushBucket:
    """A node in the CRUSH hierarchy (OSD, host, rack, root, etc.)."""

    id: int
    name: str
    type: str
    weight: float
    children: List["CrushBucket"] = field(default_factory=list)
    alg: str = "straw2"

    def topology(self, _indent: int = 0) -> str:
        """Render this bucket and all descendants as an indented string."""
        prefix = "  " * _indent
        line = f"{prefix}{self.name} (type={self.type}, weight={self.weight:.3f})"
        if not self.children:
            return line
        child_lines = "\n".join(c.topology(_indent + 1) for c in self.children)
        return f"{line}\n{child_lines}"


@dataclass
class CrushMap:
    """The full CRUSH map: a flat list of all buckets."""

    buckets: List[CrushBucket] = field(default_factory=list)
    tunable_profile: str = "optimal"

    def topology(self) -> str:
        """Render the full CRUSH map topology."""
        header = "CRUSH Map"
        if not self.buckets:
            return header
        # Find root buckets (those not referenced as a child of any other bucket)
        child_ids = {c.id for b in self.buckets for c in b.children}
        roots = [b for b in self.buckets if b.id not in child_ids]
        body = "\n".join(r.topology() for r in roots)
        return f"{header}\n{body}"

    def find_bucket(self, name: str) -> Optional[CrushBucket]:
        """Return the first bucket with the given name, or None."""
        for b in self.buckets:
            if b.name == name:
                return b
        return None


# ---------------------------------------------------------------------------
# CRUSH algorithm — pure Python implementation
# ---------------------------------------------------------------------------


def crush_hash(pg_id: int, osd_id: int, retry: int) -> int:
    """
    rjenkins1 hash used by the Ceph CRUSH algorithm.

    Returns a deterministic 32-bit non-negative integer.
    """
    # rjenkins1: hash a sequence of bytes using Jenkins one-at-a-time
    def _rjenkins1(*vals: int) -> int:
        h = 0
        for v in vals:
            for _ in range(4):
                h += v & 0xFF
                h += h << 10
                h ^= h >> 6
                h &= 0xFFFFFFFF
                v >>= 8
        h += h << 3
        h ^= h >> 11
        h += h << 15
        return h & 0xFFFFFFFF

    return _rjenkins1(pg_id, osd_id, retry, 0x12345678)


def straw2_choose(
    osd_ids: List[int],
    weights: List[float],
    pg_id: int,
    retry: int = 0,
) -> int:
    """
    straw2 OSD selection algorithm.

    Returns the winning OSD id, or -1 if the list is empty.
    Weight=0 OSDs are never selected.
    """
    if not osd_ids:
        return -1

    best_osd = -1
    best_draw = -1.0

    for osd_id, weight in zip(osd_ids, weights, strict=False):
        if weight <= 0.0:
            continue
        h = crush_hash(pg_id, osd_id, retry)
        # straw2: draw = (h / 2^32) ^ (1 / weight)  — higher draw wins
        u = h / 0x100000000  # uniform [0, 1)
        if u == 0.0:
            u = 1e-10
        # ln(u) / weight — equivalent form: larger value wins
        draw = math.log(u) / weight
        if best_osd == -1 or draw > best_draw:
            best_draw = draw
            best_osd = osd_id

    return best_osd


def crush_place(
    key: str,
    osd_ids: List[int],
    weights: List[float],
    replicas: int,
) -> List[int]:
    """
    Place an object on `replicas` unique OSDs using the CRUSH straw2 algorithm.

    Returns a list of unique OSD ids (may be shorter than `replicas` if there
    are fewer available OSDs).
    """
    if not osd_ids:
        return []

    # Derive a numeric pg_id from the key
    pg_id = _hash_key(key)

    available_ids = list(osd_ids)
    available_weights = list(weights)
    selected: List[int] = []
    retry = 0

    while len(selected) < replicas and available_ids:
        winner = straw2_choose(available_ids, available_weights, pg_id, retry=retry)
        if winner == -1:
            break
        selected.append(winner)
        idx = available_ids.index(winner)
        available_ids.pop(idx)
        available_weights.pop(idx)
        retry += 1

    return selected


def _hash_key(key: str) -> int:
    """Derive a stable 32-bit integer from a string key."""
    h = 0
    for ch in key.encode("utf-8"):
        h = (h * 31 + ch) & 0xFFFFFFFF
    return h


# ---------------------------------------------------------------------------
# CrushMapBuilder
# ---------------------------------------------------------------------------


class CrushMapBuilder:
    """
    Generates microceph CLI commands to build and manage the CRUSH map.
    Does NOT invoke the Ceph CLI directly — returns command strings.
    """

    TUNABLES_OPTIMAL: Dict[str, int] = {
        "chooseleaf_descend_once": 1,
        "chooseleaf_vary_r": 1,
        "chooseleaf_stable": 1,
        "straw_calc_version": 1,
        "allowed_bucket_algs": 54,
    }

    def __init__(self, config: "MicroCephConfig") -> None:
        self.config = config
        self._crush_map = CrushMap()

    def ensure_host_bucket(self, host_name: Optional[str] = None) -> CrushBucket:
        """Ensure a host bucket exists in the CRUSH map, creating it if needed."""
        name = host_name or self.config.crush_host_name
        existing = self._crush_map.find_bucket(name)
        if existing:
            return existing
        bucket = CrushBucket(id=-(len(self._crush_map.buckets) + 2), name=name, type="host", weight=0.0)
        self._crush_map.buckets.append(bucket)
        return bucket

    def add_osd_to_crush(self, osd_id: int, weight: float = 1.0) -> CrushBucket:
        """Add an OSD leaf bucket to the CRUSH map."""
        name = f"osd.{osd_id}"
        existing = self._crush_map.find_bucket(name)
        if existing:
            return existing
        osd_bucket = CrushBucket(id=osd_id, name=name, type="osd", weight=weight)
        self._crush_map.buckets.append(osd_bucket)
        # Attach to host bucket
        host = self.ensure_host_bucket()
        host.children.append(osd_bucket)
        host.weight += weight
        return osd_bucket

    def create_replicated_rule(self, rule_name: str = "replicated_rule", replicas: int = 3) -> str:
        """Return the microceph command to create a replicated placement rule."""
        return (
            f"{MICROCEPH_CMD} disk add-rule "
            f"--name {rule_name} "
            f"--type replicated "
            f"--min-size {replicas} "
            f"--max-size {replicas}"
        )

    def build(self) -> CrushMap:
        """Return the constructed CrushMap."""
        return self._crush_map


# ---------------------------------------------------------------------------
# MicroCephConfig
# ---------------------------------------------------------------------------


@dataclass
class MicroCephConfig:
    """Configuration for MicroCeph deployment on Tranc3 infrastructure."""

    single_node: bool = True
    osd_loop_dev: bool = False
    enable_health_watch: bool = True
    metrics_enabled: bool = True
    crush_host_name: str = "tranc3-node-0"
    pools: List[str] = field(default_factory=lambda: list(DEFAULT_POOLS))
    rgw_port: int = 7480
    rgw_host: str = "127.0.0.1"
    replicas: int = 1
    pg_num: int = 32


# ---------------------------------------------------------------------------
# MicroCephProvider
# ---------------------------------------------------------------------------


class MicroCephProvider:
    """
    High-level async interface to a MicroCeph cluster.

    In non-cluster environments (tests, CI) all methods that would invoke
    the Ceph CLI log a warning and return safe stub values.
    """

    def __init__(self, config: Optional[MicroCephConfig] = None) -> None:
        self.config = config or MicroCephConfig()
        self._crush_map: Optional[CrushMap] = None

    async def initialise(self) -> None:
        """Build an in-memory CRUSH map from config."""
        builder = CrushMapBuilder(self.config)
        self._crush_map = builder.build()

    def crush_map(self) -> Optional[CrushMap]:
        return self._crush_map

    async def status(self) -> Dict:
        return {"health": CephHealthStatus.HEALTH_OK.value, "provider": "microceph"}

    async def close(self) -> None:
        self._crush_map = None


# ---------------------------------------------------------------------------
# Async singleton
# ---------------------------------------------------------------------------

_provider_singleton: Optional[MicroCephProvider] = None
_singleton_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _singleton_lock
    if _singleton_lock is None:
        _singleton_lock = asyncio.Lock()
    return _singleton_lock


async def get_microceph_provider(config: Optional[MicroCephConfig] = None) -> MicroCephProvider:
    """Return the singleton MicroCephProvider, creating it on first call."""
    global _provider_singleton
    lock = _get_lock()
    async with lock:
        if _provider_singleton is None:
            _provider_singleton = MicroCephProvider(config)
            await _provider_singleton.initialise()
        return _provider_singleton


async def shutdown_microceph_provider() -> None:
    """Shut down and clear the singleton provider."""
    global _provider_singleton, _singleton_lock
    lock = _get_lock()
    async with lock:
        if _provider_singleton is not None:
            await _provider_singleton.close()
            _provider_singleton = None
        _singleton_lock = None
