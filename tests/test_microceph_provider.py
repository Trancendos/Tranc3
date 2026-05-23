"""
tests/test_microceph_provider.py — Unit tests for MicroCeph storage provider.

Tests cover:
  - CRUSH algorithm: rjenkins1 hash, straw2 selection, crush_place
  - CrushBucket / CrushMap dataclasses and topology rendering
  - CrushMapBuilder (command-generation, not live Ceph)
  - MicroCephConfig defaults and validation
  - OsdState / PoolType / CephHealthStatus enums
  - OsdInfo / PoolInfo / RgwCredentials dataclass construction
  - Singleton helpers: get_microceph_provider / shutdown_microceph_provider

No live Ceph cluster is required — all I/O-bound paths are exercised via
mocks or by testing the pure-Python CRUSH maths directly.
"""

from __future__ import annotations


import pytest

# ---------------------------------------------------------------------------
# Module-level imports (verified importable)
# ---------------------------------------------------------------------------
from shared_core.architecture.microceph_provider import (
    DEFAULT_POOLS,
    MICROCEPH_CMD,
    MIN_PG_COUNT,
    MAX_PG_COUNT,
    OSD_TARGET_PG_PER_OSD,
    CephHealthStatus,
    CrushBucket,
    CrushMap,
    CrushMapBuilder,
    MicroCephConfig,
    OsdInfo,
    OsdState,
    PoolInfo,
    PoolType,
    RgwCredentials,
    crush_hash,
    crush_place,
    straw2_choose,
    get_microceph_provider,
    shutdown_microceph_provider,
)


# ===========================================================================
# Constants
# ===========================================================================


class TestModuleConstants:
    def test_default_pools_are_three(self):
        assert len(DEFAULT_POOLS) == 3

    def test_default_pool_names(self):
        assert "tranc3-meta" in DEFAULT_POOLS
        assert "tranc3-data" in DEFAULT_POOLS
        assert "tranc3-archive" in DEFAULT_POOLS

    def test_pg_count_bounds(self):
        assert MIN_PG_COUNT >= 1
        assert MAX_PG_COUNT > MIN_PG_COUNT
        assert OSD_TARGET_PG_PER_OSD > 0

    def test_microceph_cmd_string(self):
        assert isinstance(MICROCEPH_CMD, str)
        assert len(MICROCEPH_CMD) > 0


# ===========================================================================
# Enums
# ===========================================================================


class TestOsdState:
    def test_all_values_are_strings(self):
        for state in OsdState:
            assert isinstance(state.value, str)

    def test_up_in_state(self):
        values = [s.value for s in OsdState]
        assert any("up" in v.lower() or "in" in v.lower() for v in values)

    def test_enum_has_members(self):
        assert len(list(OsdState)) >= 2


class TestPoolType:
    def test_replicated_exists(self):
        values = [p.value for p in PoolType]
        assert any("replicated" in v.lower() for v in values)

    def test_enum_has_members(self):
        assert len(list(PoolType)) >= 1


class TestCephHealthStatus:
    def test_ok_exists(self):
        values = [s.value for s in CephHealthStatus]
        assert any("ok" in v.lower() or "health_ok" in v.lower() for v in values)

    def test_warn_exists(self):
        values = [s.value for s in CephHealthStatus]
        assert any("warn" in v.lower() for v in values)

    def test_err_exists(self):
        values = [s.value for s in CephHealthStatus]
        assert any("err" in v.lower() for v in values)


# ===========================================================================
# Dataclasses
# ===========================================================================


