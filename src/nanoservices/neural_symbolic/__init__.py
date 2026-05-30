"""Neural-Symbolic Reasoning — Phase 10

Hybrid neuro-symbolic reasoning with forward/backward chaining.
"""

from .neural_symbolic import (
    BackwardChainer,
    Fact,
    ForwardChainer,
    InferenceDirection,
    KnowledgeBase,
    LogicType,
    NeuralPredicateEvaluator,
    NeuralSymbolicReasoner,
    Predicate,
    ProofStep,
    ReasoningResult,
    ReasoningStatus,
    Rule,
    Symbol,
)

__all__ = [
    "LogicType",
    "InferenceDirection",
    "ReasoningStatus",
    "Symbol",
    "Predicate",
    "Rule",
    "Fact",
    "ProofStep",
    "ReasoningResult",
    "KnowledgeBase",
    "NeuralPredicateEvaluator",
    "ForwardChainer",
    "BackwardChainer",
    "NeuralSymbolicReasoner",
]
