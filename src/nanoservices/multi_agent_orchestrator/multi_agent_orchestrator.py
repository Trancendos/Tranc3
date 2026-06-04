"""Multi-Agent Orchestrator — Phase 9

Coordinates multiple AI agents for collaborative task execution
using a shared message bus, task delegation, and consensus mechanisms.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    COORDINATOR = "coordinator"
    WORKER = "worker"
    OBSERVER = "observer"
    VALIDATOR = "validator"
    DELEGATOR = "delegator"
    PLANNER = "planner"
    EXECUTOR = "executor"
    CRITIC = "critic"


class AgentState(Enum):
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    OFFLINE = "offline"


class MessageType(Enum):
    TASK_ASSIGN = "task_assign"
    TASK_RESULT = "task_result"
    BROADCAST = "broadcast"
    CONSENSUS_REQUEST = "consensus_request"
    CONSENSUS_VOTE = "consensus_vote"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    COORDINATION = "coordination"


@dataclass
class AgentMessage:
    """Message exchanged between agents."""

    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    sender_id: str = ""
    recipient_id: str = ""
    message_type: MessageType = MessageType.BROADCAST
    content: Any = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: Optional[str] = None
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentCapability:
    """Describes what an agent can do."""

    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    cost_estimate: float = 0.0
    reliability: float = 1.0


@dataclass
class AgentProfile:
    """Profile of a registered agent."""

    agent_id: str
    name: str = ""
    role: AgentRole = AgentRole.WORKER
    state: AgentState = AgentState.IDLE
    capabilities: List[AgentCapability] = field(default_factory=list)
    message_queue: List[AgentMessage] = field(default_factory=list)
    task_history: List[str] = field(default_factory=list)
    reputation_score: float = 1.0
    last_heartbeat: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratedTask:
    """A task being orchestrated across agents."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    required_capabilities: List[str] = field(default_factory=list)
    assigned_agents: List[str] = field(default_factory=list)
    subtasks: List[str] = field(default_factory=list)
    status: str = "pending"
    priority: int = 0
    result: Optional[Any] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "required_capabilities": self.required_capabilities,
            "assigned_agents": self.assigned_agents,
            "subtasks": self.subtasks,
            "status": self.status,
            "priority": self.priority,
            "result": self.result,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }


@dataclass
class ConsensusProposal:
    """A proposal requiring multi-agent consensus."""

    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    proposer_id: str = ""
    content: Any = None
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0
    required_quorum: float = 0.5
    status: str = "voting"
    deadline: Optional[str] = None
    voters: Set[str] = field(default_factory=set)

    def is_approved(self) -> bool:
        total = self.votes_for + self.votes_against + self.votes_abstain
        if total == 0:
            return False
        ratio = self.votes_for / total
        return ratio >= self.required_quorum and self.votes_for > self.votes_against


class MessageBus:
    """Shared message bus for inter-agent communication."""

    def __init__(self):
        self._queues: Dict[str, List[AgentMessage]] = {}
        self._broadcast_log: List[AgentMessage] = []
        self._handlers: Dict[str, Callable[[AgentMessage], None]] = {}

    def register(self, agent_id: str, handler: Optional[Callable[[AgentMessage], None]] = None):
        if agent_id not in self._queues:
            self._queues[agent_id] = []
        if handler:
            self._handlers[agent_id] = handler

    def unregister(self, agent_id: str):
        self._queues.pop(agent_id, None)
        self._handlers.pop(agent_id, None)

    def send(self, message: AgentMessage) -> bool:
        if message.message_type == MessageType.BROADCAST:
            self._broadcast_log.append(message)
            for agent_id, queue in self._queues.items():
                if agent_id != message.sender_id:
                    queue.append(message)
                    handler = self._handlers.get(agent_id)
                    if handler:
                        try:
                            handler(message)
                        except Exception as e:
                            logger.error("Handler error for %s: %s", agent_id, e)
            return True
        elif message.recipient_id in self._queues:
            self._queues[message.recipient_id].append(message)
            handler = self._handlers.get(message.recipient_id)
            if handler:
                try:
                    handler(message)
                except Exception as e:
                    logger.error("Handler error for %s: %s", message.recipient_id, e)
            return True
        return False

    def receive(self, agent_id: str) -> List[AgentMessage]:
        messages = self._queues.get(agent_id, [])
        self._queues[agent_id] = []
        return messages

    def peek(self, agent_id: str) -> List[AgentMessage]:
        return list(self._queues.get(agent_id, []))


