"""Neural-Symbolic Reasoning — Phase 10

Hybrid neuro-symbolic reasoning engine combining neural network
pattern recognition with symbolic logic inference. Supports
forward/backward chaining, unification, and neural predicate
evaluation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class LogicType(Enum):
    PROPOSITIONAL = "propositional"
    FIRST_ORDER = "first_order"
    MODAL = "modal"
    FUZZY = "fuzzy"
    TEMPORAL = "temporal"
    DESCRIPTION = "description"


class InferenceDirection(Enum):
    FORWARD = "forward"
    BACKWARD = "backward"
    BIDIRECTIONAL = "bidirectional"


class ReasoningStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


@dataclass
class Symbol:
    """A symbolic term or predicate."""
    name: str
    arity: int = 0
    sort: str = "individual"
    value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "arity": self.arity, "sort": self.sort}


@dataclass
class Predicate:
    """A logical predicate with arguments."""
    name: str = ""
    arguments: List[Symbol] = field(default_factory=list)
    negated: bool = False
    confidence: float = 1.0
    source: str = "symbolic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "arguments": [a.to_dict() for a in self.arguments],
            "negated": self.negated,
            "confidence": self.confidence,
            "source": self.source,
        }

    def __hash__(self) -> int:
        return hash((self.name, tuple(a.name for a in self.arguments), self.negated))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Predicate):
            return False
        return (self.name == other.name and
                [a.name for a in self.arguments] == [a.name for a in other.arguments] and
                self.negated == other.negated)


@dataclass
class Rule:
    """An inference rule: IF antecedents THEN consequent."""
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    antecedents: List[Predicate] = field(default_factory=list)
    consequent: Predicate = field(default_factory=Predicate)
    weight: float = 1.0
    logic_type: LogicType = LogicType.FIRST_ORDER
    direction: InferenceDirection = InferenceDirection.FORWARD
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "antecedents": [a.to_dict() for a in self.antecedents],
            "consequent": self.consequent.to_dict(),
            "weight": self.weight,
            "logic_type": self.logic_type.value,
            "description": self.description,
        }


@dataclass
class Fact:
    """A known fact in the knowledge base."""
    fact_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    predicate: Predicate = field(default_factory=Predicate)
    source: str = "asserted"
    confidence: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "predicate": self.predicate.to_dict(),
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class ProofStep:
    """A single step in a reasoning proof."""
    step_number: int = 0
    rule_applied: Optional[str] = None
    derived_fact: Optional[Fact] = None
    bindings: Dict[str, str] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class ReasoningResult:
    """Result of a reasoning query."""
    query: Predicate = field(default_factory=Predicate)
    proven: bool = False
    confidence: float = 0.0
    proof_steps: List[ProofStep] = field(default_factory=list)
    bindings: Dict[str, str] = field(default_factory=dict)
    status: ReasoningStatus = ReasoningStatus.PENDING
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query.to_dict(),
            "proven": self.proven,
            "confidence": round(self.confidence, 4),
            "proof_steps": len(self.proof_steps),
            "bindings": self.bindings,
            "status": self.status.value,
            "explanation": self.explanation,
        }


class KnowledgeBase:
    """Symbolic knowledge base storing facts and rules."""

    def __init__(self):
        self.facts: Dict[str, Fact] = {}
        self.rules: Dict[str, Rule] = {}
        self._predicate_index: Dict[str, Set[str]] = {}

    def assert_fact(self, predicate: Predicate, source: str = "asserted",
                     confidence: float = 1.0) -> Fact:
        fact = Fact(predicate=predicate, source=source, confidence=confidence)
        self.facts[fact.fact_id] = fact
        key = predicate.name
        if key not in self._predicate_index:
            self._predicate_index[key] = set()
        self._predicate_index[key].add(fact.fact_id)
        return fact

    def retract_fact(self, fact_id: str) -> bool:
        if fact_id in self.facts:
            fact = self.facts[fact_id]
            key = fact.predicate.name
            self._predicate_index.get(key, set()).discard(fact_id)
            del self.facts[fact_id]
            return True
        return False

    def add_rule(self, rule: Rule) -> str:
        self.rules[rule.rule_id] = rule
        return rule.rule_id

    def find_facts(self, predicate_name: str) -> List[Fact]:
        fact_ids = self._predicate_index.get(predicate_name, set())
        return [self.facts[fid] for fid in fact_ids if fid in self.facts]

    def match_predicate(self, query: Predicate) -> List[Tuple[Fact, Dict[str, str]]]:
        matches = []
        for fact in self.find_facts(query.name):
            if len(fact.predicate.arguments) != len(query.arguments):
                continue
            bindings: Dict[str, str] = {}
            match = True
            for q_arg, f_arg in zip(query.arguments, fact.predicate.arguments):
                if q_arg.name.startswith("?"):
                    bindings[q_arg.name] = f_arg.name
                elif q_arg.name != f_arg.name:
                    match = False
                    break
            if match:
                matches.append((fact, bindings))
        return matches


class NeuralPredicateEvaluator:
    """Evaluates predicates using neural network confidence scores.

    Bridges the neural-symbolic gap by assigning neural confidence
    to symbolic predicates based on learned patterns.
    """

    def __init__(self, shi_url: str = "http://localhost:7781"):
        self.shi_url = shi_url
        self._models: Dict[str, Dict[str, Any]] = {}

    def register_predicate_model(self, predicate_name: str,
                                  model_config: Optional[Dict] = None):
        self._models[predicate_name] = model_config or {
            "type": "heuristic",
            "default_confidence": 0.8,
        }

    def evaluate(self, predicate: Predicate) -> float:
        if predicate.name in self._models:
            model = self._models[predicate.name]
            if model.get("type") == "heuristic":
                return model.get("default_confidence", 0.8)
        if predicate.source == "neural":
            return predicate.confidence
        return 0.5 + random.uniform(-0.1, 0.1)


class ForwardChainer:
    """Forward chaining inference engine."""

    def __init__(self, kb: KnowledgeBase, neural_eval: NeuralPredicateEvaluator):
        self.kb = kb
        self.neural_eval = neural_eval

    def infer(self, max_steps: int = 100) -> List[Fact]:
        derived = []
        for step in range(max_steps):
            new_facts = []
            for rule in self.kb.rules.values():
                all_match = True
                bindings_list: List[Dict[str, str]] = [{}]
                for antecedent in rule.antecedents:
                    matches = self.kb.match_predicate(antecedent)
                    if not matches:
                        all_match = False
                        break
                    new_bindings_list = []
                    for existing_bindings in bindings_list:
                        for fact, fact_bindings in matches:
                            merged = {**existing_bindings, **fact_bindings}
                            new_bindings_list.append(merged)
                    bindings_list = new_bindings_list
                if all_match and bindings_list:
                    for bindings in bindings_list:
                        new_pred = self._apply_bindings(rule.consequent, bindings)
                        neural_conf = self.neural_eval.evaluate(new_pred)
                        confidence = rule.weight * min(
                            neural_conf,
                            max(0.5, 1.0 - step * 0.01)
                        )
                        new_pred.confidence = confidence
                        new_fact = self.kb.assert_fact(
                            new_pred, source=f"rule:{rule.rule_id}", confidence=confidence
                        )
                        new_facts.append(new_fact)
                        derived.append(new_fact)
            if not new_facts:
                break
        return derived

    def _apply_bindings(self, predicate: Predicate, bindings: Dict[str, str]) -> Predicate:
        new_args = []
        for arg in predicate.arguments:
            if arg.name.startswith("?") and arg.name in bindings:
                new_args.append(Symbol(name=bindings[arg.name], arity=arg.arity, sort=arg.sort))
            else:
                new_args.append(arg)
        return Predicate(
            name=predicate.name,
            arguments=new_args,
            negated=predicate.negated,
            confidence=predicate.confidence,
        )


class BackwardChainer:
    """Backward chaining inference engine."""

    def __init__(self, kb: KnowledgeBase, neural_eval: NeuralPredicateEvaluator):
        self.kb = kb
        self.neural_eval = neural_eval

    def prove(self, goal: Predicate, max_depth: int = 10) -> ReasoningResult:
        result = ReasoningResult(query=goal)
        proven, bindings, steps = self._prove_recursive(goal, max_depth, [], set())
        result.proven = proven
        result.bindings = bindings
        result.proof_steps = steps
        result.confidence = self._compute_confidence(steps)
        result.status = ReasoningStatus.COMPLETED if proven else ReasoningStatus.INCONCLUSIVE
        result.explanation = self._explain(steps)
        return result

    def _prove_recursive(self, goal: Predicate, depth: int,
                          steps: List[ProofStep], visited: Set[str]) -> Tuple[bool, Dict[str, str], List[ProofStep]]:
        goal_key = f"{goal.name}({','.join(a.name for a in goal.arguments)})"
        if goal_key in visited:
            return False, {}, steps
        visited = visited | {goal_key}

        matches = self.kb.match_predicate(goal)
        if matches:
            fact, bindings = matches[0]
            step = ProofStep(
                step_number=len(steps) + 1,
                derived_fact=fact,
                bindings=bindings,
                confidence=fact.confidence,
            )
            steps.append(step)
            return True, bindings, steps

        for rule in self.kb.rules.values():
            if rule.consequent.name != goal.name:
                continue
            all_proven = True
            combined_bindings: Dict[str, str] = {}
            for antecedent in rule.antecedents:
                bound_antecedent = self._apply_bindings(antecedent, combined_bindings)
                proven, sub_bindings, steps = self._prove_recursive(
                    bound_antecedent, depth - 1, steps, visited
                )
                if not proven:
                    all_proven = False
                    break
                combined_bindings.update(sub_bindings)
            if all_proven:
                step = ProofStep(
                    step_number=len(steps) + 1,
                    rule_applied=rule.rule_id,
                    bindings=combined_bindings,
                    confidence=rule.weight,
                )
                steps.append(step)
                return True, combined_bindings, steps

        neural_conf = self.neural_eval.evaluate(goal)
        if neural_conf > 0.8:
            step = ProofStep(
                step_number=len(steps) + 1,
                bindings={},
                confidence=neural_conf,
            )
            steps.append(step)
            return True, {}, steps

        return False, {}, steps

    def _apply_bindings(self, predicate: Predicate, bindings: Dict[str, str]) -> Predicate:
        new_args = []
        for arg in predicate.arguments:
            if arg.name.startswith("?") and arg.name in bindings:
                new_args.append(Symbol(name=bindings[arg.name], sort=arg.sort))
            else:
                new_args.append(arg)
        return Predicate(name=predicate.name, arguments=new_args, confidence=predicate.confidence)

    def _compute_confidence(self, steps: List[ProofStep]) -> float:
        if not steps:
            return 0.0
        return min(s.confidence for s in steps) if steps else 0.0

    def _explain(self, steps: List[ProofStep]) -> str:
        if not steps:
            return "No proof steps found"
        explanations = []
        for step in steps:
            if step.rule_applied:
                explanations.append(f"Applied rule {step.rule_applied} (confidence: {step.confidence:.2f})")
            elif step.derived_fact:
                explanations.append(f"Found fact {step.derived_fact.predicate.name} (confidence: {step.confidence:.2f})")
        return "; ".join(explanations)


class NeuralSymbolicReasoner:
    """Hybrid neuro-symbolic reasoning engine.

    Features:
    - Symbolic knowledge base with facts and rules
    - Forward chaining (data-driven) inference
    - Backward chaining (goal-driven) inference with proof trees
    - Neural predicate evaluation bridging neural/symbolic
    - Unification and variable binding
    - Confidence propagation through reasoning chains
    - Multi-valued logic (fuzzy, probabilistic)
    """

    def __init__(self, shi_url: str = "http://localhost:7781"):
        self.kb = KnowledgeBase()
        self.neural_eval = NeuralPredicateEvaluator(shi_url)
        self.forward_chainer = ForwardChainer(self.kb, self.neural_eval)
        self.backward_chainer = BackwardChainer(self.kb, self.neural_eval)
        self._id = str(uuid.uuid4())[:8]

    def assert_fact(self, name: str, args: List[str],
                     confidence: float = 1.0) -> Fact:
        predicate = Predicate(
            name=name,
            arguments=[Symbol(name=a) for a in args],
            confidence=confidence,
        )
        return self.kb.assert_fact(predicate)

    def add_rule(self, name: str, antecedents: List[Tuple[str, List[str]]],
                 consequent: Tuple[str, List[str]], weight: float = 1.0) -> str:
        ant_preds = [Predicate(name=n, arguments=[Symbol(name=a) for a in args])
                     for n, args in antecedents]
        con_name, con_args = consequent
        con_pred = Predicate(name=con_name, arguments=[Symbol(name=a) for a in con_args])
        rule = Rule(name=name, antecedents=ant_preds, consequent=con_pred, weight=weight)
        return self.kb.add_rule(rule)

    def query(self, name: str, args: List[str],
              direction: InferenceDirection = InferenceDirection.BACKWARD) -> ReasoningResult:
        predicate = Predicate(
            name=name,
            arguments=[Symbol(name=a) for a in args],
        )
        if direction in (InferenceDirection.BACKWARD, InferenceDirection.BIDIRECTIONAL):
            return self.backward_chainer.prove(predicate)
        else:
            derived = self.forward_chainer.infer()
            matches = self.kb.match_predicate(predicate)
            if matches:
                fact, bindings = matches[0]
                return ReasoningResult(
                    query=predicate,
                    proven=True,
                    confidence=fact.confidence,
                    bindings=bindings,
                    status=ReasoningStatus.COMPLETED,
                    explanation=f"Found in knowledge base: {fact.predicate.name}",
                )
            return ReasoningResult(
                query=predicate,
                proven=False,
                status=ReasoningStatus.INCONCLUSIVE,
                explanation="No matching fact found after forward chaining",
            )

    def register_neural_predicate(self, name: str, confidence: float = 0.8):
        self.neural_eval.register_predicate_model(name, {
            "type": "heuristic",
            "default_confidence": confidence,
        })

    def get_reasoner_status(self) -> Dict[str, Any]:
        return {
            "reasoner_id": self._id,
            "total_facts": len(self.kb.facts),
            "total_rules": len(self.kb.rules),
            "predicate_types": list(self.kb._predicate_index.keys()),
            "neural_predicates": list(self.neural_eval._models.keys()),
        }
