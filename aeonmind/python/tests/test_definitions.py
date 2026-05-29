"""
Tests for AeonMind Definitions — Tier Hierarchy, Entity Types, Sentinel Channels.
"""

from aeonmind.core.definitions import (
    AgentEntity,
    AiComplex,
    BotService,
    SentinelChannel,
    Tier,
    sentinel_channels,
    tier_hierarchy,
)


class TestTier:
    """Tests for the Tier enum."""

    def test_tier_values(self):
        assert Tier.HUMAN == 0
        assert Tier.ORCHESTRATOR == 1
        assert Tier.PRIME == 2
        assert Tier.AI == 3
        assert Tier.AGENT == 4
        assert Tier.BOT == 5

    def test_tier_ordering(self):
        assert Tier.HUMAN < Tier.ORCHESTRATOR
        assert Tier.ORCHESTRATOR < Tier.PRIME
        assert Tier.PRIME < Tier.AI
        assert Tier.AI < Tier.AGENT
        assert Tier.AGENT < Tier.BOT

    def test_tier_count(self):
        assert len(Tier) == 6

    def test_custom_hierarchy(self):
        """AI = ML/LLM Complex (T3) | Agent = Autonomous AI (T4) | Bot = Worker (T5)"""
        assert Tier.AI == 3
        assert Tier.AGENT == 4
        assert Tier.BOT == 5
        assert Tier.AI < Tier.AGENT  # AI is higher in hierarchy than Agent


class TestSentinelChannel:
    """Tests for the SentinelChannel enum."""

    def test_channel_count(self):
        assert len(SentinelChannel) == 11

    def test_channel_values(self):
        assert SentinelChannel.PLATFORM.value == "platform"
        assert SentinelChannel.AGENTS.value == "agents"
        assert SentinelChannel.MODELS.value == "models"
        assert SentinelChannel.WORKFLOWS.value == "workflows"
        assert SentinelChannel.SECURITY.value == "security"
        assert SentinelChannel.HIVE.value == "hive"
        assert SentinelChannel.NEXUS.value == "nexus"
        assert SentinelChannel.BRIDGE.value == "bridge"
        assert SentinelChannel.PILLARS.value == "pillars"
        assert SentinelChannel.INFRASTRUCTURE.value == "infrastructure"
        assert SentinelChannel.EVENTS.value == "events"


class TestBotService:
    """Tests for BotService (Tier 5 — Stateless Worker)."""

    def test_bot_creation(self):
        bot = BotService(name="test-bot", capability="translate")
        assert bot.name == "test-bot"
        assert bot.capability == "translate"
        assert bot.stateless is True
        assert bot.status == "idle"

    def test_bot_execute(self):
        bot = BotService(name="exec-bot")
        result = bot.execute({"action": "process"})
        assert result["status"] == "completed"
        assert result["bot_id"] == bot.id
        assert bot.status == "idle"  # Returns to idle after execution

    def test_bot_is_stateless(self):
        bot = BotService()
        assert bot.stateless is True

    def test_bot_custom_id(self):
        bot = BotService(id="custom-id")
        assert bot.id == "custom-id"


class TestAgentEntity:
    """Tests for AgentEntity (Tier 4 — Autonomous AI)."""

    def test_agent_creation(self):
        agent = AgentEntity(name="test-agent")
        assert agent.name == "test-agent"
        assert agent.tier == Tier.AGENT
        assert agent.confidence == 0.0
        assert agent.status == "idle"

    def test_agent_can_act_autonomously(self):
        agent = AgentEntity(confidence=0.7)
        assert agent.can_act_autonomously() is True

    def test_agent_cannot_act_autonomously(self):
        agent = AgentEntity(confidence=0.3)
        assert agent.can_act_autonomously() is False

    def test_agent_can_act_with_explicit_confidence(self):
        agent = AgentEntity(confidence=0.3)
        assert agent.can_act_autonomously(confidence=0.8) is True
        assert agent.can_act_autonomously(confidence=0.2) is False

    def test_agent_subscribe(self):
        agent = AgentEntity()
        agent.subscribe(SentinelChannel.AGENTS)
        assert SentinelChannel.AGENTS in agent.subscriptions

    def test_agent_unsubscribe(self):
        agent = AgentEntity()
        agent.subscribe(SentinelChannel.AGENTS)
        agent.unsubscribe(SentinelChannel.AGENTS)
        assert SentinelChannel.AGENTS not in agent.subscriptions


class TestAiComplex:
    """Tests for AiComplex (Tier 3 — ML/LLM Complex)."""

    def test_ai_complex_creation(self):
        ai = AiComplex(name="test-ai")
        assert ai.name == "test-ai"
        assert ai.tier == Tier.AI
        assert len(ai.agents) == 0
        assert len(ai.bots) == 0

    def test_add_agent_with_id(self):
        ai = AiComplex(name="test-ai")
        agent = ai.add_agent("agent-1")
        assert "agent-1" in ai.agents
        assert agent.id == "agent-1"

    def test_add_agent_with_object(self):
        ai = AiComplex(name="test-ai")
        agent_obj = AgentEntity(name="my-agent")
        agent = ai.add_agent("agent-1", agent_obj)
        assert agent.name == "my-agent"
        assert agent.id == "agent-1"

    def test_remove_agent(self):
        ai = AiComplex(name="test-ai")
        ai.add_agent("agent-1")
        removed = ai.remove_agent("agent-1")
        assert removed is not None
        assert "agent-1" not in ai.agents

    def test_add_bot_with_id(self):
        ai = AiComplex(name="test-ai")
        bot = ai.add_bot("bot-1")
        assert "bot-1" in ai.bots
        assert bot.id == "bot-1"

    def test_add_bot_with_object(self):
        ai = AiComplex(name="test-ai")
        bot_obj = BotService(name="my-bot")
        bot = ai.add_bot("bot-1", bot_obj)
        assert bot.name == "my-bot"
        assert bot.id == "bot-1"

    def test_remove_bot(self):
        ai = AiComplex(name="test-ai")
        ai.add_bot("bot-1")
        removed = ai.remove_bot("bot-1")
        assert removed is not None
        assert "bot-1" not in ai.bots

    def test_list_agents(self):
        ai = AiComplex(name="test-ai")
        ai.add_agent("a1")
        ai.add_agent("a2")
        assert set(ai.list_agents()) == {"a1", "a2"}

    def test_list_bots(self):
        ai = AiComplex(name="test-ai")
        ai.add_bot("b1")
        ai.add_bot("b2")
        assert set(ai.list_bots()) == {"b1", "b2"}


class TestDisplayFunctions:
    """Tests for tier_hierarchy() and sentinel_channels() display functions."""

    def test_tier_hierarchy(self):
        result = tier_hierarchy()
        assert "Tier 0" in result
        assert "Tier 3" in result
        assert "AI" in result or "ML/LLM" in result
        assert "Agent" in result
        assert "Bot" in result

    def test_sentinel_channels(self):
        result = sentinel_channels()
        assert "platform" in result
        assert "agents" in result
        assert "security" in result