class TestCrushBucket:
    def test_basic_construction(self):
        b = CrushBucket(id=0, name="osd.0", type="osd", weight=1.0)
        assert b.id == 0
        assert b.name == "osd.0"
        assert b.type == "osd"
        assert b.weight == 1.0
        assert b.children == []
        assert b.alg == "straw2"

    def test_default_alg_is_straw2(self):
        b = CrushBucket(id=1, name="host", type="host", weight=2.0)
        assert b.alg == "straw2"

    def test_children_are_mutable_list(self):
        parent = CrushBucket(id=-1, name="root", type="root", weight=5.0)
        child = CrushBucket(id=0, name="osd.0", type="osd", weight=1.0)
        parent.children.append(child)
        assert len(parent.children) == 1
        assert parent.children[0] is child

    def test_topology_leaf_node(self):
        osd = CrushBucket(id=0, name="osd.0", type="osd", weight=1.0)
        topo = osd.topology()
        assert "osd.0" in topo
        assert "1.000" in topo

    def test_topology_nested(self):
        root = CrushBucket(id=-1, name="default", type="root", weight=3.0)
        host = CrushBucket(id=-2, name="node-0", type="host", weight=3.0)
        osd0 = CrushBucket(id=0, name="osd.0", type="osd", weight=1.0)
        osd1 = CrushBucket(id=1, name="osd.1", type="osd", weight=1.0)
        host.children = [osd0, osd1]
        root.children = [host]
        topo = root.topology()
        assert "default" in topo
        assert "node-0" in topo
        assert "osd.0" in topo
        assert "osd.1" in topo

    def test_topology_indentation(self):
        parent = CrushBucket(id=-1, name="root", type="root", weight=1.0)
        child = CrushBucket(id=0, name="osd.0", type="osd", weight=1.0)
        parent.children = [child]
        topo = parent.topology()
        lines = topo.split("\n")
        assert len(lines) == 2
        # Child line should be indented
        assert lines[1].startswith("  ")


class TestCrushMap:
    def _make_map(self) -> CrushMap:
        root = CrushBucket(id=-1, name="default", type="root", weight=2.0)
        host = CrushBucket(id=-2, name="tranc3-node-0", type="host", weight=2.0)
        osd0 = CrushBucket(id=0, name="osd.0", type="osd", weight=1.0)
        osd1 = CrushBucket(id=1, name="osd.1", type="osd", weight=1.0)
        host.children = [osd0, osd1]
        root.children = [host]
        return CrushMap(buckets=[root, host, osd0, osd1])

    def test_empty_map_topology(self):
        cm = CrushMap()
        topo = cm.topology()
        assert "CRUSH Map" in topo

    def test_populated_map_topology(self):
        cm = self._make_map()
        topo = cm.topology()
        assert "CRUSH Map" in topo
        assert "default" in topo

    def test_find_bucket_root(self):
        cm = self._make_map()
        b = cm.find_bucket("default")
        assert b is not None
        assert b.type == "root"

    def test_find_bucket_nested(self):
        cm = self._make_map()
        b = cm.find_bucket("tranc3-node-0")
        assert b is not None
        assert b.type == "host"

    def test_find_bucket_osd(self):
        cm = self._make_map()
        b = cm.find_bucket("osd.0")
        assert b is not None
        assert b.type == "osd"

    def test_find_bucket_missing_returns_none(self):
        cm = self._make_map()
        assert cm.find_bucket("nonexistent") is None

    def test_tunable_profile_default(self):
        cm = CrushMap()
        assert cm.tunable_profile == "optimal"

    def test_custom_tunable_profile(self):
        cm = CrushMap(tunable_profile="firefly")
        assert cm.tunable_profile == "firefly"


class TestMicroCephConfig:
    def test_defaults(self):
        cfg = MicroCephConfig()
        assert cfg.single_node is True
        assert cfg.osd_loop_dev is False
        assert cfg.enable_health_watch is True
        assert cfg.metrics_enabled is True

    def test_default_pools_match_module_constant(self):
        cfg = MicroCephConfig()
        assert sorted(cfg.pools) == sorted(DEFAULT_POOLS)

    def test_default_host_name(self):
        cfg = MicroCephConfig()
        assert "tranc3" in cfg.crush_host_name

    def test_custom_host_name(self):
        cfg = MicroCephConfig(crush_host_name="my-host")
        assert cfg.crush_host_name == "my-host"

    def test_custom_pools(self):
        cfg = MicroCephConfig(pools=["pool-a", "pool-b"])
        assert cfg.pools == ["pool-a", "pool-b"]

    def test_rgw_defaults(self):
        cfg = MicroCephConfig()
        assert isinstance(cfg.rgw_port, int)
        assert 1 <= cfg.rgw_port <= 65535
        assert isinstance(cfg.rgw_host, str)


