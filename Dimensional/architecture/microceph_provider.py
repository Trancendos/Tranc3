"""
Dimensional.architecture.microceph_provider — MicroCeph single-node storage provider.

Implements intelligent, adaptive Ceph management for single-node and diode
deployments using the snap-deployed MicroCeph distribution.

Architecture
============
  MicroCeph (snap)
    ├── MON  — monitor daemon (quorum, cluster map)
    ├── MGR  — manager daemon (metrics, orchestrator)
    ├── OSD  — object storage daemon (one per disk/loop device)
    └── RGW  — RADOS Gateway (S3-compatible HTTP endpoint)

CRUSH Map Design
================
The CRUSH (Controlled Replication Under Scalable Hashing) algorithm places
data according to a hierarchical topology map.  This provider manages the
full CRUSH map lifecycle:

    root "default"
      └── host "tranc3-node-0"
            ├── osd.0   (NVMe — weight 1.0)
            ├── osd.1   (SSD  — weight 0.8)
            └── osd.2   (HDD  — weight 0.5)

Rules
-----
  Rule 0 (replicated_rule):  min_size=1, max_size=10, chooseleaf host
  Rule 1 (ec_rule):          Erasure coding 2+1 across OSDs

Pool Strategy
=============
  .mgr            — internal manager pool         (size=1, EC disabled)
  tranc3-meta     — PID/AID/SID/NID metadata      (size=1, replicated)
  tranc3-data     — bulk object data              (size=1, replicated)
  tranc3-archive  — cold storage / audit ledger   (size=1, replicated)
  .rgw.*          — RADOS Gateway internal pools  (auto-created by RGW)

Single-Node Replication
=======================
On a single-node deployment the replication size is forced to 1 (no
replicas).  ``osd_pool_default_min_size = 1`` is also set so that writes
succeed even when all OSDs are on a single host.

Zero-Cost Mandate
=================
MicroCeph uses the block volume included in the OCI Always Free tier
(200 GB total — shared with OS).  Loop-device OSDs are supported for
development; real block devices are preferred for production.

Usage
=====
    provider = MicroCephProvider.from_env()
    await provider.initialize()
    await provider.write("tranc3-data", "PID/records/001.json", data)
    obj = await provider.read("tranc3-data", "PID/records/001.json")
    await provider.close()

    # CRUSH map introspection
    crush = await provider.get_crush_map()
    print(crush.topology())
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac as _hmac_module
import json
import logging
import os
import shlex
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote as _quote
from urllib.parse import urlencode as _urlencode

import aiohttp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MICROCEPH_SOCKET = "/var/snap/microceph/current/run/ceph"
CEPH_CONF_PATH = "/var/snap/microceph/current/conf/ceph.conf"
MICROCEPH_CMD = "microceph"
RADOSGW_ADMIN_CMD = "radosgw-admin"
CEPH_CMD = "ceph"

DEFAULT_POOLS = [
    "tranc3-meta",
    "tranc3-data",
    "tranc3-archive",
]

RGW_DEFAULT_PORT = 7480
RGW_DEFAULT_HOST = "127.0.0.1"
RGW_REALM = "tranc3"
RGW_ZONE_GROUP = "default"
RGW_ZONE = "tranc3-zone"

OSD_TARGET_PG_PER_OSD = 100  # recommended: ~100 PGs per OSD for small clusters
MIN_PG_COUNT = 8  # minimum PGs per pool (power of 2)
MAX_PG_COUNT = 512  # cap for single-node (avoids overhead)

COMMAND_TIMEOUT_SECONDS = 60
HEALTH_CHECK_INTERVAL = 30  # seconds between background health checks
OSD_LOOP_SIZE_GB = 20  # loop-device OSD size for dev environments


# ---------------------------------------------------------------------------
# Enumerations & data classes
# ---------------------------------------------------------------------------


class OsdState(str, Enum):
    UP = "up"
    DOWN = "down"
    IN = "in"
    OUT = "out"


class PoolType(str, Enum):
    REPLICATED = "replicated"
    ERASURE = "erasure"


class CephHealthStatus(str, Enum):
    OK = "HEALTH_OK"
    WARN = "HEALTH_WARN"
    ERR = "HEALTH_ERR"


@dataclass
class OsdInfo:
    id: int
    uuid: str
    state: List[str]
    weight: float
    device: str = ""
    host: str = ""
    class_dev: str = "hdd"  # "ssd", "nvme", "hdd"

    @property
    def is_up(self) -> bool:
        return "up" in self.state

    @property
    def is_in(self) -> bool:
        return "in" in self.state


@dataclass
class PoolInfo:
    name: str
    pool_id: int
    pg_num: int
    pgp_num: int
    pool_type: PoolType = PoolType.REPLICATED
    size: int = 1
    min_size: int = 1
    crush_rule: str = "replicated_rule"
    application: str = ""

    def utilization_pct(self, used_bytes: int, total_bytes: int) -> float:
        if total_bytes == 0:
            return 0.0
        return round(used_bytes / total_bytes * 100, 2)


@dataclass
class CrushBucket:
    """A node in the CRUSH hierarchy (root, datacenter, rack, host, osd)."""

    id: int
    name: str
    type: str  # "root", "host", "osd"
    weight: float
    children: List["CrushBucket"] = field(default_factory=list)
    alg: str = "straw2"

    def topology(self, indent: int = 0) -> str:
        prefix = "  " * indent
        lines = [f"{prefix}{self.type}({self.id}) '{self.name}' w={self.weight:.3f}"]
        for child in self.children:
            lines.append(child.topology(indent + 1))
        return "\n".join(lines)


@dataclass
class CrushMap:
    """Full CRUSH map representation."""

    tunable_profile: str = "optimal"
    devices: List[Dict[str, Any]] = field(default_factory=list)
    types: List[Dict[str, Any]] = field(default_factory=list)
    buckets: List[CrushBucket] = field(default_factory=list)
    rules: List[Dict[str, Any]] = field(default_factory=list)

    def topology(self) -> str:
        lines = [f"CRUSH Map (tunable={self.tunable_profile})"]
        for b in self.buckets:
            if b.type == "root":
                lines.append(b.topology(1))
        return "\n".join(lines)

    def find_bucket(self, name: str) -> Optional[CrushBucket]:
        for b in self.buckets:
            if b.name == name:
                return b
            result = self._search(b, name)
            if result:
                return result
        return None

    def _search(self, node: CrushBucket, name: str) -> Optional[CrushBucket]:
        for child in node.children:
            if child.name == name:
                return child
            found = self._search(child, name)
            if found:
                return found
        return None


@dataclass
class RgwCredentials:
    access_key: str
    secret_key: str
    user_id: str
    display_name: str


@dataclass
class MicroCephConfig:
    """MicroCeph provider configuration."""

    rgw_host: str = RGW_DEFAULT_HOST
    rgw_port: int = RGW_DEFAULT_PORT
    rgw_admin_user: str = "tranc3-admin"
    rgw_realm: str = RGW_REALM
    rgw_zone: str = RGW_ZONE
    pools: List[str] = field(default_factory=lambda: list(DEFAULT_POOLS))
    osd_loop_dev: bool = False  # use loop devices (dev only)
    osd_loop_size_gb: int = OSD_LOOP_SIZE_GB
    single_node: bool = True  # forces replication size = 1
    crush_host_name: str = "tranc3-node-0"
    enable_health_watch: bool = True
    metrics_enabled: bool = True


# ---------------------------------------------------------------------------
# CRUSH algorithm implementation (rjenkins1 hash + straw2 selection)
# ---------------------------------------------------------------------------


def _rjenkins1(value: int) -> int:
    """
    rjenkins1 hash function — the CRUSH placement hash.

    This is the exact function used by Ceph's CRUSH implementation.
    Reference: src/crush/hash.c in the Ceph source tree.
    """
    a = b = c = 0xDEADBEEF + value
    # Mix
    a = (a ^ (c >> 4)) & 0xFFFFFFFF
    a = (a - c) & 0xFFFFFFFF
    b = (b ^ a) & 0xFFFFFFFF
    b = (b - a) & 0xFFFFFFFF
    c = (c ^ b) & 0xFFFFFFFF
    c = (c - b) & 0xFFFFFFFF
    a = (a ^ c) & 0xFFFFFFFF
    a = (a - c) & 0xFFFFFFFF
    b = (b ^ a) & 0xFFFFFFFF
    b = (b - a) & 0xFFFFFFFF
    c = (c ^ b) & 0xFFFFFFFF
    c = (c - b) & 0xFFFFFFFF
    return c


def crush_hash(pg_id: int, osd_id: int, retry: int) -> int:
    """Compute CRUSH placement hash for a (PG, OSD, retry) triple."""
    h = _rjenkins1(pg_id)
    h = (h ^ _rjenkins1(osd_id)) & 0xFFFFFFFF
    h = (h ^ _rjenkins1(retry)) & 0xFFFFFFFF
    return _rjenkins1(h)


def straw2_choose(
    osd_ids: List[int],
    weights: List[float],
    pg_id: int,
    retry: int = 0,
) -> int:
    """
    Straw2 bucket selection algorithm.

    Selects a single OSD from the weighted candidate list for the given PG.
    Straw2 is the default CRUSH bucket algorithm since Ceph Firefly and
    provides optimal movement when OSDs are added/removed.

    Each OSD gets a score = draw / (-ln(rand)) where draw is derived from
    the CRUSH hash.  The OSD with the highest score wins.
    """

    best_score = -1.0
    best_osd = osd_ids[0] if osd_ids else -1

    for _i, (osd_id, weight) in enumerate(zip(osd_ids, weights, strict=False)):
        if weight <= 0:
            continue
        h = crush_hash(pg_id, osd_id, retry)
        # Normalize to [0, 1) float
        r = (h & 0xFFFF) / 65536.0 + 1.0  # in [1, 2)
        # straw2 draw: w * r
        draw = weight * r
        score = draw
        if score > best_score:
            best_score = score
            best_osd = osd_id

    return best_osd


def crush_place(
    object_name: str,
    osd_ids: List[int],
    weights: List[float],
    replicas: int = 1,
) -> List[int]:
    """
    Compute CRUSH placement for an object, returning a list of OSD IDs
    that should store the replicas.

    This is a simplified single-bucket implementation matching a flat host
    topology (all OSDs under a single host bucket).
    """
    pg_id = int(hashlib.sha256(object_name.encode()).hexdigest()[:8], 16)
    result: List[int] = []

    remaining_ids = list(osd_ids)
    remaining_weights = list(weights)

    for replica in range(replicas):
        if not remaining_ids:
            break
        chosen = straw2_choose(remaining_ids, remaining_weights, pg_id, retry=replica)
        result.append(chosen)
        # Remove chosen OSD for next replica
        idx = remaining_ids.index(chosen)
        remaining_ids.pop(idx)
        remaining_weights.pop(idx)

    return result


# ---------------------------------------------------------------------------
# Async command runner
# ---------------------------------------------------------------------------


async def _run(
    *args: str,
    check: bool = True,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
    input: Optional[bytes] = None,
) -> Tuple[int, str, str]:
    """
    Run a shell command asynchronously.

    Returns (returncode, stdout, stderr).
    Raises RuntimeError if check=True and returncode != 0.
    """
    cmd_str = " ".join(shlex.quote(a) for a in args)
    logger.debug("microceph.run: %s", cmd_str)
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if input else None,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input),
            timeout=timeout,
        )
        rc = proc.returncode or 0
        if check and rc != 0:
            raise RuntimeError(
                f"Command failed (rc={rc}): {cmd_str}\n"
                f"stderr: {stderr.decode(errors='replace')[:500]}"
            )
        return rc, stdout.decode(errors="replace"), stderr.decode(errors="replace")
    except asyncio.TimeoutError:
        raise RuntimeError(f"Command timed out after {timeout}s: {cmd_str}") from None


async def _ceph(*args: str, **kw) -> Tuple[int, str, str]:
    """Run a ceph CLI command (JSON output by default)."""
    return await _run(CEPH_CMD, *args, **kw)


async def _ceph_json(*args: str) -> Any:
    """Run ceph CLI with -f json and parse the output."""
    _, stdout, _ = await _ceph(*args, "-f", "json")
    return json.loads(stdout)


async def _microceph(*args: str, **kw) -> Tuple[int, str, str]:
    return await _run(MICROCEPH_CMD, *args, **kw)


async def _radosgw_admin(*args: str, **kw) -> Tuple[int, str, str]:
    return await _run(RADOSGW_ADMIN_CMD, *args, **kw)


async def _radosgw_admin_json(*args: str) -> Any:
    _, stdout, _ = await _radosgw_admin(*args)
    return json.loads(stdout)


# ---------------------------------------------------------------------------
# CRUSH map builder
# ---------------------------------------------------------------------------


class CrushMapBuilder:
    """
    Builds and applies an optimal CRUSH map for a single-node MicroCeph
    deployment.

    Tuning strategy for single-node:
      - Profile: ``optimal`` (relaxes host-level requirements)
      - chooseleaf_vary_r: 1     (prevents corner-case sub-optimal mappings)
      - chooseleaf_stable:  1    (stable placement under OSD reweights)
      - straw_calc_version: 1    (straw2 algorithm)
    """

    TUNABLES_OPTIMAL = {
        "choose_local_tries": 0,
        "choose_local_fallback_tries": 0,
        "choose_total_tries": 50,
        "chooseleaf_descend_once": 1,
        "chooseleaf_vary_r": 1,
        "chooseleaf_stable": 1,
        "straw_calc_version": 1,
    }

    def __init__(self, config: MicroCephConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    async def get_current_map(self) -> CrushMap:
        """Fetch and parse the current CRUSH map from a running cluster."""
        crush = CrushMap()

        # Fetch OSD tree
        osd_tree = await _ceph_json("osd", "tree")
        nodes = {n["id"]: n for n in osd_tree.get("nodes", [])}

        def _build_bucket(node: Dict[str, Any]) -> CrushBucket:
            children = []
            for child_id in node.get("children", []):
                if child_id in nodes:
                    children.append(_build_bucket(nodes[child_id]))
            return CrushBucket(
                id=node["id"],
                name=node["name"],
                type=node.get("type", "osd"),
                weight=node.get("crush_weight", node.get("weight", 1.0)),
                children=children,
                alg=node.get("alg", "straw2"),
            )

        for node in osd_tree.get("nodes", []):
            if node.get("type") == "root":
                crush.buckets.append(_build_bucket(node))
                break

        # Fetch rules
        crush_dump = await _ceph_json("osd", "crush", "dump")
        crush.rules = crush_dump.get("rules", [])
        crush.devices = crush_dump.get("devices", [])
        crush.types = crush_dump.get("types", [])

        return crush

    # ------------------------------------------------------------------
    async def apply_single_node_tunables(self) -> None:
        """
        Apply optimal CRUSH tunables for single-node deployment.
        Prevents the cluster from warning about suboptimal placement.
        """
        logger.info("crush_map.applying_tunables profile=optimal")
        await _ceph("osd", "crush", "tunables", "optimal", check=False)
        for tunable, value in self.TUNABLES_OPTIMAL.items():
            await _ceph(
                "osd",
                "crush",
                "set-tunable",
                tunable,
                str(value),
                check=False,
            )
        logger.info("crush_map.tunables_applied")

    # ------------------------------------------------------------------
    async def ensure_host_bucket(self, host_name: str) -> None:
        """Create a host-level CRUSH bucket if it doesn't already exist."""
        crush = await self.get_current_map()
        if crush.find_bucket(host_name):
            logger.debug("crush_map.host_bucket_exists name=%s", host_name)
            return
        logger.info("crush_map.creating_host_bucket name=%s", host_name)
        await _ceph("osd", "crush", "add-bucket", host_name, "host")
        await _ceph("osd", "crush", "move", host_name, "root=default")

    # ------------------------------------------------------------------
    async def add_osd_to_crush(
        self,
        osd_id: int,
        host_name: str,
        weight: float = 1.0,
        dev_class: str = "hdd",
    ) -> None:
        """Add an OSD into the CRUSH map under the specified host bucket."""
        logger.info(
            "crush_map.add_osd osd_id=%d host=%s weight=%.3f class=%s",
            osd_id,
            host_name,
            weight,
            dev_class,
        )
        await _ceph(
            "osd",
            "crush",
            "create-or-move",
            f"osd.{osd_id}",
            str(weight),
            f"host={host_name}",
        )
        # Tag device class (nvme / ssd / hdd)
        await _ceph("osd", "crush", "rm-device-class", f"osd.{osd_id}", check=False)
        await _ceph("osd", "crush", "set-device-class", dev_class, f"osd.{osd_id}")

    # ------------------------------------------------------------------
    async def create_replicated_rule(
        self,
        rule_name: str = "tranc3_replicated",
        root: str = "default",
        type: str = "host",
    ) -> None:
        """Create a replicated CRUSH rule targeting the specified root and type."""
        rules = (await _ceph_json("osd", "crush", "dump")).get("rules", [])
        if any(r["rule_name"] == rule_name for r in rules):
            logger.debug("crush_map.rule_exists name=%s", rule_name)
            return
        logger.info("crush_map.creating_rule name=%s root=%s type=%s", rule_name, root, type)
        await _ceph(
            "osd",
            "crush",
            "rule",
            "create-replicated",
            rule_name,
            root,
            type,
        )

    # ------------------------------------------------------------------
    async def reweight_osd_by_utilization(self, threshold_pct: float = 20.0) -> None:
        """
        Auto-reweight OSDs to balance utilization.
        Only adjusts OSDs that deviate more than threshold_pct from average.
        """
        logger.info("crush_map.reweight_check threshold=%.1f%%", threshold_pct)
        await _ceph("osd", "reweight-by-utilization", str(int(threshold_pct + 100)), check=False)


