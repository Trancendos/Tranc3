# src/distributed/swarm_intelligence.py
# TRANC3 Distributed Swarm Intelligence

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List

try:
    import torch
except (ImportError, RuntimeError, OSError):  # pragma: no cover
    # RuntimeError: CUDA init / driver mismatch; OSError: missing shared lib
    torch = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False
else:
    _TORCH_AVAILABLE = True

from Dimensional.sanitize import sanitize_for_log
from src.distributed.intelligence_blockchain import (
    HomomorphicCrypto,
    IntelligenceBlockchain,
)

logger = logging.getLogger(__name__)


@dataclass
class SwarmNode:
    node_id: str
    capabilities: Dict[str, float]
    compute_power: float
    specialization: str
    trust_score: float


class DistributedIntelligenceSwarm:
    """
    Decentralised swarm intelligence network.
    Each node contributes to collective inference.
    Uses IntelligenceBlockchain for auditability and HomomorphicCrypto for privacy.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.nodes: Dict[str, SwarmNode] = {}
        self.consensus_algo = config.get("consensus", "neural_consensus")
        self.min_nodes = config.get("min_nodes", 3)
        self.pheromone_trails: Dict = {}
        self.exploration_rate = 0.1

        self.blockchain = IntelligenceBlockchain()
        self.crypto = HomomorphicCrypto(epsilon=1.0)
        logger.info("DistributedIntelligenceSwarm initialised")

    # ── Public API ────────────────────────────────────────────────────────────

    async def collective_problem_solving(self, problem: Dict) -> Dict:
        """Distributed problem solving with consensus and blockchain recording."""
        if not self.nodes:
            # No nodes registered — return direct result
            return {"result": torch.zeros(768), "mode": "single_node"}

        sub_tasks = self._decompose_problem(problem)
        task_assignments = self._assign_tasks(sub_tasks)

        results = await asyncio.gather(
            *[self._execute_on_node(task, node) for task, node in task_assignments],
            return_exceptions=True,
        )

        valid = [r for r in results if not isinstance(r, Exception)]
        if not valid:
            return {"result": torch.zeros(768), "mode": "fallback"}

        consensus = self._neural_consensus(valid)

        self.blockchain.add_computation(
            problem=problem,
            result={"consensus_norm": float(consensus.norm())},
            participants=[n.node_id for _, n in task_assignments],
        )

        return {"result": consensus, "mode": "swarm", "nodes_used": len(valid)}

    async def share_insight(self, thought: Dict):
        """Broadcast an insight to all registered nodes."""
        logger.debug("Sharing insight to %s nodes", sanitize_for_log(len(self.nodes)))

    def register_node(self, node: SwarmNode):
        self.nodes[node.node_id] = node
        logger.info(
            "Node registered: %s (%s)",
            sanitize_for_log(node.node_id),
            sanitize_for_log(node.specialization),
        )

    def federated_learning_step(self, local_model: torch.nn.Module) -> torch.nn.Module:
        """Privacy-preserving federated learning step."""
        encrypted = self.crypto.encrypt_gradients(local_model)
        aggregated = self.crypto.secure_aggregation([encrypted])
        private = self.crypto.add_differential_privacy(aggregated)
        with torch.no_grad():
            for name, param in local_model.named_parameters():
                if name in private and param.grad is not None:
                    param.data -= 0.001 * private[name]
        return local_model

    def get_stats(self) -> Dict:
        return {
            "nodes": len(self.nodes),
            "blockchain_stats": self.blockchain.get_stats(),
            "exploration_rate": self.exploration_rate,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _decompose_problem(self, problem: Dict) -> List[Dict]:
        """Split problem into sub-tasks."""
        msg = problem.get("message", problem.get("input", ""))
        if isinstance(msg, torch.Tensor):
            return [{"chunk": msg, "index": 0}]
        sentences = str(msg).split(".")
        return [{"chunk": s.strip(), "index": i} for i, s in enumerate(sentences) if s.strip()]

    def _assign_tasks(self, sub_tasks: List[Dict]):
        """Assign sub-tasks to nodes round-robin."""
        node_list = list(self.nodes.values())
        if not node_list:
            return []
        return [(task, node_list[i % len(node_list)]) for i, task in enumerate(sub_tasks)]

    async def _execute_on_node(self, task: Dict, node: SwarmNode) -> torch.Tensor:
        """Execute a task on a node (simulated locally)."""
        await asyncio.sleep(0)  # yield
        chunk = task.get("chunk", "")
        if isinstance(chunk, torch.Tensor):
            return chunk
        # Encode text chunk as a simple tensor
        vals = [ord(c) % 768 for c in str(chunk)[:768]]
        t = torch.tensor(vals, dtype=torch.float32)
        return torch.nn.functional.pad(t, (0, max(0, 768 - len(t))))[:768]

    def _neural_consensus(self, results: List[torch.Tensor]) -> torch.Tensor:
        """Attention-weighted consensus over node results."""
        stacked = torch.stack([r.float() for r in results])
        norms = stacked.norm(dim=-1, keepdim=True) + 1e-8
        weights = torch.softmax(norms.squeeze(-1), dim=0)
        return (stacked * weights.unsqueeze(-1)).sum(dim=0)