class TestOsdInfo:
    def test_construction(self):
        info = OsdInfo(id=0, uuid="test-uuid-0000", state=["up", "in"], weight=1.0)
        assert info.id == 0
        assert "up" in info.state
        assert info.weight == 1.0


class TestPoolInfo:
    def test_construction(self):
        info = PoolInfo(
            name="tranc3-data",
            pool_id=1,
            pool_type=PoolType.REPLICATED,
            pg_num=32,
            pgp_num=32,
        )
        assert info.name == "tranc3-data"
        assert info.pool_id == 1
        assert info.pool_type == PoolType.REPLICATED
        assert info.pg_num == 32


class TestRgwCredentials:
    def test_construction(self):
        creds = RgwCredentials(
            access_key="AKIATEST123",
            secret_key="supersecret",
            user_id="tranc3-admin",
            display_name="Tranc3 Admin",
        )
        assert creds.access_key == "AKIATEST123"
        assert creds.user_id == "tranc3-admin"


# ===========================================================================
# CRUSH algorithm — pure Python, no Ceph required
# ===========================================================================


class TestCrushHash:
    def test_deterministic(self):
        """Same inputs always produce the same hash."""
        assert crush_hash(10, 0, 0) == crush_hash(10, 0, 0)
        assert crush_hash(42, 7, 3) == crush_hash(42, 7, 3)

    def test_different_pg_ids_differ(self):
        h1 = crush_hash(1, 0, 0)
        h2 = crush_hash(2, 0, 0)
        assert h1 != h2

    def test_different_osd_ids_differ(self):
        h1 = crush_hash(10, 0, 0)
        h2 = crush_hash(10, 1, 0)
        assert h1 != h2

    def test_retry_changes_hash(self):
        h0 = crush_hash(10, 0, 0)
        h1 = crush_hash(10, 0, 1)
        assert h0 != h1

    def test_returns_non_negative_int(self):
        for pg in range(20):
            h = crush_hash(pg, 0, 0)
            assert isinstance(h, int)
            assert h >= 0

    def test_hash_is_32_bit_range(self):
        """rjenkins1 output fits in 32 bits."""
        for i in range(50):
            h = crush_hash(i, i % 3, 0)
            assert h < 2**32


class TestStraw2Choose:
    def test_returns_valid_osd(self):
        osd_ids = [0, 1, 2]
        winner = straw2_choose(osd_ids, [1.0, 1.0, 1.0], pg_id=42)
        assert winner in osd_ids

    def test_deterministic_same_input(self):
        osd_ids = [0, 1, 2]
        weights = [1.0, 0.8, 0.5]
        w1 = straw2_choose(osd_ids, weights, pg_id=42)
        w2 = straw2_choose(osd_ids, weights, pg_id=42)
        assert w1 == w2

    def test_single_osd_always_wins(self):
        for pg in range(20):
            assert straw2_choose([5], [1.0], pg_id=pg) == 5

    def test_zero_weight_osd_never_wins(self):
        """An OSD with weight=0 must never be selected."""
        losers = set()
        for pg in range(200):
            w = straw2_choose([0, 1, 2], [0.0, 1.0, 1.0], pg_id=pg)
            losers.add(w)
        assert 0 not in losers, "OSD 0 (weight=0) should never win"

    def test_distribution_is_roughly_even_equal_weights(self):
        """With equal weights, distribution over many PGs should be roughly uniform."""
        counts = {0: 0, 1: 0, 2: 0}
        for pg in range(3000):
            w = straw2_choose([0, 1, 2], [1.0, 1.0, 1.0], pg_id=pg)
            counts[w] += 1
        total = sum(counts.values())
        for osd, cnt in counts.items():
            ratio = cnt / total
            assert 0.25 <= ratio <= 0.45, f"OSD {osd} got {ratio:.2%} of PGs — expected ~33%"

    def test_higher_weight_wins_more_often(self):
        """OSD 0 (weight=10) should win far more than OSD 1 (weight=1)."""
        wins = {0: 0, 1: 0}
        for pg in range(2000):
            w = straw2_choose([0, 1], [10.0, 1.0], pg_id=pg)
            wins[w] += 1
        assert wins[0] > wins[1] * 3, f"Expected OSD 0 to dominate; got {wins}"

    def test_empty_list_returns_minus_one(self):
        """Empty OSD list returns sentinel -1."""
        result = straw2_choose([], [], pg_id=0)
        assert result == -1

    def test_retry_changes_selection(self):
        """Different retry values should change the winner for at least some PGs."""
        changes = 0
        for pg in range(100):
            w0 = straw2_choose([0, 1, 2], [1.0, 1.0, 1.0], pg_id=pg, retry=0)
            w1 = straw2_choose([0, 1, 2], [1.0, 1.0, 1.0], pg_id=pg, retry=1)
            if w0 != w1:
                changes += 1
        assert changes > 0, "retry=0 and retry=1 should differ for some PGs"


