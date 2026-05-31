"""Backward-compatibility shim.

The canonical implementation now lives in
``Dimensional.architecture.microceph_provider`` after the
``shared_core`` → ``Dimensional`` rename. This module re-exports the
public (and a few test-referenced private) symbols so legacy imports of
``shared_core.architecture.microceph_provider`` keep working.
"""

from __future__ import annotations

from Dimensional.architecture.microceph_provider import (  # noqa: F401
    DEFAULT_POOLS,
    MAX_PG_COUNT,
    MICROCEPH_CMD,
    MIN_PG_COUNT,
    OSD_TARGET_PG_PER_OSD,
    CephHealthStatus,
    CrushBucket,
    CrushMap,
    CrushMapBuilder,
    MicroCephConfig,
    MicroCephProvider,
    OsdInfo,
    OsdState,
    PoolInfo,
    PoolType,
    RgwCredentials,
    crush_hash,
    crush_place,
    get_microceph_provider,
    shutdown_microceph_provider,
    straw2_choose,
)

__all__ = [
    "DEFAULT_POOLS",
    "MICROCEPH_CMD",
    "MIN_PG_COUNT",
    "MAX_PG_COUNT",
    "OSD_TARGET_PG_PER_OSD",
    "CephHealthStatus",
    "CrushBucket",
    "CrushMap",
    "CrushMapBuilder",
    "MicroCephConfig",
    "MicroCephProvider",
    "OsdInfo",
    "OsdState",
    "PoolInfo",
    "PoolType",
    "RgwCredentials",
    "crush_hash",
    "crush_place",
    "straw2_choose",
    "get_microceph_provider",
    "shutdown_microceph_provider",
]
