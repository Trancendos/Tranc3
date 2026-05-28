"""
Tests for AeonMind Bot Services.
"""


from aeonmind.services.bot_services import (
    BotCapability,
    BotServiceConfig,
    BotServiceRegistry,
    BotServiceWorker,
    BotStatus,
)


class TestBotCapability:
    """Tests for the BotCapability enum."""

    def test_capability_count(self):
        assert len(BotCapability) >= 10

    def test_specific_capabilities(self):
        assert BotCapability.TRANSLATE.value == "translate"
        assert BotCapability.SUMMARIZE.value == "summarize"
        assert BotCapability.MONITOR.value == "monitor"


class TestBotServiceWorker:
    """Tests for BotServiceWorker (Tier 5 — Stateless Worker)."""

    def test_bot_worker_creation(self):
        config = BotServiceConfig(name="test-bot", capability=BotCapability.TRANSLATE)
        bot = BotServiceWorker(config)
        assert bot.config.name == "test-bot"
        assert bot.status == BotStatus.IDLE

    def test_bot_worker_execute(self):
        config = BotServiceConfig(name="exec-bot", capability=BotCapability.SUMMARIZE)
        bot = BotServiceWorker(config)
        result = bot.execute({"text": "Hello world"})
        assert result.status == BotStatus.COMPLETED
        assert result.success is True

    def test_bot_is_stateless(self):
        config = BotServiceConfig(name="stateless-bot")
        bot = BotServiceWorker(config)
        assert bot.config.stateless is True


class TestBotServiceRegistry:
    """Tests for the BotServiceRegistry."""

    def test_registry_creation(self):
        registry = BotServiceRegistry()
        assert len(registry) == 0

    def test_registry_register(self):
        registry = BotServiceRegistry()
        config = BotServiceConfig(name="reg-bot", capability=BotCapability.MONITOR)
        bot = BotServiceWorker(config)
        registry.register("bot-1", bot)
        assert len(registry) == 1

    def test_registry_get(self):
        registry = BotServiceRegistry()
        config = BotServiceConfig(name="get-bot", capability=BotCapability.VALIDATE)
        bot = BotServiceWorker(config)
        registry.register("bot-1", bot)
        retrieved = registry.get("bot-1")
        assert retrieved is not None
        assert retrieved.config.name == "get-bot"

    def test_registry_unregister(self):
        registry = BotServiceRegistry()
        config = BotServiceConfig(name="unreg-bot")
        bot = BotServiceWorker(config)
        registry.register("bot-1", bot)
        registry.unregister("bot-1")
        assert len(registry) == 0

    def test_registry_list_by_capability(self):
        registry = BotServiceRegistry()
        for i in range(3):
            config = BotServiceConfig(
                name=f"bot-{i}",
                capability=BotCapability.TRANSLATE if i < 2 else BotCapability.SUMMARIZE,
            )
            registry.register(f"bot-{i}", BotServiceWorker(config))

        translate_bots = registry.list_by_capability(BotCapability.TRANSLATE)
        assert len(translate_bots) == 2
