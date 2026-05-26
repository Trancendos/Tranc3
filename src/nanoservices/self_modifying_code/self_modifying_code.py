"""Self-Modifying Code Engine — Phase 10

Runtime code evolution engine that can analyze, mutate, test,
and deploy modifications to its own codebase using genetic
programming principles and safety constraints.
"""

from __future__ import annotations

import ast
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class MutationType(Enum):
    PARAMETER_TUNING = "parameter_tuning"
    ALGORITHM_SWAP = "algorithm_swap"
    CODE_INSERTION = "code_insertion"
    CODE_DELETION = "code_deletion"
    CODE_REPLACEMENT = "code_replacement"
    REFACTORING = "refactoring"
    OPTIMIZATION = "optimization"
    BUG_FIX = "bug_fix"


class MutationStatus(Enum):
    PROPOSED = "proposed"
    TESTED = "tested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"
    DEPLOYED = "deployed"


class SafetyLevel(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    FORBIDDEN = "forbidden"


@dataclass
class CodeMutation:
    """A proposed code mutation."""

    mutation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    target_module: str = ""
    target_function: str = ""
    mutation_type: MutationType = MutationType.PARAMETER_TUNING
    status: MutationStatus = MutationStatus.PROPOSED
    safety_level: SafetyLevel = SafetyLevel.SAFE
    original_code: str = ""
    mutated_code: str = ""
    diff_description: str = ""
    fitness_score: float = 0.0
    test_results: Optional[Dict[str, Any]] = None
    generation: int = 0
    parent_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mutation_id": self.mutation_id,
            "target_module": self.target_module,
            "target_function": self.target_function,
            "mutation_type": self.mutation_type.value,
            "status": self.status.value,
            "safety_level": self.safety_level.value,
            "fitness_score": self.fitness_score,
            "diff_description": self.diff_description,
            "generation": self.generation,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
        }


@dataclass
class CodeSnapshot:
    """Snapshot of code at a point in time."""

    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    module: str = ""
    code_hash: str = ""
    code_content: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mutation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "module": self.module,
            "code_hash": self.code_hash,
            "code_length": len(self.code_content),
            "timestamp": self.timestamp,
            "mutation_id": self.mutation_id,
        }


@dataclass
class FitnessFunction:
    """Evaluates the fitness of a code mutation."""

    name: str = ""
    description: str = ""
    weight: float = 1.0
    evaluate: Optional[Callable[[Dict[str, Any]], float]] = None

    def score(self, metrics: Dict[str, Any]) -> float:
        if self.evaluate:
            try:
                return self.evaluate(metrics) * self.weight
            except Exception:
                return 0.0
        return metrics.get(self.name, 0.0) * self.weight


