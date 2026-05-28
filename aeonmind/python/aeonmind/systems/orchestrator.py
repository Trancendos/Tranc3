"""
AeonMind Logical Orchestrator — Tier 1 Platform Orchestrator.

The LogicalOrchestrator manages AI Complexes (Tier 3), Agents (Tier 4),
and Bot Services (Tier 5). It provides entity lifecycle management,
task dispatch, evolution, optimization, and sentinel broadcast
capabilities using Ray for distributed execution when available.

Custom Hierarchy:
  AI    = The overarching ML/LLM Complex (Tier 3)
  Agent = Lower-level autonomous AI (Tier 4)
  Bot   = Stateless service worker/function (Tier 5)
"""

from __future__ import annotations  # noqa: I001

import time
import uuid  # noqa: F401
from dataclasses import dataclass, field  # noqa: F401
from enum import Enum
from typing import Any, Dict, List, Optional  # noqa: UP035

import numpy as np

from ..core.definitions import Tier, SentinelChannel, AiComplex, AgentEntity, BotService  # noqa: F401
from ..core.frontier_agent import FrontierAgent, FrontierAgentConfig
from ..services.bot_services import BotServiceWorker, BotServiceConfig


class OrchestratorState(str, Enum):
    """State of the orchestrator."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class OrchestratorConfig:
    """Configuration for the Logical Orchestrator."""
    max_ai_complexes: int = 10
    max_agents_per_complex: int = 50
    max_bots_per_complex: int = 100
    evolution_interval: int = 100
    optimization_interval: int = 50
    use_ray: bool = True
    sentinel_buffer_size: int = 1000


@dataclass
class OrchestratorMetrics:
    """Runtime metrics for the orchestrator."""
    total_entities: int = 0
    total_agents: int = 0
    total_bots: int = 0
    total_tasks_dispatched: int = 0
    total_evolution_rounds: int = 0
    total_optimization_rounds: int = 0
    uptime_seconds: float = 0.0
    sentinel_messages_sent: int = 0


class LogicalOrchestrator:
    """Logical Orchestrator — Tier 1.

    Manages the lifecycle of AI Complexes, Agents, and Bots.
    Provides task dispatch, evolution, optimization, and
    sentinel broadcast capabilities.
    """

    def __init__(self, config: Optional[OrchestratorConfig] = None):  # noqa: UP045
        self.config = config or OrchestratorConfig()
        self.state = OrchestratorState.INITIALIZING
        self.metrics = OrchestratorMetrics()
        self._start_time = time.time()
        self._ai_complexes: Dict[str, AiComplex] = {}  # noqa: UP006
        self._agents: Dict[str, FrontierAgent] = {}  # noqa: UP006
        self._bots: Dict[str, BotServiceWorker] = {}  # noqa: UP006
        self._sentinel_channels: Dict[SentinelChannel, List[str]] = {  # noqa: UP006
            ch: [] for ch in SentinelChannel
        }
        self._ray_initialized = False

        self._initialize()

    def _initialize(self) -> None:
        """Initialize the orchestrator and optional Ray runtime."""
        if self.config.use_ray:
            try:
                import ray
                if not ray.is_initialized():
                    ray.init(ignore_reinit_error=True)
                self._ray_initialized = True
            except ImportError:
                self._ray_initialized = False

        self.state = OrchestratorState.RUNNING

    def create_ai_complex(self, name: str) -> AiComplex:
        """Create a new AI Complex (Tier 3)."""
        ai = AiComplex(name=name)
        self._ai_complexes[ai.id] = ai
        self._update_metrics()
        self._subscribe(ai.id, SentinelChannel.PLATFORM)
        return ai

    def create_agent(self, name: str, config: Optional[FrontierAgentConfig] = None) -> FrontierAgent:  # noqa: UP045, E501
        """Create a new Agent (Tier 4)."""
        agent_config = config or FrontierAgentConfig(name=name)
        agent = FrontierAgent(agent_config)
        self._agents[agent.id] = agent
        self._update_metrics()
        self._subscribe(agent.id, SentinelChannel.AGENTS)
        return agent

    def create_bot(self, name: str, capability: str = "generic") -> BotServiceWorker:
        """Create a new Bot Service Worker (Tier 5)."""
        from ..services.bot_services import BotCapability
        try:
            cap = BotCapability(capability)
        except ValueError:
            cap = BotCapability.GENERIC
        config = BotServiceConfig(name=name, capability=cap)
        bot = BotServiceWorker(config)
        self._bots[bot.id] = bot
        self._update_metrics()
        return bot

    def dispatch_task(self, entity_id: str, task_type: str,
                      payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:  # noqa: UP045
        """Dispatch a task to an entity."""
        payload = payload or {}
        self.metrics.total_tasks_dispatched += 1

        if entity_id in self._agents:
            agent = self._agents[entity_id]
            input_data = np.zeros(agent.config.state_dim)
            result = agent.process(input_data)
            return {"status": "completed", "result": result}
        elif entity_id in self._bots:
            bot = self._bots[entity_id]
            exec_result = bot.execute(payload)
            return {"status": "completed", "result": exec_result}
        elif entity_id in self._ai_complexes:
            return {"status": "dispatched", "message": f"Task sent to AI complex {entity_id}"}
        else:
            return {"status": "error", "message": f"Entity {entity_id} not found"}

    def dispatch_batch(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:  # noqa: UP006
        """Dispatch a batch of tasks."""
        results = []
        for task in tasks:
            result = self.dispatch_task(
                task.get("entity_id", ""),
                task.get("task_type", "generic"),
                task.get("payload", {}),
            )
            results.append(result)
        return results

    def run_evolution_round(self, agent_id: str, generations: int = 5) -> Dict[str, Any]:  # noqa: UP006
        """Run an evolution round for a specific agent."""
        if agent_id not in self._agents:
            return {"status": "error", "message": f"Agent {agent_id} not found"}

        agent = self._agents[agent_id]

        def fitness_fn(dna):
            return -float(np.sum(dna ** 2))

        stats = agent.evolution.evolve(fitness_fn, generations=generations)
        self.metrics.total_evolution_rounds += 1
        return {"status": "completed", "best_fitness": stats.best_fitness}

    def optimize_all_agents(self, max_steps: int = 50) -> Dict[str, Any]:  # noqa: UP006
        """Optimize all agents in the system."""
        results = {}
        for agent_id, agent in self._agents.items():
            def loss_fn(params):
                return float(np.sum(params ** 2))

            def grad_fn(params):
                return 2.0 * params

            summary = agent.learner.optimize(loss_fn, grad_fn)
            results[agent_id] = {
                "final_loss": summary.final_loss,
                "steps": summary.total_steps,
            }
            self.metrics.total_optimization_rounds += 1

        return results

    def _subscribe(self, entity_id: str, channel: SentinelChannel) -> None:
        """Subscribe an entity to a sentinel channel."""
        if entity_id not in self._sentinel_channels[channel]:
            self._sentinel_channels[channel].append(entity_id)

    def broadcast(self, channel: SentinelChannel, message: Any,
                  source_id: Optional[str] = None) -> int:  # noqa: UP045
        """Broadcast a message on a sentinel channel."""
        recipients = self._sentinel_channels.get(channel, [])
        self.metrics.sentinel_messages_sent += len(recipients)
        return len(recipients)

    def health_check(self) -> Dict[str, Any]:  # noqa: UP006
        """Perform a health check."""
        self.metrics.uptime_seconds = time.time() - self._start_time
        return {
            "state": self.state.value,
            "healthy": self.state in (OrchestratorState.RUNNING, OrchestratorState.PAUSED),
            "metrics": {
                "total_entities": self.metrics.total_entities,
                "total_agents": self.metrics.total_agents,
                "total_bots": self.metrics.total_bots,
                "tasks_dispatched": self.metrics.total_tasks_dispatched,
                "evolution_rounds": self.metrics.total_evolution_rounds,
                "optimization_rounds": self.metrics.total_optimization_rounds,
                "uptime_seconds": round(self.metrics.uptime_seconds, 2),
            },
            "ray_initialized": self._ray_initialized,
        }

    def get_agent_summaries(self) -> Dict[str, Dict[str, Any]]:  # noqa: UP006
        """Get summaries of all agents."""
        return {aid: agent.summary() for aid, agent in self._agents.items()}

    def _update_metrics(self) -> None:
        """Update orchestrator metrics."""
        self.metrics.total_agents = len(self._agents)
        self.metrics.total_bots = len(self._bots)
        self.metrics.total_entities = (
            len(self._ai_complexes) + len(self._agents) + len(self._bots)
        )
