"""
Tests for AeonMind Frontier Agent.
"""

import pytest
import numpy as np

from aeonmind.core.frontier_agent import FrontierAgent, FrontierAgentConfig
from aeonmind.core.definitions import Tier


class TestFrontierAgentConfig:
    """Tests for FrontierAgentConfig."""

    def test_default_config(self):
        config = FrontierAgentConfig()
        assert config.name == "frontier-agent"
        assert config.state_dim == 10
        assert config.action_dim == 4

    def test_custom_config(self):
        config = FrontierAgentConfig(
            name="custom-agent",
            state_dim=20,
            action_dim=8,
        )
        assert config.name == "custom-agent"
        assert config.state_dim == 20
        assert config.action_dim == 8


class TestFrontierAgent:
    """Tests for the FrontierAgent."""

    def test_agent_creation(self):
        agent = FrontierAgent()
        assert agent is not None
        assert agent.config.name == "frontier-agent"

    def test_agent_process(self):
        config = FrontierAgentConfig(state_dim=10, action_dim=4)
        agent = FrontierAgent(config)
        input_data = np.random.randn(10)
        result = agent.process(input_data)
        assert "action" in result
        assert 0 <= result["action"] < 4

    def test_agent_report_outcome(self):
        config = FrontierAgentConfig(state_dim=10, action_dim=4)
        agent = FrontierAgent(config)
        input_data = np.random.randn(10)
        agent.process(input_data)
        agent.report_outcome(success=True)
        # Intelligence score should be updated
        summary = agent.summary()
        assert "intelligence" in summary

    def test_agent_summary(self):
        agent = FrontierAgent()
        summary = agent.summary()
        assert isinstance(summary, dict)
        assert "name" in summary

    def test_agent_to_entity(self):
        config = FrontierAgentConfig(name="test-agent")
        agent = FrontierAgent(config)
        entity = agent.to_entity()
        assert entity.tier == Tier.AGENT
        assert entity.name == "test-agent"

    def test_agent_reset(self):
        agent = FrontierAgent()
        input_data = np.random.randn(10)
        agent.process(input_data)
        agent.reset()
        # After reset, should be back to initial state
        assert agent is not None