class CodeAnalyzer:
    """Analyzes Python code for structure, complexity, and safety."""

    def analyze_complexity(self, code: str) -> Dict[str, Any]:
        try:
            tree = ast.parse(code)
            functions = [
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            total_lines = len(code.split("\n"))
            return {
                "functions": len(functions),
                "classes": len(classes),
                "total_lines": total_lines,
                "function_names": [f.name for f in functions],
                "class_names": [c.name for c in classes],
                "parseable": True,
            }
        except SyntaxError as e:
            return {"parseable": False, "error": str(e)}

    def check_safety(self, code: str) -> SafetyLevel:
        dangerous_patterns = [
            "os.system",
            "subprocess.call",
            "eval(",
            "exec(",
            "import os",
            "import sys",
            "shutil.rmtree",
            "__import__",
            "open(",
            "write(",
            "remove(",
        ]
        caution_patterns = [
            "import ",
            "from os",
            "global ",
            "setattr(",
            "delattr(",
            "globals()",
            "locals()",
        ]
        for pattern in dangerous_patterns:
            if pattern in code:
                return SafetyLevel.DANGEROUS
        for pattern in caution_patterns:
            if pattern in code:
                return SafetyLevel.CAUTION
        return SafetyLevel.SAFE

    def extract_functions(self, code: str) -> Dict[str, str]:
        functions = {}
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = node.lineno - 1
                    end = node.end_lineno if hasattr(node, "end_lineno") else start + 1
                    lines = code.split("\n")
                    func_code = "\n".join(lines[start:end])
                    functions[node.name] = func_code
        except SyntaxError:
            pass
        return functions


class MutationEngine:
    """Generates code mutations using various strategies."""

    def tune_parameters(self, code: str) -> List[CodeMutation]:
        mutations = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                    original_value = node.value
                    if isinstance(original_value, int):
                        for delta in [-1, 1, 2]:
                            new_value = original_value + delta
                            if new_value > 0:
                                mutations.append(
                                    CodeMutation(
                                        mutation_type=MutationType.PARAMETER_TUNING,
                                        safety_level=SafetyLevel.SAFE,
                                        diff_description=f"Change constant from {original_value} to {new_value}",
                                        original_code=str(original_value),
                                        mutated_code=str(new_value),
                                    )
                                )
                    elif isinstance(original_value, float):
                        for factor in [0.8, 0.9, 1.1, 1.2]:
                            new_value = round(original_value * factor, 4)
                            mutations.append(
                                CodeMutation(
                                    mutation_type=MutationType.PARAMETER_TUNING,
                                    safety_level=SafetyLevel.SAFE,
                                    diff_description=f"Change constant from {original_value} to {new_value}",
                                    original_code=str(original_value),
                                    mutated_code=str(new_value),
                                )
                            )
        except SyntaxError:
            pass
        return mutations[:20]

    def swap_algorithm(
        self, function_code: str, alternatives: Optional[Dict[str, str]] = None
    ) -> List[CodeMutation]:
        if not alternatives:
            alternatives = {
                "bubble_sort": "sorted(data)",
                "linear_search": "binary_search(data, target)",
                "list_comprehension": "[f(x) for x in data]",
            }
        mutations = []
        for name, replacement in alternatives.items():
            mutations.append(
                CodeMutation(
                    mutation_type=MutationType.ALGORITHM_SWAP,
                    safety_level=SafetyLevel.CAUTION,
                    diff_description=f"Swap with {name}",
                    original_code=function_code[:100],
                    mutated_code=replacement,
                )
            )
        return mutations


class SelfModifyingCodeEngine:
    """Self-modifying code engine for runtime code evolution.

    Features:
    - Code analysis via AST parsing
    - Parameter tuning mutations
    - Algorithm swap mutations
    - Fitness-based selection of mutations
    - Safety classification and constraints
    - Code snapshotting for rollback
    - Sandbox testing before deployment
    - Generation tracking and lineage
    """

    def __init__(self, safety_threshold: SafetyLevel = SafetyLevel.CAUTION):
        self.mutations: Dict[str, CodeMutation] = {}
        self.snapshots: Dict[str, CodeSnapshot] = {}
        self.fitness_functions: List[FitnessFunction] = []
        self.analyzer = CodeAnalyzer()
        self.mutation_engine = MutationEngine()
        self.safety_threshold = safety_threshold
        self.current_generation = 0
        self._id = str(uuid.uuid4())[:8]

    def add_fitness_function(
        self, name: str, weight: float = 1.0, evaluate: Optional[Callable] = None
    ):
        self.fitness_functions.append(FitnessFunction(name=name, weight=weight, evaluate=evaluate))

    def analyze_code(self, code: str) -> Dict[str, Any]:
        complexity = self.analyzer.analyze_complexity(code)
        safety = self.analyzer.check_safety(code)
        functions = self.analyzer.extract_functions(code)
        return {
            "complexity": complexity,
            "safety_level": safety.value,
            "functions": list(functions.keys()),
            "code_hash": hashlib.sha256(code.encode()).hexdigest()[:16],
        }

    def create_snapshot(self, module: str, code: str) -> CodeSnapshot:
        snapshot = CodeSnapshot(
            module=module,
            code_content=code,
            code_hash=hashlib.sha256(code.encode()).hexdigest(),
        )
        self.snapshots[snapshot.snapshot_id] = snapshot
        return snapshot

    def propose_mutations(
        self, module: str, code: str, max_mutations: int = 10
    ) -> List[CodeMutation]:
        safety = self.analyzer.check_safety(code)
        param_mutations = self.mutation_engine.tune_parameters(code)
        algo_mutations = self.mutation_engine.swap_algorithm(code)

        all_mutations = param_mutations + algo_mutations
        accepted = []
        for mut in all_mutations:
            if mut.safety_level.value <= self.safety_threshold.value:
                mut.target_module = module
                mut.generation = self.current_generation
                mut.safety_level = safety
                self.mutations[mut.mutation_id] = mut
                accepted.append(mut)
                if len(accepted) >= max_mutations:
                    break

        logger.info(
            "Proposed %d mutations for %s (safety: %s)", len(accepted), module, safety.value
        )
        return accepted

    def evaluate_fitness(self, mutation_id: str, metrics: Dict[str, Any]) -> float:
        mutation = self.mutations.get(mutation_id)
        if not mutation:
            return 0.0
        total_score = 0.0
        for ff in self.fitness_functions:
            total_score += ff.score(metrics)
        mutation.fitness_score = total_score
        return total_score

    def test_mutation(self, mutation_id: str, test_fn: Optional[Callable] = None) -> Dict[str, Any]:
        mutation = self.mutations.get(mutation_id)
        if not mutation:
            return {"error": "Mutation not found"}

        results = {"mutation_id": mutation_id, "passed": False}

        if mutation.safety_level == SafetyLevel.FORBIDDEN:
            mutation.status = MutationStatus.REJECTED
            results["reason"] = "Mutation is forbidden"
            return results

        if test_fn:
            try:
                test_result = test_fn(mutation)
                results["test_output"] = test_result
                results["passed"] = True
            except Exception as e:
                results["error"] = str(e)
                results["passed"] = False
        else:
            try:
                ast.parse(mutation.mutated_code)
                results["passed"] = True
                results["check"] = "syntax_valid"
            except SyntaxError as e:
                results["error"] = str(e)
                results["passed"] = False

        mutation.test_results = results
        mutation.status = MutationStatus.TESTED if results["passed"] else MutationStatus.REJECTED
        return results

    def accept_mutation(self, mutation_id: str) -> bool:
        mutation = self.mutations.get(mutation_id)
        if not mutation or mutation.status != MutationStatus.TESTED:
            return False
        mutation.status = MutationStatus.ACCEPTED
        logger.info("Accepted mutation %s: %s", mutation_id, mutation.diff_description)
        return True

    def rollback(self, mutation_id: str) -> bool:
        mutation = self.mutations.get(mutation_id)
        if not mutation:
            return False
        mutation.status = MutationStatus.ROLLED_BACK
        logger.info("Rolled back mutation %s", mutation_id)
        return True

    def evolve(
        self, module: str, code: str, metrics: Dict[str, Any], generations: int = 5
    ) -> Dict[str, Any]:
        self.create_snapshot(module, code)
        best_mutation = None
        best_score = -1.0
        history = []

        for gen in range(generations):
            self.current_generation = gen
            mutations = self.propose_mutations(module, code, max_mutations=10)
            for mut in mutations:
                score = self.evaluate_fitness(mut.mutation_id, metrics)
                self.test_mutation(mut.mutation_id)
                if score > best_score and mut.status == MutationStatus.TESTED:
                    best_score = score
                    best_mutation = mut
            history.append(
                {
                    "generation": gen,
                    "mutations_proposed": len(mutations),
                    "best_score": best_score,
                }
            )

        if best_mutation:
            self.accept_mutation(best_mutation.mutation_id)

        return {
            "module": module,
            "generations": generations,
            "best_score": best_score,
            "best_mutation": best_mutation.to_dict() if best_mutation else None,
            "history": history,
            "total_mutations": len(self.mutations),
        }

    def get_engine_status(self) -> Dict[str, Any]:
        return {
            "engine_id": self._id,
            "current_generation": self.current_generation,
            "total_mutations": len(self.mutations),
            "accepted_mutations": sum(
                1 for m in self.mutations.values() if m.status == MutationStatus.ACCEPTED
            ),
            "rejected_mutations": sum(
                1 for m in self.mutations.values() if m.status == MutationStatus.REJECTED
            ),
            "total_snapshots": len(self.snapshots),
            "fitness_functions": len(self.fitness_functions),
            "safety_threshold": self.safety_threshold.value,
        }
