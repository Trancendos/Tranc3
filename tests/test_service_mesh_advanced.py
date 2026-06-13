"""
Tests for advanced service mesh: quota enforcer, nano mesh,
quantum router, genetic router, meta router.
"""

from __future__ import annotations

import asyncio
import pytest


# ── QuotaEnforcer ─────────────────────────────────────────────────────────────


def test_quota_enforcer_basic(tmp_path):
    from src.mesh.quota_enforcer import QuotaEnforcer

    e = QuotaEnforcer(db_path=str(tmp_path / "q.db"), threshold_pct=80.0)

    # Fresh — not blocked
    assert not e.is_blocked("groq")
    assert e.select_provider() in ["ollama", "groq", "cerebras", "offline"]


def test_quota_enforcer_hard_stop(tmp_path):
    from datetime import datetime, timezone

    from src.mesh.quota_enforcer import PROVIDER_LIMITS, QuotaEnforcer

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    e = QuotaEnforcer(db_path=str(tmp_path / "q.db"), threshold_pct=80.0)

    # Push groq to 81% of daily_requests
    limit = PROVIDER_LIMITS["groq"]["daily_requests"]
    over = int(limit * 0.82)
    e._inc("groq", "daily_requests", over, today)

    assert e.is_blocked("groq")
    # Should rotate away from groq
    provider = e.select_provider(preferred="groq")
    assert provider != "groq"


def test_quota_enforcer_rotation_chain(tmp_path):
    from datetime import datetime, timezone

    from src.mesh.quota_enforcer import PROVIDER_LIMITS, ROTATION_ORDER, QuotaEnforcer

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    e = QuotaEnforcer(db_path=str(tmp_path / "q.db"), threshold_pct=80.0)

    # Block all except offline and ollama
    blocked = [p for p in ROTATION_ORDER if p not in ("ollama", "offline")]
    for p in blocked:
        limit = PROVIDER_LIMITS[p].get("daily_requests", 100)
        if limit != float("inf"):
            e._inc(p, "daily_requests", int(limit * 0.9), today)
        else:
            # Use tokens
            limit = PROVIDER_LIMITS[p].get("daily_tokens", 100)
            if limit != float("inf"):
                e._inc(p, "daily_tokens", int(limit * 0.9), today)

    provider = e.select_provider()
    assert provider in ("ollama", "offline")


def test_quota_enforcer_dashboard(tmp_path):
    from src.mesh.quota_enforcer import QuotaEnforcer

    e = QuotaEnforcer(db_path=str(tmp_path / "q.db"))
    dash = e.dashboard()
    assert "providers" in dash
    assert dash["threshold_pct"] == 80.0
    assert len(dash["providers"]) >= 8


# ── NanoMesh ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_nano_mesh_basic():
    from src.mesh.nano_mesh import NanoMesh

    mesh = NanoMesh()
    call_log = []

    @mesh.register("greet")
    async def hello(name: str) -> str:
        call_log.append(name)
        return f"Hello, {name}!"

    result = await mesh.call("greet", name="World")
    assert result == "Hello, World!"
    assert "World" in call_log


@pytest.mark.asyncio
async def test_nano_mesh_fallback():
    from src.mesh.nano_mesh import NanoMesh

    mesh = NanoMesh()
    primary_calls = []
    fallback_calls = []

    @mesh.register("proc", weight=1.0)
    async def primary(*args, **kwargs):
        primary_calls.append(1)
        raise RuntimeError("primary failed")

    @mesh.register("proc", weight=2.0)
    async def fallback(*args, **kwargs):
        fallback_calls.append(1)
        return "fallback ok"

    # Primary is selected first (weight 1 vs 2 — p2c picks higher effective weight)
    # Force primary's circuit open by simulating many errors
    mesh._functions["proc"][0].error_count = 10
    mesh._functions["proc"][0].call_count = 10
    mesh._functions["proc"][0].open_until = 9999999999.0  # force open

    result = await mesh.call("proc")
    assert result == "fallback ok"


@pytest.mark.asyncio
async def test_nano_mesh_no_capability():
    from src.mesh.nano_mesh import NanoMesh

    mesh = NanoMesh()
    with pytest.raises(RuntimeError, match="no function registered"):
        await mesh.call("nonexistent")


# ── QuantumRouter ─────────────────────────────────────────────────────────────


