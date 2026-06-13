"""Self-Modifying Code Engine — Phase 10

Runtime code evolution with genetic programming principles.
"""

from .self_modifying_code import (
    CodeAnalyzer,
    CodeMutation,
    CodeSnapshot,
    FitnessFunction,
    MutationEngine,
    MutationStatus,
    MutationType,
    SafetyLevel,
    SelfModifyingCodeEngine,
)

__all__ = [
    "MutationType",
    "MutationStatus",
    "SafetyLevel",
    "CodeMutation",
    "CodeSnapshot",
    "FitnessFunction",
    "CodeAnalyzer",
    "MutationEngine",
    "SelfModifyingCodeEngine",
]
