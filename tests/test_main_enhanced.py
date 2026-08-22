import pytest
from src.main_enhanced import TRANC3Enhanced


@pytest.mark.asyncio
async def test_get_system_health():
    # Setup mock subsystems
    class MockMonitor:
        def get_dashboard(self):
            return {"cpu": "ok"}

    class MockEvolution:
        def get_stats(self):
            return {"generations": 5}

    class MockSkillRegistry:
        def get_stats(self):
            return {"skills": 10}

    class MockBotDispatcher:
        def get_bot_stats(self):
            return {"active_bots": 3}

    system = TRANC3Enhanced()
    system._subsystems = {
        "health_monitor": MockMonitor(),
        "evolution": MockEvolution(),
        "skill_registry": MockSkillRegistry(),
        "bot_dispatcher": MockBotDispatcher(),
    }
    system._initialized = True

    health = await system.get_system_health()

    assert health["services"] == {"cpu": "ok"}
    assert health["evolution"] == {"generations": 5}
    assert health["skills"] == {"skills": 10}
    assert health["bots"] == {"active_bots": 3}
    assert "health_monitor" in health["subsystems_active"]
    assert health["initialized"] is True


@pytest.mark.asyncio
async def test_get_system_health_empty():
    system = TRANC3Enhanced()
    system._subsystems = {}
    system._initialized = False

    health = await system.get_system_health()

    assert health["services"] == {}
    assert health["evolution"] == {}
    assert health["skills"] == {}
    assert health["bots"] == {}
    assert health["subsystems_active"] == []
    assert health["initialized"] is False
