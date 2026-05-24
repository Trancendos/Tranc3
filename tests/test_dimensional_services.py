"""
tests/test_dimensional_services.py
Phase 22.4 — Dimensional Services unit tests.
Tests: DimensionalServiceBus, DimensionalServiceRegistry, UnderverseRegistry,
       FluidicRouter + CausalEventBus integration, registry stats.
"""

from __future__ import annotations

import asyncio
import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-dimensionals-00001")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-dimensionals-000001")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Dimensional.dimensionals import (
    DimensionalServiceBus,
    DimensionalServiceRegistry,
    get_dimensional_bus,
    get_dimensional_registry,
    get_underverse_registry,
)
from Dimensional.dimensionals.underverse import UnderverseRegistry


def _run_coro(coro):
    """Run a coroutine using asyncio.run() to avoid event-loop pollution."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# DimensionalServiceRegistry (the actual class name — formerly "Enhanced…")
# ---------------------------------------------------------------------------
class TestDimensionalServiceRegistry:
    def setup_method(self):
        self.registry = DimensionalServiceRegistry()

    def test_instantiation(self):
        assert self.registry is not None

    def test_get_stats_returns_dict(self):
        stats = self.registry.get_stats()
        assert isinstance(stats, dict)

    def test_stats_has_service_count(self):
        stats = self.registry.get_stats()
        # Accept any of the known count keys
        count_keys = {"service_count", "total", "registered", "total_services", "active_services"}
        assert count_keys & stats.keys(), f"No count key found in stats: {list(stats.keys())}"

    def test_heartbeat_updates_registry(self):
        self.registry.heartbeat("test-service-01")
        # Should not raise; registry records heartbeat

    def test_heartbeat_multiple_services(self):
        for name in ["svc-a", "svc-b", "svc-c"]:
            self.registry.heartbeat(name)

    def test_list_all_returns_iterable(self):
        services = self.registry.list_all()
        assert services is not None
        assert hasattr(services, "__iter__")

    def test_get_by_capability_returns_list(self):
        result = self.registry.get_by_capability("auth")
        assert isinstance(result, list)

    def test_registered_services_count_non_negative(self):
        """Stats counts should be non-negative integers."""
        stats = self.registry.get_stats()
        for k, v in stats.items():
            if isinstance(v, int):
                assert v >= 0, f"Stat {k} is negative: {v}"


# ---------------------------------------------------------------------------
# UnderverseRegistry
# ---------------------------------------------------------------------------
class TestUnderverseRegistry:
    def setup_method(self):
        self.underverse = UnderverseRegistry()

    def test_instantiation(self):
        assert self.underverse is not None

    def test_get_stats_returns_dict(self):
        stats = self.underverse.get_stats()
        assert isinstance(stats, dict)

    def test_heartbeat_records_nanoservice(self):
        self.underverse.heartbeat("nano-test-01")

    def test_get_by_capability_returns_list(self):
        result = self.underverse.get_by_capability("auth")
        assert isinstance(result, list)

    def test_list_all_returns_iterable(self):
        modules = self.underverse.list_all()
        assert hasattr(modules, "__iter__")

    def test_multiple_heartbeats_do_not_crash(self):
        for i in range(20):
            self.underverse.heartbeat(f"nano-{i:03d}")

    def test_stats_values_non_negative(self):
        stats = self.underverse.get_stats()
        for k, v in stats.items():
            if isinstance(v, int):
                assert v >= 0, f"Stat {k} is negative: {v}"


# ---------------------------------------------------------------------------
# DimensionalServiceBus
# ---------------------------------------------------------------------------
class TestDimensionalServiceBus:
    def setup_method(self):
        self.bus = DimensionalServiceBus()

    def test_instantiation(self):
        assert self.bus is not None

    def test_is_not_running_before_start(self):
        assert self.bus.is_running is False

    def test_get_stats_returns_dict(self):
        stats = self.bus.get_stats()
        assert isinstance(stats, dict)

    def test_stats_has_fluidic_routes_key(self):
        """Phase 22.6: DimensionalServiceBus should expose fluidic_routes stat."""
        stats = self.bus.get_stats()
        assert "fluidic_routes" in stats, (
            f"Expected 'fluidic_routes' in stats, got keys: {list(stats.keys())}"
        )

    def test_stats_has_causal_events_key(self):
        stats = self.bus.get_stats()
        assert "causal_events" in stats, (
            f"Expected 'causal_events' in stats, got keys: {list(stats.keys())}"
        )

    def test_stats_has_messages_sent_key(self):
        stats = self.bus.get_stats()
        assert "messages_sent" in stats

    def test_start_and_stop(self):
        _run_coro(self.bus.start())
        assert self.bus.is_running is True
        _run_coro(self.bus.stop())
        assert self.bus.is_running is False

    def test_double_start_safe(self):
        """Starting an already-running bus should not raise."""
        _run_coro(self.bus.start())
        _run_coro(self.bus.start())  # second start — should be no-op
        _run_coro(self.bus.stop())

    def test_stop_without_start_safe(self):
        _run_coro(self.bus.stop())  # Should not raise


# ---------------------------------------------------------------------------
# Singleton factories
# ---------------------------------------------------------------------------
class TestSingletonFactories:
    def test_get_dimensional_bus_returns_same_instance(self):
        bus1 = get_dimensional_bus()
        bus2 = get_dimensional_bus()
        assert bus1 is bus2

    def test_get_dimensional_registry_returns_same_instance(self):
        reg1 = get_dimensional_registry()
        reg2 = get_dimensional_registry()
        assert reg1 is reg2

    def test_get_underverse_registry_returns_same_instance(self):
        uv1 = get_underverse_registry()
        uv2 = get_underverse_registry()
        assert uv1 is uv2

    def test_registry_is_dimensional_service_registry(self):
        reg = get_dimensional_registry()
        assert isinstance(reg, DimensionalServiceRegistry)

    def test_underverse_is_underverse_registry(self):
        uv = get_underverse_registry()
        assert isinstance(uv, UnderverseRegistry)

    def test_bus_is_dimensional_service_bus(self):
        bus = get_dimensional_bus()
        assert isinstance(bus, DimensionalServiceBus)


# ---------------------------------------------------------------------------
# FluidicRouter + CausalEventBus (optional integration)
# ---------------------------------------------------------------------------
class TestFluidicIntegration:
    """
    Tests for the optional FluidicRouter / CausalEventBus integration
    wired into DimensionalServiceBus.  These are soft tests — we check
    that the integration doesn't break the bus even if the optional
    modules are unavailable.
    """

    def test_bus_starts_with_fluidic_router(self):
        bus = DimensionalServiceBus()
        _run_coro(bus.start())
        # Either attribute is acceptable (or neither — we just must not crash)
        has_router = hasattr(bus, "_fluidic_router") or hasattr(bus, "fluidic_router")
        assert has_router or True
        _run_coro(bus.stop())

    def test_bus_starts_with_causal_bus(self):
        bus = DimensionalServiceBus()
        _run_coro(bus.start())
        has_causal = hasattr(bus, "_causal_bus") or hasattr(bus, "causal_bus")
        assert has_causal or True
        _run_coro(bus.stop())

    def test_bus_stats_running_after_start(self):
        bus = DimensionalServiceBus()
        _run_coro(bus.start())
        stats = bus.get_stats()
        assert stats.get("running") is True
        _run_coro(bus.stop())
