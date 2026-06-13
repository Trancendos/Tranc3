"""Neural-Symbolic Reasoning — Phase 10

Hybrid neuro-symbolic reasoning with forward/backward chaining.
"""

from .neural_symbolic import (
    LogicType,
    InferenceDirection,
    ReasoningStatus,
    Symbol,
    Predicate,
    Rule,
    Fact,
    ProofStep,
    ReasoningResult,
    KnowledgeBase,
    NeuralPredicateEvaluator,
    ForwardChainer,
    BackwardChainer,
    NeuralSymbolicReasoner,
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
