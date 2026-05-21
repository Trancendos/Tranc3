# src/intelligence/causal_reasoner.py
"""
Lightweight Causal Inference Engine for Tranc3.

Provides a rule-based causal reasoning system that enables nanoservices
to understand and predict cause-and-effect relationships.  Unlike
causal_bus.py (which provides vector-clock-ordered *message delivery*
for distributed consistency), this module provides *causal inference*:
identifying what caused what, predicting effects of actions, and
computing counterfactuals.

Key concepts
------------
- **CausalRule**: A directed cause-effect relationship with a
  confidence score and optional conditions.
- **CausalGraph**: A DAG of causal relationships supporting forward
  (prediction) and backward (diagnosis) inference.
- **CausalReasoner**: The inference engine that traverses the graph
  to answer causal queries.

Zero-cost guarantees
--------------------
- No external APIs or paid services.
- No heavy ML frameworks; uses graph traversal and probability.
- Deterministic inference for reproducible debugging.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Data structures ────────────────────────────────────────────────

class CausalStrength(str, Enum):
    """Classification of causal link strength."""
    NECESSARY = "necessary"       # Effect cannot occur without cause
    SUFFICIENT = "sufficient"     # Cause always produces effect
    CONTRIBUTING = "contributing" # Cause contributes but is not alone sufficient
    INHIBITING = "inhibiting"     # Cause prevents or reduces effect


@dataclass
class CausalRule:
    """A directed cause-effect relationship.

    Attributes
    ----------
    rule_id : str
        Unique identifier.
    cause : str
        The cause event/state name.
    effect : str
        The effect event/state name.
    strength : CausalStrength
        Classification of the causal link.
    confidence : float
        Confidence in this causal relationship (0-1).
    conditions : Dict[str, Any]
        Additional conditions that must hold for causation.
    priority : int
        Priority for conflict resolution (higher = checked first).
    source : str
        Nanoservice that registered this rule.
    metadata : Dict[str, Any]
        Additional metadata.
    """
    rule_id: str = ""
    cause: str = ""
    effect: str = ""
    strength: CausalStrength = CausalStrength.CONTRIBUTING
    confidence: float = 0.5
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rule_id:
            self.rule_id = uuid.uuid4().hex[:12]
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class InferenceResult:
    """Result of a causal inference query."""
    query_type: str  # "predict", "diagnose", "counterfactual", "intervene"
    causes: List[Tuple[str, float]]  # [(event, probability), ...]
    effects: List[Tuple[str, float]]  # [(event, probability), ...]
    reasoning_chain: List[str]  # Human-readable chain of reasoning
    confidence: float


# ── Causal Graph ───────────────────────────────────────────────────

class CausalGraph:
    """Directed Acyclic Graph of causal relationships.

    Supports:
    - Forward traversal (cause -> effect prediction)
    - Backward traversal (effect -> cause diagnosis)
    - Cycle detection (causal loops are rejected)
    - Topological ordering for layer-by-layer inference
    """

    def __init__(self) -> None:
        self._rules: Dict[str, CausalRule] = {}
        self._adj_forward: Dict[str, List[str]] = defaultdict(list)   # cause -> [effect rule_ids]
        self._adj_backward: Dict[str, List[str]] = defaultdict(list)  # effect -> [cause rule_ids]
        self._nodes: Set[str] = set()

    def add_rule(self, rule: CausalRule) -> str:
        """Add a causal rule to the graph.

        Rejects rules that would create a cycle.

        Returns
        -------
        str
            The rule ID.

        Raises
        ------
        ValueError
            If adding this rule would create a causal cycle.
        """
        # Check for cycles
        if self._would_create_cycle(rule.cause, rule.effect):
            raise ValueError(
                f"Adding rule '{rule.cause}' -> '{rule.effect}' would create a causal cycle"
            )
        self._rules[rule.rule_id] = rule
        self._adj_forward[rule.cause].append(rule.rule_id)
        self._adj_backward[rule.effect].append(rule.rule_id)
        self._nodes.add(rule.cause)
        self._nodes.add(rule.effect)
        return rule.rule_id

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a causal rule by ID."""
        rule = self._rules.pop(rule_id, None)
        if rule is None:
            return False
        self._adj_forward[rule.cause] = [
            rid for rid in self._adj_forward[rule.cause] if rid != rule_id
        ]
        self._adj_backward[rule.effect] = [
            rid for rid in self._adj_backward[rule.effect] if rid != rule_id
        ]
        # Clean up isolated nodes
        for node in (rule.cause, rule.effect):
            if not self._adj_forward[node] and not self._adj_backward[node]:
                self._nodes.discard(node)
        return True

    def get_rules_from_cause(self, cause: str) -> List[CausalRule]:
        """Return all rules where the given event is a cause."""
        rule_ids = self._adj_forward.get(cause, [])
        return [self._rules[rid] for rid in rule_ids if rid in self._rules]

    def get_rules_to_effect(self, effect: str) -> List[CausalRule]:
        """Return all rules where the given event is an effect."""
        rule_ids = self._adj_backward.get(effect, [])
        return [self._rules[rid] for rid in rule_ids if rid in self._rules]

    def get_rule(self, rule_id: str) -> Optional[CausalRule]:
        """Return a specific rule."""
        return self._rules.get(rule_id)

    def _would_create_cycle(self, cause: str, effect: str) -> bool:
        """Check if adding cause->effect would create a cycle.

        A cycle exists if we can already reach `cause` from `effect`
        by following existing forward edges.
        """
        if cause == effect:
            return True
        # BFS from effect to see if we can reach cause
        visited: Set[str] = set()
        queue = deque([effect])
        while queue:
            current = queue.popleft()
            if current == cause:
                return True
            if current in visited:
                continue
            visited.add(current)
            for rid in self._adj_forward.get(current, []):
                rule = self._rules.get(rid)
                if rule:
                    queue.append(rule.effect)
        return False

    def topological_order(self) -> List[str]:
        """Return nodes in topological order (causes before effects)."""
        in_degree: Dict[str, int] = defaultdict(int)
        for node in self._nodes:
            if node not in in_degree:
                in_degree[node] = 0
        for rule in self._rules.values():
            in_degree[rule.effect] += 1

        queue = deque([n for n, d in in_degree.items() if d == 0])
        order: List[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for rid in self._adj_forward.get(node, []):
                rule = self._rules.get(rid)
                if rule:
                    in_degree[rule.effect] -= 1
                    if in_degree[rule.effect] == 0:
                        queue.append(rule.effect)
        return order

    @property
    def nodes(self) -> Set[str]:
        """All nodes in the causal graph."""
        return set(self._nodes)

    @property
    def rules(self) -> Dict[str, CausalRule]:
        """All causal rules."""
        return dict(self._rules)

    def stats(self) -> Dict[str, Any]:
        """Return graph statistics."""
        return {
            "total_nodes": len(self._nodes),
            "total_rules": len(self._rules),
            "root_causes": [n for n in self._nodes if not self._adj_backward.get(n)],
            "leaf_effects": [n for n in self._nodes if not self._adj_forward.get(n)],
        }


# ── Causal Reasoner ────────────────────────────────────────────────

class CausalReasoner:
    """Lightweight causal inference engine.

    Supports four types of causal queries:

    1. **Predict**: Given observed causes, predict likely effects.
    2. **Diagnose**: Given observed effects, infer likely causes.
    3. **Counterfactual**: Given observed effects and a hypothetical
       intervention, estimate what would have happened.
    4. **Intervene**: Compute the expected effects of an action (do-calculus
       inspired, simplified).

    Parameters
    ----------
    max_depth : int
        Maximum inference chain depth.
    min_confidence : float
        Minimum confidence threshold for including a result.
    decay_factor : float
        Confidence decay per inference step.
    """

    def __init__(
        self,
        max_depth: int = 10,
        min_confidence: float = 0.1,
        decay_factor: float = 0.85,
    ) -> None:
        self._graph = CausalGraph()
        self._max_depth = max_depth
        self._min_confidence = min_confidence
        self._decay_factor = decay_factor
        self._evidence: Dict[str, float] = {}  # event -> probability (0-1)
        self._interventions: Set[str] = set()  # events set by do()
        self._lock = asyncio.Lock()

    # ── Rule management ────────────────────────────────────────────

    async def add_rule(self, rule: CausalRule) -> str:
        """Add a causal rule."""
        async with self._lock:
            return self._graph.add_rule(rule)

    async def remove_rule(self, rule_id: str) -> bool:
        """Remove a causal rule."""
        async with self._lock:
            return self._graph.remove_rule(rule_id)

    # ── Evidence management ────────────────────────────────────────

    async def observe(self, event: str, probability: float = 1.0) -> None:
        """Record an observation (evidence).

        Parameters
        ----------
        event : str
            The observed event.
        probability : float
            Probability that this event occurred (1.0 = certain).
        """
        async with self._lock:
            self._evidence[event] = max(0.0, min(1.0, probability))

    async def do(self, event: str) -> None:
        """Perform a do-intervention (Pearl's do-calculus, simplified).

        Setting an event via do() means it was externally forced,
        severing its incoming causal edges.
        """
        async with self._lock:
            self._interventions.add(event)
            self._evidence[event] = 1.0

    async def reset_evidence(self) -> None:
        """Clear all observations and interventions."""
        async with self._lock:
            self._evidence.clear()
            self._interventions.clear()

    # ── Inference queries ──────────────────────────────────────────

    async def predict(
        self,
        causes: List[str],
        max_results: int = 10,
    ) -> InferenceResult:
        """Predict effects given observed causes.

        Forward-traverses the causal graph from each cause, accumulating
        effect probabilities with confidence decay at each step.
        """
        async with self._lock:
            effects: Dict[str, float] = {}
            chain: List[str] = []
            # Track (event, depth) pairs already enqueued to avoid redundant
            # re-traversal from the *same* path, but allow re-entry from
            # different paths that may carry higher probability.
            enqueued: Set[tuple] = set()

            queue = deque([(c, 1.0, 0) for c in causes])
            while queue:
                event, prob, depth = queue.popleft()
                if depth >= self._max_depth:
                    continue

                rules = self._graph.get_rules_from_cause(event)
                rules.sort(key=lambda r: -r.priority)

                for rule in rules:
                    # Compute effect probability
                    rule_prob = prob * rule.confidence * self._decay_factor
                    if rule.strength == CausalStrength.NECESSARY:
                        rule_prob = min(rule_prob, prob)  # Can't exceed cause prob
                    elif rule.strength == CausalStrength.SUFFICIENT:
                        rule_prob = prob * rule.confidence  # Full propagation
                    elif rule.strength == CausalStrength.INHIBITING:
                        rule_prob = -rule_prob  # Negative = inhibiting

                    # Check conditions — only scalar values are checkable
                    if rule.conditions:
                        cond_met = all(
                            self._evidence.get(k) == v or k in self._interventions
                            for k, v in rule.conditions.items()
                            if isinstance(v, (bool, int, float, str))
                        )
                        if not cond_met:
                            continue

                    if abs(rule_prob) >= self._min_confidence:
                        existing = effects.get(rule.effect, 0.0)
                        # Combine using noisy-OR for multiple causes
                        if rule_prob > 0:
                            effects[rule.effect] = 1.0 - (1.0 - existing) * (1.0 - rule_prob)
                        else:
                            effects[rule.effect] = existing + rule_prob
                        chain.append(
                            f"{event} -> {rule.effect} "
                            f"(p={abs(rule_prob):.2f}, {rule.strength.value})"
                        )
                        # Only enqueue if this (effect, depth) pair hasn't been
                        # processed yet — prevents infinite loops in the DAG while
                        # still allowing re-propagation from different source paths.
                        key = (rule.effect, depth + 1)
                        if key not in enqueued:
                            enqueued.add(key)
                            queue.append((rule.effect, abs(rule_prob), depth + 1))

            # Sort by probability and return top results
            sorted_effects = sorted(effects.items(), key=lambda x: -abs(x[1]))[:max_results]
            overall_confidence = (
                sum(abs(p) for _, p in sorted_effects) / len(sorted_effects)
                if sorted_effects else 0.0
            )

        return InferenceResult(
            query_type="predict",
            causes=[(c, self._evidence.get(c, 1.0)) for c in causes],
            effects=sorted_effects,
            reasoning_chain=chain,
            confidence=overall_confidence,
        )

    async def diagnose(
        self,
        effects: List[str],
        max_results: int = 10,
    ) -> InferenceResult:
        """Diagnose likely causes given observed effects.

        Backward-traverses the causal graph from each effect.
        Uses approximate Bayesian reasoning: P(cause|effect) is proportional to
        P(effect|cause) * P(cause).
        """
        async with self._lock:
            causes: Dict[str, float] = {}
            chain: List[str] = []
            visited: Set[str] = set()

            queue = deque([(e, 1.0, 0) for e in effects])
            while queue:
                event, prob, depth = queue.popleft()
                if depth >= self._max_depth or event in visited:
                    continue
                visited.add(event)

                # Skip if this was an intervention (externally forced)
                if event in self._interventions:
                    continue

                rules = self._graph.get_rules_to_effect(event)
                rules.sort(key=lambda r: -r.priority)

                for rule in rules:
                    # Approximate P(cause|effect)
                    cause_prob = prob * rule.confidence * self._decay_factor
                    # Weight by prior evidence
                    prior = self._evidence.get(rule.cause, 0.5)
                    cause_prob *= prior

                    if cause_prob >= self._min_confidence:
                        existing = causes.get(rule.cause, 0.0)
                        # Combine multiple explanations (noisy-OR)
                        causes[rule.cause] = 1.0 - (1.0 - existing) * (1.0 - cause_prob)
                        chain.append(
                            f"{rule.cause} -> {event} "
                            f"(p={cause_prob:.2f}, {rule.strength.value})"
                        )
                        queue.append((rule.cause, cause_prob, depth + 1))

            sorted_causes = sorted(causes.items(), key=lambda x: -x[1])[:max_results]
            overall_confidence = (
                sum(p for _, p in sorted_causes) / len(sorted_causes)
                if sorted_causes else 0.0
            )

        return InferenceResult(
            query_type="diagnose",
            causes=sorted_causes,
            effects=[(e, self._evidence.get(e, 1.0)) for e in effects],
            reasoning_chain=chain,
            confidence=overall_confidence,
        )

    async def counterfactual(
        self,
        observed_effects: List[str],
        intervention: str,
        max_results: int = 10,
    ) -> InferenceResult:
        """Compute a counterfactual: what would happen if we intervened?

        Steps:
        1. Diagnose likely causes from the observed effects.
        2. Apply the intervention (do-calculus: sever incoming edges).
        3. Predict new effects from the intervened state.

        NOTE: We must NOT hold self._lock while awaiting diagnose()/predict(),
        because those methods acquire self._lock themselves — deadlock.  Instead
        we snapshot and restore state without the outer lock.
        """
        # Step 1: Diagnose (acquires its own lock internally)
        diagnosis = await self.diagnose(observed_effects, max_results)

        # Step 2: Apply intervention and save/restore state atomically
        async with self._lock:
            old_evidence = dict(self._evidence)
            old_interventions = set(self._interventions)
            self._interventions.add(intervention)
            self._evidence[intervention] = 1.0
            # Remove evidence for effects that were caused by severed edges
            for effect in observed_effects:
                self._evidence.pop(effect, None)

        # Step 3: Predict from intervened state (acquires its own lock internally)
        prediction = await self.predict([intervention], max_results)

        # Restore state
        async with self._lock:
            self._evidence = old_evidence
            self._interventions = old_interventions

        chain = [
            f"COUNTERFACTUAL: If we do({intervention}) instead of what caused {observed_effects}",
        ] + diagnosis.reasoning_chain + prediction.reasoning_chain

        return InferenceResult(
            query_type="counterfactual",
            causes=diagnosis.causes,
            effects=prediction.effects,
            reasoning_chain=chain,
            confidence=min(diagnosis.confidence, prediction.confidence),
        )

    # ── Introspection ──────────────────────────────────────────────

    def graph_stats(self) -> Dict[str, Any]:
        """Return statistics about the causal graph."""
        return self._graph.stats()

    def list_rules(self, cause: Optional[str] = None, effect: Optional[str] = None) -> List[CausalRule]:
        """List causal rules, optionally filtered."""
        rules = list(self._graph.rules.values())
        if cause:
            rules = [r for r in rules if r.cause == cause]
        if effect:
            rules = [r for r in rules if r.effect == effect]
        return sorted(rules, key=lambda r: -r.confidence)

    def export_graph(self) -> Dict[str, Any]:
        """Export the causal graph as a serializable dictionary."""
        return {
            "rules": {
                rid: {
                    "cause": r.cause,
                    "effect": r.effect,
                    "strength": r.strength.value,
                    "confidence": r.confidence,
                    "conditions": r.conditions,
                    "source": r.source,
                }
                for rid, r in self._graph.rules.items()
            },
            "evidence": dict(self._evidence),
            "interventions": list(self._interventions),
        }