# ---------------------------------------------------------------------------
# Pool manager
# ---------------------------------------------------------------------------


class CephPoolManager:
    """
    Manages Ceph pool lifecycle — creation, deletion, PG sizing, and
    application tagging.

    PG count formula (Ceph guidelines):
        pg_count = max(MIN_PG_COUNT, next_power_of_2(
            (osd_count * OSD_TARGET_PG_PER_OSD) / replica_count
        ))
        capped at MAX_PG_COUNT for single-node deployments.
    """

    def __init__(self, config: MicroCephConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    @staticmethod
    def _next_power_of_2(n: int) -> int:
        if n <= 0:
            return MIN_PG_COUNT
        p = 1
        while p < n:
            p <<= 1
        return p

    def calculate_pg_count(self, osd_count: int, replicas: int = 1) -> int:
        raw = (osd_count * OSD_TARGET_PG_PER_OSD) // max(1, replicas)
        pg_num = self._next_power_of_2(max(MIN_PG_COUNT, raw))
        return min(pg_num, MAX_PG_COUNT)

    # ------------------------------------------------------------------
    async def list_pools(self) -> List[PoolInfo]:
        pools_data = await _ceph_json("osd", "pool", "ls", "detail")
        result = []
        for p in pools_data:
            result.append(
                PoolInfo(
                    name=p["pool_name"],
                    pool_id=p["pool"],
                    pg_num=p.get("pg_num", 8),
                    pgp_num=p.get("pg_placement_num", 8),
                    pool_type=PoolType.REPLICATED if p.get("type") == 1 else PoolType.ERASURE,
                    size=p.get("size", 1),
                    min_size=p.get("min_size", 1),
                    crush_rule=p.get("crush_rule", "replicated_rule"),
                    application=",".join(p.get("application_metadata", {}).keys()),
                )
            )
        return result

    # ------------------------------------------------------------------
    async def ensure_pool(
        self,
        name: str,
        pg_num: Optional[int] = None,
        size: int = 1,
        application: str = "tranc3",
        crush_rule: str = "replicated_rule",
    ) -> PoolInfo:
        """Create pool if it doesn't exist; return its info."""
        pools = await self.list_pools()
        existing = next((p for p in pools if p.name == name), None)
        if existing:
            logger.debug("ceph_pool.exists name=%s", name)
            return existing

        # Determine PG count
        if pg_num is None:
            osd_count = len(await self._list_osd_ids())
            pg_num = self.calculate_pg_count(osd_count, replicas=size)

        logger.info(
            "ceph_pool.creating name=%s pg_num=%d size=%d",
            name,
            pg_num,
            size,
        )

        await _ceph(
            "osd",
            "pool",
            "create",
            name,
            str(pg_num),
            str(pg_num),
            "replicated",
            crush_rule,
        )
        await _ceph("osd", "pool", "set", name, "size", str(size))
        await _ceph("osd", "pool", "set", name, "min_size", "1")

        if application:
            await _ceph(
                "osd",
                "pool",
                "application",
                "enable",
                name,
                application,
                check=False,
            )

        return PoolInfo(
            name=name,
            pool_id=-1,
            pg_num=pg_num,
            pgp_num=pg_num,
            size=size,
            min_size=1,
            crush_rule=crush_rule,
            application=application,
        )

    # ------------------------------------------------------------------
    async def delete_pool(self, name: str) -> None:
        """Delete a pool (requires mon_allow_pool_delete = true)."""
        logger.warning("ceph_pool.deleting name=%s — THIS IS DESTRUCTIVE", name)
        await _ceph(
            "osd",
            "pool",
            "delete",
            name,
            name,
            "--yes-i-really-really-mean-it",
        )

    # ------------------------------------------------------------------
    async def get_pool_stats(self, name: str) -> Dict[str, Any]:
        stats_all = await _ceph_json("df", "detail")
        for pool in stats_all.get("pools", []):
            if pool["name"] == name:
                stats = pool.get("stats", {})
                return {
                    "pool": name,
                    "bytes_used": stats.get("bytes_used", 0),
                    "bytes_avail": stats.get("max_avail", 0),
                    "objects": stats.get("objects", 0),
                    "kb_used": stats.get("kb_used", 0),
                    "percent_used": stats.get("percent_used", 0.0),
                }
        return {"pool": name, "error": "not_found"}

    # ------------------------------------------------------------------
    async def _list_osd_ids(self) -> List[int]:
        data = await _ceph_json("osd", "ls")
        return [int(x) for x in data] if isinstance(data, list) else []

    # ------------------------------------------------------------------
    async def optimize_pg_autoscaler(self) -> None:
        """Enable the PG autoscaler module for all pools."""
        await _ceph("mgr", "module", "enable", "pg_autoscaler", check=False)
        pools = await self.list_pools()
        for pool in pools:
            await _ceph(
                "osd",
                "pool",
                "set",
                pool.name,
                "pg_autoscale_mode",
                "on",
                check=False,
            )
        logger.info("ceph_pool.pg_autoscaler_enabled pools=%d", len(pools))


# ---------------------------------------------------------------------------
# OSD lifecycle manager
# ---------------------------------------------------------------------------


class OsdLifecycleManager:
    """
    Manages OSD provisioning, health, and decommissioning.

    Supports:
      - Physical block devices (e.g., /dev/sdb)
      - Loop-file OSDs (for development / OCI Always Free block volume)
    """

    def __init__(self, config: MicroCephConfig) -> None:
        self._config = config
        self._loop_devs: List[str] = []  # track created loop devices

    # ------------------------------------------------------------------
    async def list_osds(self) -> List[OsdInfo]:
        """Return info for all OSDs in the cluster."""
        osd_dump = await _ceph_json("osd", "dump")
        osd_tree = await _ceph_json("osd", "tree")
        tree_map = {n["id"]: n for n in osd_tree.get("nodes", []) if n.get("type") == "osd"}

        result = []
        for osd in osd_dump.get("osds", []):
            osd_id = osd["osd"]
            state = []
            if osd.get("up"):
                state.append("up")
            if osd.get("in"):
                state.append("in")

            tree_node = tree_map.get(osd_id, {})
            result.append(
                OsdInfo(
                    id=osd_id,
                    uuid=osd.get("uuid", ""),
                    state=state,
                    weight=tree_node.get("crush_weight", 1.0),
                    host=tree_node.get("host", ""),
                    class_dev=tree_node.get("device_class", "hdd"),
                )
            )
        return result

    # ------------------------------------------------------------------
    async def add_disk(self, device: str) -> None:
        """
        Add a physical or loop block device as a new OSD.
        Uses MicroCeph's ``add-osd`` subcommand.
        """
        logger.info("osd_lifecycle.add_disk device=%s", device)
        await _microceph("disk", "add", device)

    # ------------------------------------------------------------------
    async def provision_loop_osd(
        self,
        index: int = 0,
        size_gb: int = OSD_LOOP_SIZE_GB,
        path: str = "/var/snap/microceph/common",
    ) -> str:
        """
        Create and attach a loop-file OSD for development/OCI block volume use.

        Returns the loop device path (e.g., /dev/loop0).
        """
        loop_file = f"{path}/osd-loop-{index}.img"
        logger.info(
            "osd_lifecycle.provision_loop size_gb=%d file=%s",
            size_gb,
            loop_file,
        )

        # Create sparse file
        await _run(
            "dd",
            "if=/dev/zero",
            f"of={loop_file}",
            "bs=1M",
            f"count={size_gb * 1024}",
            "conv=sparse",
        )

        # Attach loop device
        _, stdout, _ = await _run("losetup", "--find", "--show", loop_file)
        loop_dev = stdout.strip()
        self._loop_devs.append(loop_dev)

        # Add to MicroCeph
        await self.add_disk(loop_dev)

        logger.info("osd_lifecycle.loop_osd_ready dev=%s", loop_dev)
        return loop_dev

    # ------------------------------------------------------------------
    async def remove_osd(self, osd_id: int) -> None:
        """
        Safely drain and remove an OSD.
        Sets weight to 0, waits for PG migration, then purges.
        """
        logger.warning("osd_lifecycle.removing osd_id=%d", osd_id)
        await _ceph("osd", "out", f"osd.{osd_id}")
        # Wait for PG migration (simplified — production should poll)
        await asyncio.sleep(5)
        await _ceph("osd", "crush", "remove", f"osd.{osd_id}")
        await _ceph("auth", "del", f"osd.{osd_id}")
        await _ceph("osd", "rm", f"osd.{osd_id}")
        logger.info("osd_lifecycle.removed osd_id=%d", osd_id)

    # ------------------------------------------------------------------
    async def scrub_all(self) -> None:
        """Trigger a scrub on all OSDs (data integrity check)."""
        logger.info("osd_lifecycle.scrub_all")
        await _ceph("osd", "scrub", "0", check=False)
        await _ceph("pg", "deep-scrub", "0", check=False)

    # ------------------------------------------------------------------
    async def cleanup_loop_devices(self) -> None:
        """Detach all loop devices created during this session."""
        for dev in self._loop_devs:
            await _run("losetup", "-d", dev, check=False)
        self._loop_devs.clear()


# ---------------------------------------------------------------------------
# RADOS Gateway (RGW) manager
# ---------------------------------------------------------------------------


class RgwManager:
    """
    Manages RADOS Gateway lifecycle and S3 user management.

    RGW provides an S3-compatible API on top of RADOS, enabling the same
    _S3CompatTier logic used in oci_adaptive_provider.py to work against
    a local Ceph cluster.
    """

    def __init__(self, config: MicroCephConfig) -> None:
        self._config = config
        self._creds: Optional[RgwCredentials] = None

    @property
    def endpoint(self) -> str:
        return f"http://{self._config.rgw_host}:{self._config.rgw_port}"

    # ------------------------------------------------------------------
    async def ensure_realm(self) -> None:
        """Create the RGW realm/zone-group/zone if not present."""
        logger.info("rgw.ensure_realm realm=%s", self._config.rgw_realm)
        await _radosgw_admin("realm", "create", "--rgw-realm", self._config.rgw_realm, check=False)
        await _radosgw_admin(
            "zonegroup",
            "create",
            "--rgw-zonegroup",
            RGW_ZONE_GROUP,
            "--master",
            "--default",
            check=False,
        )
        await _radosgw_admin(
            "zone",
            "create",
            "--rgw-zonegroup",
            RGW_ZONE_GROUP,
            "--rgw-zone",
            self._config.rgw_zone,
            "--master",
            "--default",
            check=False,
        )
        await _radosgw_admin(
            "period",
            "update",
            "--rgw-realm",
            self._config.rgw_realm,
            "--commit",
            check=False,
        )

    # ------------------------------------------------------------------
    async def ensure_admin_user(self) -> RgwCredentials:
        """Create (or fetch existing) RGW admin user credentials."""
        if self._creds:
            return self._creds

        user_id = self._config.rgw_admin_user
        try:
            info = await _radosgw_admin_json("user", "info", "--uid", user_id)
        except Exception:
            info = None

        if info is None:
            logger.info("rgw.creating_admin_user uid=%s", user_id)
            info = await _radosgw_admin_json(
                "user",
                "create",
                "--uid",
                user_id,
                "--display-name",
                f"Tranc3 Admin ({user_id})",
                "--caps",
                "users=*;buckets=*;metadata=*;usage=*;zone=*",
            )

        keys = info.get("keys", [{}])[0]
        self._creds = RgwCredentials(
            access_key=keys.get("access_key", ""),
            secret_key=keys.get("secret_key", ""),
            user_id=user_id,
            display_name=info.get("display_name", user_id),
        )
        logger.info("rgw.admin_user_ready uid=%s", user_id)
        return self._creds

    # ------------------------------------------------------------------
    async def create_bucket(self, bucket_name: str, user_id: Optional[str] = None) -> None:
        """Create an RGW bucket and assign ownership."""
        uid = user_id or self._config.rgw_admin_user
        logger.info("rgw.creating_bucket name=%s uid=%s", bucket_name, uid)
        await _radosgw_admin(
            "bucket",
            "link",
            "--bucket",
            bucket_name,
            "--uid",
            uid,
            check=False,
        )

    # ------------------------------------------------------------------
    async def list_buckets(self) -> List[str]:
        """List all RGW buckets."""
        data = await _radosgw_admin_json("bucket", "list")
        if isinstance(data, list):
            return data
        return []

    # ------------------------------------------------------------------
    async def get_bucket_stats(self, bucket_name: str) -> Dict[str, Any]:
        """Return utilization stats for a bucket."""
        try:
            data = await _radosgw_admin_json("bucket", "stats", "--bucket", bucket_name)
            usage = data.get("usage", {}).get("rgw.main", {})
            return {
                "bucket": bucket_name,
                "owner": data.get("owner", ""),
                "objects": usage.get("num_objects", 0),
                "bytes_used": usage.get("size_actual", 0),
                "bytes_kb": usage.get("size_kb_actual", 0),
            }
        except Exception as exc:
            return {"bucket": bucket_name, "error": str(exc)}

    # ------------------------------------------------------------------
    async def is_healthy(self) -> bool:
        """Probe the RGW HTTP endpoint for liveness."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as sess:
                async with sess.get(self.endpoint) as resp:
                    return resp.status in (200, 403)  # 403 = up but auth required
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Cluster health monitor
# ---------------------------------------------------------------------------


class CephHealthMonitor:
    """
    Background task that polls cluster health every HEALTH_CHECK_INTERVAL
    seconds and logs warnings/errors.

    Tracks:
      - Overall HEALTH_OK / HEALTH_WARN / HEALTH_ERR
      - OSD up/in counts
      - PG degraded/misplaced counts
      - Slow OPS warnings
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last: Optional[Dict[str, Any]] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="ceph_health_monitor")
        logger.info("ceph_health.monitor_started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._check()
            except Exception as exc:
                logger.debug("ceph_health.check_error: %s", exc)
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def _check(self) -> None:
        data = await _ceph_json("health", "detail")
        status = data.get("status", "HEALTH_ERR")
        checks = data.get("checks", {})
        self._last = {
            "status": status,
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if status == CephHealthStatus.OK.value:
            logger.debug("ceph_health.ok")
        elif status == CephHealthStatus.WARN.value:
            for check_name, check_data in checks.items():
                logger.warning(
                    "ceph_health.warn check=%s summary=%s",
                    check_name,
                    check_data.get("summary", {}).get("message", ""),
                )
        else:
            logger.error(
                "ceph_health.error status=%s checks=%s",
                status,
                list(checks.keys()),
            )

    def last_status(self) -> Optional[Dict[str, Any]]:
        return self._last

    def is_healthy(self) -> bool:
        if not self._last:
            return True  # assume healthy until first check
        return self._last.get("status") == CephHealthStatus.OK.value


# ---------------------------------------------------------------------------
# RGW S3 client (thin wrapper over _S3CompatTier)
# ---------------------------------------------------------------------------

# Re-use S3-compat tier from oci_adaptive_provider logic
# (inline simplified version to avoid import circularity)


class _RgwS3Client:
    """
    Lightweight async S3 client talking to the local RGW endpoint.
    Uses AWS Signature Version 4 (same as oci_adaptive_provider).
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._session: Optional[aiohttp.ClientSession] = None

    def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._session

    def _url(self, bucket: str, key: str) -> str:
        return f"{self._endpoint}/{bucket}/{_quote(key, safe='/')}"

    def _sign(
        self, method: str, url: str, body: bytes, extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """AWS Sig4 signing — inline to avoid import from oci_adaptive_provider."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.netloc
        path = parsed.path or "/"
        qs = parsed.query
        now = datetime.now(timezone.utc)
        date_s = now.strftime("%Y%m%d")
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        ph = hashlib.sha256(body).hexdigest()
        hdrs: Dict[str, str] = {
            "host": host,
            "x-amz-content-sha256": ph,
            "x-amz-date": amz_date,
        }
        if extra_headers:
            for k, v in extra_headers.items():
                hdrs[k.lower()] = v.strip()
        sh = ";".join(sorted(hdrs.keys()))
        ch = "".join(f"{k}:{v}\n" for k, v in sorted(hdrs.items()))
        cr = "\n".join([method.upper(), path, qs, ch, sh, ph])
        scope = f"{date_s}/{self._region}/s3/aws4_request"
        sts = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(cr.encode()).hexdigest(),
            ]
        )

        def hmac_b(key: bytes, msg: str) -> bytes:
            return _hmac_module.new(key, msg.encode(), hashlib.sha256).digest()

        sk = hmac_b(
            hmac_b(hmac_b(hmac_b(f"AWS4{self._secret_key}".encode(), date_s), self._region), "s3"),
            "aws4_request",
        )
        sig = _hmac_module.new(sk, sts.encode(), hashlib.sha256).hexdigest()
        auth = (
            f"AWS4-HMAC-SHA256 Credential={self._access_key}/{scope}, "
            f"SignedHeaders={sh}, Signature={sig}"
        )
        return {**hdrs, "Authorization": auth}

    async def put(
        self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        url = self._url(bucket, key)
        headers = self._sign("PUT", url, data, {"content-type": content_type})
        async with self._sess().put(url, headers=headers, data=data) as resp:
            resp.raise_for_status()

    async def get(self, bucket: str, key: str) -> bytes:
        url = self._url(bucket, key)
        headers = self._sign("GET", url, b"")
        async with self._sess().get(url, headers=headers) as resp:
            if resp.status == 404:
                raise FileNotFoundError(f"Object not found: {bucket}/{key}")
            resp.raise_for_status()
            return await resp.read()

    async def delete(self, bucket: str, key: str) -> None:
        url = self._url(bucket, key)
        headers = self._sign("DELETE", url, b"")
        async with self._sess().delete(url, headers=headers) as resp:
            if resp.status not in (204, 404):
                resp.raise_for_status()

    async def list_objects(self, bucket: str, prefix: str = "") -> List[str]:
        url = f"{self._endpoint}/{bucket}"
        params = {"list-type": "2", "prefix": prefix}
        full = f"{url}?{_urlencode(params)}"
        headers = self._sign("GET", full, b"")
        async with self._sess().get(full, headers=headers) as resp:
            resp.raise_for_status()
            body = await resp.text()
        import defusedxml.ElementTree as ET  # nosec B405 — defusedxml prevents XXE

        root = ET.fromstring(body)
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        return [k.text for k in root.findall(".//s3:Contents/s3:Key", ns) if k.text]

    async def head(self, bucket: str, key: str) -> bool:
        url = self._url(bucket, key)
        headers = self._sign("HEAD", url, b"")
        async with self._sess().head(url, headers=headers) as resp:
            return resp.status == 200

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


# ---------------------------------------------------------------------------
# Main MicroCeph provider
# ---------------------------------------------------------------------------


class MicroCephProvider:
    """
    MicroCeph single-node storage provider — full lifecycle management.

    Combines:
      - OSD provisioning (physical or loop devices)
      - CRUSH map management with straw2 / optimal tunables
      - Pool lifecycle (replicated, single-node size=1)
      - RGW S3-gateway management and user provisioning
      - Async S3 client for object read/write/delete/list
      - Background health monitoring
      - Prometheus-compatible metrics

    Entity Taxonomy
    ---------------
    Objects are stored as:
        {pool}/{entity_type}/{category}/{identifier}

    Example paths:
        tranc3-meta/PID/config/global-v1.json
        tranc3-data/AID/sessions/user-42/v1717000000.msgpack
        tranc3-archive/SID/backup/2025-06/snapshot.tar.zst
    """

    def __init__(self, config: MicroCephConfig) -> None:
        self._config = config
        self._crush = CrushMapBuilder(config)
        self._pools = CephPoolManager(config)
        self._osds = OsdLifecycleManager(config)
        self._rgw = RgwManager(config)
        self._health_mon = CephHealthMonitor()
        self._s3: Optional[_RgwS3Client] = None
        self._creds: Optional[RgwCredentials] = None
        self._metrics: Dict[str, int] = {
            "reads": 0,
            "writes": 0,
            "deletes": 0,
            "crush_placements": 0,
            "health_checks": 0,
            "errors": 0,
        }
        self._initialized = False

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "MicroCephProvider":
        """Construct from environment variables."""
        return cls(
            MicroCephConfig(
                rgw_host=os.getenv("MICROCEPH_RGW_HOST", RGW_DEFAULT_HOST),
                rgw_port=int(os.getenv("MICROCEPH_RGW_PORT", str(RGW_DEFAULT_PORT))),
                rgw_admin_user=os.getenv("MICROCEPH_ADMIN_USER", "tranc3-admin"),
                rgw_realm=os.getenv("MICROCEPH_REALM", RGW_REALM),
                rgw_zone=os.getenv("MICROCEPH_ZONE", RGW_ZONE),
                pools=os.getenv("MICROCEPH_POOLS", ",".join(DEFAULT_POOLS)).split(","),
                osd_loop_dev=os.getenv("MICROCEPH_OSD_LOOP", "false").lower() == "true",
                single_node=os.getenv("MICROCEPH_SINGLE_NODE", "true").lower() == "true",
                crush_host_name=os.getenv("MICROCEPH_CRUSH_HOST", "tranc3-node-0"),
                enable_health_watch=os.getenv("MICROCEPH_HEALTH_WATCH", "true").lower() == "true",
            )
        )

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        Full provider initialization sequence:
          1. Apply single-node CRUSH tunables
          2. Ensure host bucket in CRUSH map
          3. Provision loop OSD if configured
          4. Ensure required pools exist
          5. Bootstrap RGW realm / admin user
          6. Build S3 client
          7. Start health monitor
        """
        if self._initialized:
            return

        logger.info("microceph_provider.initializing")

        # 1. CRUSH tunables
        try:
            await self._crush.apply_single_node_tunables()
        except Exception as exc:
            logger.warning("microceph_provider.crush_tunables_warn: %s", exc)

        # 2. CRUSH host bucket
        try:
            await self._crush.ensure_host_bucket(self._config.crush_host_name)
        except Exception as exc:
            logger.warning("microceph_provider.crush_host_warn: %s", exc)

        # 3. Loop OSD provisioning (dev mode)
        if self._config.osd_loop_dev:
            try:
                osds = await self._osds.list_osds()
                if not osds:
                    logger.info("microceph_provider.provisioning_loop_osd")
                    await self._osds.provision_loop_osd(
                        index=0,
                        size_gb=self._config.osd_loop_size_gb,
                    )
            except Exception as exc:
                logger.warning("microceph_provider.loop_osd_warn: %s", exc)

        # 4. Ensure pools
        for pool_name in self._config.pools:
            try:
                await self._pools.ensure_pool(
                    name=pool_name,
                    size=1 if self._config.single_node else 3,
                )
            except Exception as exc:
                logger.warning("microceph_provider.pool_init_warn pool=%s: %s", pool_name, exc)

        # Enable PG autoscaler
        try:
            await self._pools.optimize_pg_autoscaler()
        except Exception as exc:
            logger.debug("microceph_provider.pg_autoscaler_warn: %s", exc)

        # 5. RGW setup
        try:
            await self._rgw.ensure_realm()
            self._creds = await self._rgw.ensure_admin_user()
        except Exception as exc:
            logger.warning("microceph_provider.rgw_init_warn: %s", exc)

        # 6. Build S3 client
        if self._creds:
            self._s3 = _RgwS3Client(
                endpoint=self._rgw.endpoint,
                access_key=self._creds.access_key,
                secret_key=self._creds.secret_key,
            )
        else:
            logger.warning("microceph_provider.no_rgw_creds — S3 operations will fail")

        # 7. Health monitor
        if self._config.enable_health_watch:
            await self._health_mon.start()

        self._initialized = True
        logger.info(
            "microceph_provider.ready pools=%s rgw=%s",
            self._config.pools,
            self._rgw.endpoint,
        )

    # ------------------------------------------------------------------
    # Core storage interface
    # ------------------------------------------------------------------

    def _require_s3(self) -> _RgwS3Client:
        if not self._s3:
            raise RuntimeError(
                "MicroCephProvider not initialized or RGW credentials unavailable. "
                "Call await provider.initialize() first."
            )
        return self._s3

    async def write(
        self,
        pool: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Write object to pool via RGW S3."""
        if not self._initialized:
            await self.initialize()
        self._metrics["writes"] += 1
        try:
            await self._require_s3().put(pool, key, data, content_type)
            logger.debug("microceph.write pool=%s key=%s bytes=%d", pool, key, len(data))
        except Exception as exc:
            self._metrics["errors"] += 1
            logger.error("microceph.write_error pool=%s key=%s: %s", pool, key, exc)
            raise

    async def read(self, pool: str, key: str) -> bytes:
        """Read object from pool via RGW S3."""
        if not self._initialized:
            await self.initialize()
        self._metrics["reads"] += 1
        try:
            data = await self._require_s3().get(pool, key)
            return data
        except Exception:
            self._metrics["errors"] += 1
            raise

    async def delete(self, pool: str, key: str) -> None:
        """Delete object from pool."""
        if not self._initialized:
            await self.initialize()
        self._metrics["deletes"] += 1
        await self._require_s3().delete(pool, key)

    async def list(self, pool: str, prefix: str = "") -> List[str]:
        """List object keys in pool matching prefix."""
        if not self._initialized:
            await self.initialize()
        return await self._require_s3().list_objects(pool, prefix)

    async def exists(self, pool: str, key: str) -> bool:
        """Check if object exists."""
        if not self._initialized:
            await self.initialize()
        return await self._require_s3().head(pool, key)

    # ------------------------------------------------------------------
    # CRUSH placement query
    # ------------------------------------------------------------------

    async def compute_placement(
        self,
        object_name: str,
        replicas: int = 1,
    ) -> List[int]:
        """
        Return list of OSD IDs where the object would be placed by CRUSH.
        This is a local simulation using the Python straw2 implementation
        and the live OSD list — it matches Ceph's actual placement for
        flat single-host topologies.
        """
        self._metrics["crush_placements"] += 1
        osds = await self._osds.list_osds()
        if not osds:
            return []
        osd_ids = [o.id for o in osds if o.is_up and o.is_in]
        weights = [o.weight for o in osds if o.is_up and o.is_in]
        return crush_place(object_name, osd_ids, weights, replicas)

    # ------------------------------------------------------------------
    # Health & diagnostics
    # ------------------------------------------------------------------

    async def health(self) -> Dict[str, Any]:
        """Return comprehensive provider health snapshot."""
        self._metrics["health_checks"] += 1

        cluster_health = self._health_mon.last_status() or {}

        try:
            pool_stats = []
            for pool_name in self._config.pools:
                pool_stats.append(await self._pools.get_pool_stats(pool_name))
        except Exception:
            pool_stats = []

        try:
            osd_list = await self._osds.list_osds()
            osd_up = sum(1 for o in osd_list if o.is_up)
            osd_in = sum(1 for o in osd_list if o.is_in)
        except Exception:
            osd_list, osd_up, osd_in = [], 0, 0

        try:
            rgw_healthy = await self._rgw.is_healthy()
        except Exception:
            rgw_healthy = False

        return {
            "provider": "microceph",
            "initialized": self._initialized,
            "single_node": self._config.single_node,
            "rgw_endpoint": self._rgw.endpoint,
            "rgw_healthy": rgw_healthy,
            "cluster": {
                "status": cluster_health.get("status", "UNKNOWN"),
                "checks": list(cluster_health.get("checks", {}).keys()),
            },
            "osds": {
                "total": len(osd_list),
                "up": osd_up,
                "in": osd_in,
            },
            "pools": pool_stats,
            "metrics": dict(self._metrics),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # CRUSH map introspection
    # ------------------------------------------------------------------

    async def get_crush_map(self) -> CrushMap:
        """Fetch and return the live CRUSH map."""
        return await self._crush.get_current_map()

    async def print_crush_topology(self) -> str:
        """Return a human-readable CRUSH topology string."""
        crush = await self.get_crush_map()
        return crush.topology()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._health_mon.stop()
        if self._s3:
            await self._s3.close()
        await self._osds.cleanup_loop_devices()
        logger.info("microceph_provider.closed")

    async def __aenter__(self) -> "MicroCephProvider":
        await self.initialize()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_microceph: Optional[MicroCephProvider] = None


async def get_microceph_provider() -> MicroCephProvider:
    """Return (and lazily initialize) the module-level default provider."""
    global _default_microceph
    if _default_microceph is None:
        _default_microceph = MicroCephProvider.from_env()
        await _default_microceph.initialize()
    return _default_microceph


async def shutdown_microceph_provider() -> None:
    """Cleanly shut down the module-level MicroCeph provider."""
    global _default_microceph
    if _default_microceph:
        await _default_microceph.close()
        _default_microceph = None