class CapabilityMatcher:
    """Matches tasks to agents based on capabilities."""

    def find_agents(self, required_caps: List[str], agents: Dict[str, AgentProfile]) -> List[str]:
        candidates = []
        for agent_id, profile in agents.items():
            if profile.state not in (AgentState.IDLE, AgentState.WAITING):
                continue
            agent_caps = {c.name for c in profile.capabilities}
            if all(cap in agent_caps for cap in required_caps):
                score = profile.reputation_score
                candidates.append((score, agent_id))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [aid for _, aid in candidates]


class ConsensusEngine:
    """Manages consensus voting among agents."""

    def __init__(self, message_bus: MessageBus, default_quorum: float = 0.5):
        self.message_bus = message_bus
        self.default_quorum = default_quorum
        self.proposals: Dict[str, ConsensusProposal] = {}

    def propose(
        self,
        proposer_id: str,
        content: Any,
        voters: Optional[Set[str]] = None,
        quorum: Optional[float] = None,
    ) -> ConsensusProposal:
        proposal = ConsensusProposal(
            proposer_id=proposer_id,
            content=content,
            required_quorum=quorum or self.default_quorum,
            voters=voters or set(),
        )
        self.proposals[proposal.proposal_id] = proposal
        self.message_bus.send(
            AgentMessage(
                sender_id=proposer_id,
                message_type=MessageType.CONSENSUS_REQUEST,
                content={"proposal_id": proposal.proposal_id, "content": content},
                correlation_id=proposal.proposal_id,
            ),
        )
        return proposal

    def vote(self, proposal_id: str, voter_id: str, vote: str) -> bool:
        proposal = self.proposals.get(proposal_id)
        if not proposal or proposal.status != "voting":
            return False
        if vote == "for":
            proposal.votes_for += 1
        elif vote == "against":
            proposal.votes_against += 1
        else:
            proposal.votes_abstain += 1
        proposal.voters.add(voter_id)

        self.message_bus.send(
            AgentMessage(
                sender_id=voter_id,
                message_type=MessageType.CONSENSUS_VOTE,
                content={"proposal_id": proposal_id, "vote": vote},
                correlation_id=proposal_id,
            ),
        )
        return True

    def resolve(self, proposal_id: str) -> Optional[bool]:
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            return None
        approved = proposal.is_approved()
        proposal.status = "approved" if approved else "rejected"
        return approved


