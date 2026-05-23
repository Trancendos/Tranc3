import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MCTSNode:
    """A single node in the Monte Carlo Search Tree."""

    state: Any
    parent: Optional["MCTSNode"] = None
    children: Dict[str, "MCTSNode"] = field(default_factory=dict)
    visits: int = 0
    value_sum: float = 0.0
    prior: float = 1.0
    action: Optional[str] = None

    @property
    def value(self) -> float:
        """Mean action value Q(s, a)."""
        return self.value_sum / self.visits if self.visits > 0 else 0.0

    @property
    def ucb_score(self) -> float:
        """Upper Confidence Bound score for tree traversal.

        UCB formula: Q(s,a) + C * P(s,a) * sqrt(N(s)) / (1 + N(s,a))
        where C is the exploration constant, P is the prior, N(s) is parent visits,
        and N(s,a) is this node's visit count.
        """
        if self.parent is None:
            return self.value

        C = 1.414  # sqrt(2) — exploration constant
        parent_visits = self.parent.visits if self.parent.visits > 0 else 1
        exploration = C * self.prior * math.sqrt(parent_visits) / (1 + self.visits)
        return self.value + exploration

    def is_leaf(self) -> bool:
        """Return True if this node has no children."""
        return len(self.children) == 0

    def expand(self, actions: Dict[str, float]) -> None:
        """Expand this node by creating child nodes for each action.

        Args:
            actions: Mapping from action string to prior probability.
        """
        for action_str, prior in actions.items():
            if action_str not in self.children:
                child = MCTSNode(
                    state=None,  # State populated lazily during simulation
                    parent=self,
                    prior=float(prior),
                    action=action_str,
                )
                self.children[action_str] = child

    def backup(self, value: float) -> None:
        """Propagate the simulation value up through the tree.

        Args:
            value: The leaf evaluation value in [-1, 1].
        """
        node: Optional[MCTSNode] = self
        while node is not None:
            node.visits += 1
            node.value_sum += value
            # Flip sign at each level (two-player zero-sum perspective)
            value = -value
            node = node.parent


@dataclass
class MCTSConfig:
    """Configuration for the MCTS search."""

    num_simulations: int = 800
    c_puct: float = 1.414
    temperature: float = 1.0
    dirichlet_alpha: float = 0.3
    dirichlet_epsilon: float = 0.25


class NeuralNetworkAdapter:
    """Wraps any callable policy+value function for use in MCTS.

    When no function is provided, falls back to uniform priors and a random value,
    so MCTS degrades gracefully to pure UCT.
    """

    def __init__(self, policy_value_fn: Optional[callable] = None) -> None:
        self._fn = policy_value_fn

    def evaluate(self, state: Any) -> Tuple[Dict[str, float], float]:
        """Evaluate a state, returning action priors and a value estimate.

        Args:
            state: The environment state to evaluate.  May be any object;
                   the underlying policy_value_fn is responsible for parsing it.

        Returns:
            Tuple of:
              - action_priors: dict mapping action strings to prior probabilities
              - value: scalar estimate in [-1, 1]
        """
        if self._fn is not None:
            try:
                return self._fn(state)
            except Exception as exc:
                logger.warning("Neural network evaluation failed: %s", exc)

        # Default: derive actions from state if possible, else generic placeholders
        actions = self._default_actions(state)
        n = max(len(actions), 1)
        priors = dict.fromkeys(actions, 1.0 / n)
        value = float(np.random.uniform(-0.1, 0.1))
        return priors, value

    def _default_actions(self, state: Any) -> List[str]:
        """Attempt to derive a list of action names from state."""
        if isinstance(state, dict) and "valid_actions" in state:
            return list(state["valid_actions"])
        if hasattr(state, "valid_actions"):
            return list(state.valid_actions)
        # Fallback: generic abstract action space
        return [f"action_{i}" for i in range(4)]