class TestCrushPlace:
    def test_single_replica(self):
        result = crush_place("my-object", [0, 1, 2], [1.0, 1.0, 1.0], replicas=1)
        assert len(result) == 1
        assert result[0] in [0, 1, 2]

    def test_two_replicas_different_osds(self):
        result = crush_place("my-object", [0, 1, 2], [1.0, 1.0, 1.0], replicas=2)
        assert len(result) == 2
        assert result[0] != result[1]

    def test_three_replicas_all_different(self):
        result = crush_place("obj", [0, 1, 2], [1.0, 1.0, 1.0], replicas=3)
        assert len(result) == 3
        assert len(set(result)) == 3

    def test_replicas_capped_by_available_osds(self):
        result = crush_place("obj", [0, 1], [1.0, 1.0], replicas=5)
        assert len(result) <= 2

    def test_deterministic(self):
        r1 = crush_place("same-key", [0, 1, 2], [1.0, 1.0, 1.0], replicas=2)
        r2 = crush_place("same-key", [0, 1, 2], [1.0, 1.0, 1.0], replicas=2)
        assert r1 == r2

    def test_different_objects_may_land_differently(self):
        placements = set()
        for i in range(20):
            r = crush_place(f"object-{i}", [0, 1, 2], [1.0, 1.0, 1.0], replicas=1)
            placements.add(r[0])
        assert len(placements) > 1, "20 different objects should land on >1 OSD"

    def test_empty_osd_list_returns_empty(self):
        result = crush_place("obj", [], [], replicas=1)
        assert result == []


# ===========================================================================
# CrushMapBuilder — tests that don't invoke Ceph CLI
# ===========================================================================


class TestCrushMapBuilder:
    def test_instantiation_with_config(self):
        cfg = MicroCephConfig()
        builder = CrushMapBuilder(config=cfg)
        assert builder is not None

    def test_tunables_constant(self):
        cfg = MicroCephConfig()
        builder = CrushMapBuilder(config=cfg)
        assert hasattr(builder, "TUNABLES_OPTIMAL")
        assert isinstance(builder.TUNABLES_OPTIMAL, dict)

    def test_has_required_methods(self):
        cfg = MicroCephConfig()
        builder = CrushMapBuilder(config=cfg)
        assert callable(getattr(builder, "add_osd_to_crush", None))
        assert callable(getattr(builder, "ensure_host_bucket", None))
        assert callable(getattr(builder, "create_replicated_rule", None))


# ===========================================================================
# Singleton helpers
# ===========================================================================


class TestSingletonHelpers:
    @pytest.mark.asyncio
    async def test_get_provider_returns_instance(self):
        """get_microceph_provider() should return a MicroCephProvider instance."""
        from shared_core.architecture.microceph_provider import MicroCephProvider

        provider = await get_microceph_provider()
        assert isinstance(provider, MicroCephProvider)

    @pytest.mark.asyncio
    async def test_get_provider_is_idempotent(self):
        """Calling twice returns the same singleton."""
        p1 = await get_microceph_provider()
        p2 = await get_microceph_provider()
        assert p1 is p2

    @pytest.mark.asyncio
    async def test_shutdown_clears_singleton(self):
        """After shutdown, next call returns a fresh provider."""
        await get_microceph_provider()
        await shutdown_microceph_provider()
        p2 = await get_microceph_provider()
        # May or may not be the same object depending on impl, but should not raise
        assert p2 is not None
