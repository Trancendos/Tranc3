"""
Design system tests — energy constants, tier base classes, proactive health,
auto-evolve scheduler. All zero-cost, no external deps.
"""

from __future__ import annotations

import asyncio
import pytest


async def _poll_until(condition, *, timeout: float = 2.0, interval: float = 0.01) -> None:
    """Spin until *condition* returns True or *timeout* seconds elapse."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if condition():
            return
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Energy constants
# ---------------------------------------------------------------------------


class TestEnergyConstants:
    def test_import(self):
        from src.bridge.energy_constants import (
            BridgeType,
            BRIDGE_DEFAULT_ENERGY,
            CRYSTAL_BASE_COST,
            DIALITHIUM_PRIORITY,
            EnergyClass,
            LIGHT_AMBIENT_TICK_HZ,
            LIGHTNING_BURST_LIMIT_MS,
            cost_for,
            priority_for,
        )

        assert DIALITHIUM_PRIORITY == 1
        assert CRYSTAL_BASE_COST == 0.6
        assert LIGHTNING_BURST_LIMIT_MS == 50.0
        assert LIGHT_AMBIENT_TICK_HZ == 10.0
        assert EnergyClass is not None
        assert BridgeType is not None
        assert cost_for is not None
        assert priority_for is not None
        assert BRIDGE_DEFAULT_ENERGY is not None

    def test_cost_ordering(self):
        from src.bridge.energy_constants import EnergyClass, cost_for

        dialithium = cost_for(EnergyClass.DIALITHIUM)
        trilithium = cost_for(EnergyClass.TRILITHIUM)
        crystal = cost_for(EnergyClass.CRYSTAL)
        lightning = cost_for(EnergyClass.LIGHTNING)
        light = cost_for(EnergyClass.LIGHT)

        # Higher priority = higher cost factor (Dialithium is most expensive to route)
        assert dialithium > trilithium > crystal > lightning >= light

    def test_priority_ordering(self):
        from src.bridge.energy_constants import EnergyClass, priority_for

        # Lower priority number = higher priority
        assert priority_for(EnergyClass.DIALITHIUM) < priority_for(EnergyClass.CRYSTAL)
        assert priority_for(EnergyClass.CRYSTAL) < priority_for(EnergyClass.LIGHT)

    def test_bridge_default_energy(self):
        from src.bridge.energy_constants import BridgeType, EnergyClass, BRIDGE_DEFAULT_ENERGY

        assert BRIDGE_DEFAULT_ENERGY[BridgeType.CRYSTAL] == EnergyClass.DIALITHIUM
        assert BRIDGE_DEFAULT_ENERGY[BridgeType.TRANSWARP] == EnergyClass.LIGHTNING
        assert BRIDGE_DEFAULT_ENERGY[BridgeType.CELL] == EnergyClass.LIGHT

    def test_all_energy_classes_covered(self):
        from src.bridge.energy_constants import EnergyClass, ENERGY_COST_FACTOR, ENERGY_PRIORITY

        for ec in EnergyClass:
            assert ec in ENERGY_COST_FACTOR, f"{ec} missing from ENERGY_COST_FACTOR"
            assert ec in ENERGY_PRIORITY, f"{ec} missing from ENERGY_PRIORITY"


# ---------------------------------------------------------------------------
# Tier base class templates
# ---------------------------------------------------------------------------


class TestTranc3Base:
    def test_instantiation(self):
        from src.entities.templates.tranc3_base import Tranc3

        class TestLeadAI(Tranc3):
            async def process(self, payload):
                return {"ok": True}

        ai = TestLeadAI(aid="AID-TST-01", location_pid="PID-TST", name="Test-AI")
        assert ai.dna.aid == "AID-TST-01"
        assert ai.dna.tier == 3
        assert ai.TIER == 3

    def test_status(self):
        from src.entities.templates.tranc3_base import Tranc3

        class TestLeadAI(Tranc3):
            async def process(self, payload):
                return {}

        ai = TestLeadAI(aid="AID-TST-02", location_pid="PID-TST", name="Test-AI-2")
        s = ai.status()
        assert s["tier"] == 3
        assert s["health_score"] == 1.0
        assert s["running"] is False

    def test_swot_assessment(self):
        from src.entities.templates.tranc3_base import Tranc3

        class TestLeadAI(Tranc3):
            async def process(self, payload):
                return {}

        ai = TestLeadAI(aid="AID-TST-03", location_pid="PID-TST", name="Test-AI-3")
        snap = ai.assess_swot()
        # High health → strength present
        assert any("health" in s.lower() for s in snap.strengths)

    def test_hub_powerup(self):
        from src.entities.templates.tranc3_base import Tranc3, HubPowerUp

        class TestLeadAI(Tranc3):
            async def process(self, payload):
                return {}

        ai = TestLeadAI(aid="AID-TST-04", location_pid="PID-TST", name="Test-AI-4")
        pu = HubPowerUp(name="turbo", description="Turbo mode")
        ai.register_hub_powerup(pu)
        assert not pu.active
        ai.enter_hub()
        assert pu.active
        ai.leave_hub()
        assert not pu.active

    @pytest.mark.asyncio
    async def test_lifecycle(self):
        from src.entities.templates.tranc3_base import Tranc3

        class TestLeadAI(Tranc3):
            async def process(self, payload):
                return {}

        ai = TestLeadAI(aid="AID-TST-05", location_pid="PID-TST", name="Test-AI-5")
        await ai.start()
        assert ai._running
        await asyncio.sleep(0)  # yield to let the task initialise
        await ai.stop()
        assert not ai._running


class TestInfinityAgentBase:
    def test_role_validation(self):
        from src.entities.templates.infinity_agent_base import InfinityAgent

        with pytest.raises(ValueError):
            InfinityAgent(sid="SID-X", location_pid="PID-X", name="X", role="gamma")

    def test_alpha_beta(self):
        from src.entities.templates.infinity_agent_base import InfinityAgent

        alpha = InfinityAgent(sid="SID-A", location_pid="PID-X", name="A", role="alpha")
        beta = InfinityAgent(sid="SID-B", location_pid="PID-X", name="B", role="beta")
        assert alpha.dna.role == "alpha"
        assert beta.dna.role == "beta"

    @pytest.mark.asyncio
    async def test_enqueue_and_process(self):
        from src.entities.templates.infinity_agent_base import InfinityAgent, AgentTask

        class TestAgent(InfinityAgent):
            pass

        agent = TestAgent(sid="SID-T1", location_pid="PID-X", name="T1", role="alpha")

        async def handler(task: AgentTask) -> dict:
            return {"handled": task.task_type}

        agent.register_handler("ping", handler)
        await agent.start()
        task = await agent.enqueue("ping", {"msg": "hello"})
        await _poll_until(lambda: any(t.task_id == task.task_id for t in agent._completed))
        await agent.stop()
        assert any(t.task_id == task.task_id for t in agent._completed)


class TestInfinityBotBase:
    def test_slot_validation(self):
        from src.entities.templates.infinity_bot_base import InfinityBot

        # Must use a concrete subclass — abstract class raises TypeError before __init__
        class _ConcreteBot(InfinityBot):
            async def run_task(self) -> dict:
                return {}

        with pytest.raises(ValueError):
            _ConcreteBot(nid="NID-X", location_pid="PID-X", name="X", slot="05")

    @pytest.mark.asyncio
    async def test_run_task_lifecycle(self):
        from src.entities.templates.infinity_bot_base import InfinityBot

        class CountBot(InfinityBot):
            def __init__(self):
                super().__init__(
                    nid="NID-CB-01",
                    location_pid="PID-TST",
                    name="Count-Bot",
                    slot="01",
                    interval_seconds=0.05,
                )
                self.run_count = 0

            async def run_task(self) -> dict:
                self.run_count += 1
                return {"count": self.run_count}

        bot = CountBot()
        await bot.start()
        await _poll_until(lambda: bot.run_count >= 1)
        await bot.stop()
        assert bot.run_count >= 1
        assert bot.success_rate() > 0.0


# ---------------------------------------------------------------------------
# Proactive health monitor
# ---------------------------------------------------------------------------


class TestProactiveHealthMonitor:
    def test_register_and_check(self, tmp_path):
        from src.observability.proactive_health import ProactiveHealthMonitor
        from src.entities.templates.tranc3_base import Tranc3

        class TestAI(Tranc3):
            async def process(self, p):
                return {}

        monitor = ProactiveHealthMonitor(db_path=tmp_path / "health.db")
        ai = TestAI(aid="AID-HM-01", location_pid="PID-HM", name="HM-AI")
        monitor.register(ai)

        alerts = monitor.check_all()
        # Healthy entity → no alerts
        assert all(a.severity != "critical" for a in alerts)

    def test_critical_alert_on_low_health(self, tmp_path):
        from src.observability.proactive_health import ProactiveHealthMonitor
        from src.entities.templates.tranc3_base import Tranc3

        class SickAI(Tranc3):
            async def process(self, p):
                return {}

        monitor = ProactiveHealthMonitor(db_path=tmp_path / "health2.db")
        ai = SickAI(aid="AID-HM-02", location_pid="PID-HM", name="Sick-AI")
        ai._health_score = 0.1  # Force critical health
        monitor.register(ai)

        # Need multiple samples for EWMA to converge
        for _ in range(5):
            monitor.check_all()

        assert any(a.severity == "critical" for a in monitor._alerts)

    def test_status(self, tmp_path):
        from src.observability.proactive_health import ProactiveHealthMonitor

        monitor = ProactiveHealthMonitor(db_path=tmp_path / "health3.db")
        s = monitor.status()
        assert "registered_entities" in s
        assert "total_alerts" in s


# ---------------------------------------------------------------------------
# AutoEvolve
# ---------------------------------------------------------------------------


class TestAutoEvolve:
    def test_register(self, tmp_path):
        from src.entities.auto_evolve import AutoEvolve
        from src.entities.templates.tranc3_base import Tranc3

        class EvolveAI(Tranc3):
            async def process(self, p):
                return {}

        ae = AutoEvolve(db_path=tmp_path / "evo.db")
        ai = EvolveAI(aid="AID-EV-01", location_pid="PID-EV", name="Evo-AI")
        ae.register(ai)
        s = ae.status()
        assert s["registered"] == 1

    @pytest.mark.asyncio
    async def test_evolve_entity_no_genetic(self, tmp_path):
        from src.entities.auto_evolve import AutoEvolve
        from src.entities.templates.tranc3_base import Tranc3

        class SimpleAI(Tranc3):
            async def process(self, p):
                return {}

        ae = AutoEvolve(interval_seconds=0.0, db_path=tmp_path / "evo2.db")
        ai = SimpleAI(aid="AID-EV-02", location_pid="PID-EV", name="Simple-AI")
        ae.register(ai)
        # evolve() returns {} when genetics not available — should not raise
        await ae._evolve_entity("AID-EV-02", ai)