class MCTS:
    """AlphaZero-style Monte Carlo Tree Search.

    Runs ``config.num_simulations`` simulations from the root state, each
    consisting of:
      1. Selection   — traverse the tree using UCB until a leaf is reached.
      2. Expansion   — expand the leaf using the neural network's action priors.
      3. Evaluation  — get the value estimate from the neural network.
      4. Backup      — propagate the value back through the path.

    After all simulations the policy is derived from visit counts, optionally
    temperature-scaled.
    """

    def __init__(self, config: MCTSConfig, nn_adapter: NeuralNetworkAdapter) -> None:
        self.config = config
        self.nn = nn_adapter

    async def search(self, root_state: Any, valid_actions: List[str]) -> Dict[str, float]:
        """Run MCTS and return a policy over valid actions.

        Args:
            root_state: The current environment state.
            valid_actions: The set of legal actions from this state.

        Returns:
            Probability distribution over actions (visit-count policy).
        """
        root = MCTSNode(state=root_state)

        # Initialise root with priors + Dirichlet noise for exploration
        priors, _ = self.nn.evaluate(root_state)
        # Only keep valid actions
        filtered = {a: priors.get(a, 1.0 / max(len(valid_actions), 1)) for a in valid_actions}
        # Normalise
        total = sum(filtered.values())
        if total > 0:
            filtered = {a: p / total for a, p in filtered.items()}
        filtered = self._add_dirichlet_noise(filtered)
        root.expand(filtered)

        for sim_idx in range(self.config.num_simulations):
            try:
                self._simulate(root)
            except Exception as exc:
                logger.debug("Simulation %d failed: %s", sim_idx, exc)

        return self.get_policy(root, self.config.temperature)

    def _simulate(self, root: MCTSNode) -> float:
        """Run a single simulation: select → expand/evaluate → backup.

        Args:
            root: The root node of the search tree.

        Returns:
            The value estimate at the leaf.
        """
        node = self._select(root)
        value = self._expand_and_evaluate(node)
        node.backup(value)
        return value

    def _select(self, node: MCTSNode) -> MCTSNode:
        """Traverse the tree from ``node`` downward using UCB until a leaf.

        A node is a leaf if it has no children OR if it has unvisited children
        (we stop at the first unvisited child to maintain tree structure integrity).

        Args:
            node: Starting node (typically the root).

        Returns:
            The selected leaf node.
        """
        while not node.is_leaf():
            # Pick the child with the highest UCB score
            best_score = -float("inf")
            best_child: Optional[MCTSNode] = None
            for child in node.children.values():
                score = child.ucb_score
                if score > best_score:
                    best_score = score
                    best_child = child

            if best_child is None:
                break

            # If this child has never been visited, stop here (it's our leaf)
            if best_child.visits == 0:
                return best_child

            node = best_child

        return node

    def _expand_and_evaluate(self, node: MCTSNode) -> float:
        """Expand a leaf node and evaluate it with the neural network.

        If the node already has children (expanded by a parallel simulation),
        we simply evaluate without re-expanding.

        Args:
            node: The leaf node to expand.

        Returns:
            Scalar value estimate for this state.
        """
        state = node.state if node.state is not None else {}
        priors, value = self.nn.evaluate(state)

        if node.is_leaf() and priors:
            # Normalise priors
            total = sum(priors.values())
            if total > 0:
                priors = {a: p / total for a, p in priors.items()}
            node.expand(priors)

        return float(value)

    def _add_dirichlet_noise(self, priors: Dict[str, float]) -> Dict[str, float]:
        """Mix in Dirichlet noise at the root to encourage exploration.

        Uses the standard AlphaZero recipe:
          p' = (1 - ε) * p + ε * η
        where η ~ Dir(α).

        Args:
            priors: Original prior probabilities.

        Returns:
            Noisy prior probabilities (still sum to 1 if inputs did).
        """
        if not priors:
            return priors

        actions = list(priors.keys())
        alpha = self.config.dirichlet_alpha
        epsilon = self.config.dirichlet_epsilon

        noise = np.random.dirichlet([alpha] * len(actions))
        noisy: Dict[str, float] = {}
        for action, eta in zip(actions, noise, strict=False):
            noisy[action] = (1.0 - epsilon) * priors[action] + epsilon * float(eta)
        return noisy

    def get_policy(self, root: MCTSNode, temperature: float) -> Dict[str, float]:
        """Convert visit counts to a probability distribution (the MCTS policy).

        With temperature → 0 this is greedy; with temperature = 1 it is
        proportional to visit counts; with temperature → ∞ it is uniform.

        Args:
            root: The root node after all simulations.
            temperature: Controls policy sharpness.

        Returns:
            Probability distribution over child actions.
        """
        children = root.children
        if not children:
            return {}

        actions = list(children.keys())
        counts = np.array([children[a].visits for a in actions], dtype=np.float64)

        if temperature == 0.0 or counts.sum() == 0:
            # Greedy: one-hot on the most-visited action
            policy = np.zeros_like(counts)
            policy[np.argmax(counts)] = 1.0
        else:
            # Softmax over (visit_count)^(1/T)
            powered = np.power(counts, 1.0 / temperature)
            total = powered.sum()
            policy = powered / total if total > 0 else np.ones_like(powered) / len(powered)

        return {action: float(prob) for action, prob in zip(actions, policy, strict=False)}