def test_quantum_router_collapse():
    from src.mesh.quantum_router import QuantumRouter

    router = QuantumRouter()
    router.add_route("a", initial_amplitude=2.0)
    router.add_route("b", initial_amplitude=1.0)

    selected = [router.collapse() for _ in range(100)]
    assert all(s in ("a", "b") for s in selected)
    # 'a' should be selected more often (higher amplitude)
    a_count = selected.count("a")
    assert a_count > 40  # statistically should dominate


def test_quantum_router_interference():
    from src.mesh.quantum_router import QuantumRouter

    router = QuantumRouter()
    r = router.add_route("a", initial_amplitude=2.0)
    initial_amp = r.amplitude

    router.record_failure("a")
    assert r.amplitude < initial_amp  # Destructive interference


def test_quantum_router_amplification():
    from src.mesh.quantum_router import QuantumRouter

    router = QuantumRouter()
    r = router.add_route("a", initial_amplitude=1.0)
    router.add_route("b", initial_amplitude=1.0)

    router.record_success("a", latency_ms=50.0)
    # After normalization, 'a' should have higher probability than 'b'
    assert r.probability >= router._routes["b"].probability


def test_quantum_router_entanglement():
    from src.mesh.quantum_router import QuantumRouter

    router = QuantumRouter()
    router.add_route("a", initial_amplitude=1.0, entangled_with="b")
    router.add_route("b", initial_amplitude=1.0, entangled_with="a")

    # After failure of 'a', b should have higher relative probability than a
    router.record_failure("a")
    b_prob = router._routes["b"].probability
    a_prob = router._routes["a"].probability
    assert b_prob > a_prob  # b wins after a fails


def test_quantum_router_exclude():
    from src.mesh.quantum_router import QuantumRouter

    router = QuantumRouter()
    router.add_route("a", initial_amplitude=2.0)
    router.add_route("b", initial_amplitude=1.0)

    for _ in range(20):
        selected = router.collapse(exclude=["a"])
        assert selected == "b"


# ── GeneticRouter ─────────────────────────────────────────────────────────────


def test_genetic_router_select():
    from src.mesh.genetic_router import GeneticRouter

    router = GeneticRouter()
    router.add_route("x", initial_pheromone=2.0)
    router.add_route("y", initial_pheromone=1.0)

    selected = [router.select() for _ in range(50)]
    assert all(s in ("x", "y") for s in selected)


def test_genetic_router_pheromone_deposit():
    from src.mesh.genetic_router import GeneticRouter

    router = GeneticRouter()
    g = router.add_route("z", initial_pheromone=1.0)
    initial = g.pheromone

    router.record_success("z", latency_ms=50.0)
    assert g.pheromone > initial  # Pheromone deposit after success


def test_genetic_router_evaporation():
    from src.mesh.genetic_router import GeneticRouter

    router = GeneticRouter()
    g = router.add_route("w", initial_pheromone=2.0)

    router.record_failure("w")
    assert g.pheromone < 2.0  # Evaporation after failure


def test_genetic_router_ranked():
    from src.mesh.genetic_router import GeneticRouter

    router = GeneticRouter()
    router.add_route("fast", initial_pheromone=3.0)
    router.add_route("slow", initial_pheromone=0.5)

    # Record fast's success
    router.record_success("fast", latency_ms=10.0)
    router.record_failure("slow")

    ranked = router.ranked()
    assert ranked[0].name == "fast"


# ── MetaRouter ────────────────────────────────────────────────────────────────


def test_meta_router_select():
    from src.mesh.meta_router import MetaRouter

    router = MetaRouter()
    # register some metrics
    router.register_route("ollama")
    router.register_route("groq")

    result = router.select()
    assert isinstance(result, str)
    assert len(result) > 0


def test_meta_router_record():
    from src.mesh.meta_router import MetaRouter

    router = MetaRouter()
    router.register_route("ollama")

    router.record_success("ollama", latency_ms=30.0)
    assert router._metrics["ollama"].call_count == 1
    assert router._metrics["ollama"].ewma_latency_ms < 100.0

    router.record_failure("ollama")
    assert router._metrics["ollama"].ewma_error_rate > 0


def test_meta_router_canary_rollback():
    from src.mesh.meta_router import MetaRouter

    router = MetaRouter()
    router.set_canary("new_model", traffic_pct=100.0)  # 100% canary for test

    # Simulate many failures
    m = router._metrics["new_model"]
    m.canary_errors = 5
    m.canary_calls = 20  # 25% error rate > 10% threshold

    # Next canary check should rollback
    router._check_canary()  # or select() triggers it
    assert m.canary_traffic_pct == 0.0