class MultiAgentOrchestrator:
    """Orchestrates multiple AI agents for collaborative task execution.

    Features:
    - Agent registration with capability discovery
    - Task delegation based on capabilities and reputation
    - Shared message bus for inter-agent communication
    - Consensus-based decision making
    - Heartbeat monitoring and agent health tracking
    - Work stealing for load balancing
    """

    def __init__(self, shi_url: str = "http://localhost:7781"):
        self.shi_url = shi_url
        self.agents: Dict[str, AgentProfile] = {}
        self.tasks: Dict[str, OrchestratedTask] = {}
        self.message_bus = MessageBus()
        self.capability_matcher = CapabilityMatcher()
        self.consensus_engine = ConsensusEngine(self.message_bus)
        self._orchestrator_id = str(uuid.uuid4())[:8]
        self._created_at = datetime.now(timezone.utc).isoformat()

        self._register_self()

    def _register_self(self):
        self.message_bus.register(f"orchestrator-{self._orchestrator_id}")

    def register_agent(
        self,
        agent_id: str,
        name: str = "",
        role: AgentRole = AgentRole.WORKER,
        capabilities: Optional[List[AgentCapability]] = None,
        handler: Optional[Callable] = None,
    ) -> AgentProfile:
        profile = AgentProfile(
            agent_id=agent_id,
            name=name or agent_id,
            role=role,
            capabilities=capabilities or [],
        )
        self.agents[agent_id] = profile
        self.message_bus.register(agent_id, handler)
        logger.info(
            "Agent registered: %s (%s) with %d capabilities",
            agent_id,
            role.value,
            len(profile.capabilities),
        )
        return profile

    def unregister_agent(self, agent_id: str) -> bool:
        if agent_id in self.agents:
            self.agents[agent_id].state = AgentState.OFFLINE
            self.message_bus.unregister(agent_id)
            return True
        return False

    def delegate_task(self, task: OrchestratedTask) -> OrchestratedTask:
        candidates = self.capability_matcher.find_agents(task.required_capabilities, self.agents)
        if not candidates:
            task.status = "no_agents_available"
            logger.warning(
                "No agents available for task %s requiring %s",
                task.task_id,
                task.required_capabilities,
            )
            return task

        for agent_id in candidates[:3]:
            task.assigned_agents.append(agent_id)
            self.agents[agent_id].state = AgentState.EXECUTING
            self.message_bus.send(
                AgentMessage(
                    sender_id=f"orchestrator-{self._orchestrator_id}",
                    recipient_id=agent_id,
                    message_type=MessageType.TASK_ASSIGN,
                    content=task.to_dict(),
                    correlation_id=task.task_id,
                ),
            )

        task.status = "delegated"
        self.tasks[task.task_id] = task
        return task

    def submit_result(self, agent_id: str, task_id: str, result: Any) -> bool:
        task = self.tasks.get(task_id)
        if not task:
            return False

        self.message_bus.send(
            AgentMessage(
                sender_id=agent_id,
                recipient_id=f"orchestrator-{self._orchestrator_id}",
                message_type=MessageType.TASK_RESULT,
                content={"task_id": task_id, "result": result},
                correlation_id=task_id,
            ),
        )

        task.result = result
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc).isoformat()

        if agent_id in self.agents:
            self.agents[agent_id].state = AgentState.IDLE
            self.agents[agent_id].task_history.append(task_id)
            self.agents[agent_id].reputation_score = min(
                2.0, self.agents[agent_id].reputation_score + 0.01,
            )

        return True

    def request_consensus(
        self, proposer_id: str, content: Any, voters: Optional[Set[str]] = None,
    ) -> ConsensusProposal:
        return self.consensus_engine.propose(proposer_id, content, voters)

    def cast_vote(self, proposal_id: str, voter_id: str, vote: str) -> bool:
        return self.consensus_engine.vote(proposal_id, voter_id, vote)

    def heartbeat(self, agent_id: str) -> bool:
        if agent_id in self.agents:
            self.agents[agent_id].last_heartbeat = datetime.now(timezone.utc).isoformat()
            self.message_bus.send(
                AgentMessage(
                    sender_id=agent_id,
                    message_type=MessageType.HEARTBEAT,
                    content={"status": self.agents[agent_id].state.value},
                ),
            )
            return True
        return False

    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        agent = self.agents.get(agent_id)
        if not agent:
            return None
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "role": agent.role.value,
            "state": agent.state.value,
            "capabilities": [c.name for c in agent.capabilities],
            "reputation_score": agent.reputation_score,
            "task_count": len(agent.task_history),
            "last_heartbeat": agent.last_heartbeat,
            "pending_messages": len(self.message_bus.peek(agent_id)),
        }

    def get_orchestrator_status(self) -> Dict[str, Any]:
        active_agents = sum(1 for a in self.agents.values() if a.state != AgentState.OFFLINE)
        return {
            "orchestrator_id": self._orchestrator_id,
            "created_at": self._created_at,
            "total_agents": len(self.agents),
            "active_agents": active_agents,
            "total_tasks": len(self.tasks),
            "completed_tasks": sum(1 for t in self.tasks.values() if t.status == "completed"),
            "pending_consensus": sum(
                1 for p in self.consensus_engine.proposals.values() if p.status == "voting"
            ),
        }
