"""
task_decomposer.py — Hierarchical Task Planning for Tranc3 Platform (Phase 5)

Decomposes high-level goals into structured, executable subtasks using
pattern-based decomposition strategies:

  1. Pattern matching: recognizes common goal patterns (analyze, create,
     debug, research, etc.) and applies known decomposition templates.
  2. Heuristic decomposition: for unrecognized goals, applies a generic
     plan-execute-verify loop.
  3. Recursive decomposition: subtasks that are still too complex can
     be further decomposed in a subsequent pass.

Each subtask specifies:
  - A description of what needs to be done
  - A suggested tool to use (from the ToolBridge registry)
  - Tool arguments (partially filled from context)
  - Dependencies on other subtasks (execution order)
  - Estimated complexity (for priority scheduling)

The TaskDecomposer is stateless: each call to decompose() is independent,
making it safe for concurrent use by multiple agents.

Zero-cost: pure Python, no external LLM API calls.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SubTask model
# ---------------------------------------------------------------------------


@dataclass
class SubTask:
    """
    A single executable subtask within a decomposition plan.

    Attributes:
        subtask_id: unique identifier
        description: human-readable description of the subtask
        suggested_tool: name of the ToolBridge tool to invoke
        tool_args: arguments to pass to the tool
        dependencies: IDs of subtasks that must complete first
        complexity: estimated complexity (1=simple, 5=very complex)
        status: current execution status
        result: output from execution (populated after running)
        order: suggested execution order (lower = earlier)
    """

    subtask_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    suggested_tool: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    dependencies: Set[str] = field(default_factory=set)
    complexity: int = 3
    status: str = "pending"  # pending | running | completed | failed | skipped
    result: Optional[Any] = None
    order: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "description": self.description,
            "suggested_tool": self.suggested_tool,
            "tool_args": self.tool_args,
            "dependencies": sorted(self.dependencies),
            "complexity": self.complexity,
            "status": self.status,
            "order": self.order,
        }


# ---------------------------------------------------------------------------
# Decomposition result
# ---------------------------------------------------------------------------


@dataclass
class Decomposition:
    """
    Result of decomposing a goal into subtasks.

    Attributes:
        goal_description: the original goal that was decomposed
        subtasks: ordered list of SubTask instances
        strategy: which decomposition strategy was used
        estimated_total_complexity: sum of subtask complexities
    """

    goal_description: str = ""
    subtasks: List[SubTask] = field(default_factory=list)
    strategy: str = "generic"
    estimated_total_complexity: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_description": self.goal_description,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "strategy": self.strategy,
            "estimated_total_complexity": self.estimated_total_complexity,
        }

    def get_execution_order(self) -> List[SubTask]:
        """
        Return subtasks in a valid execution order respecting dependencies.
        Uses topological sort with order as tiebreaker.
        """
        if not self.subtasks:
            return []

        # Build adjacency
        subtask_map = {st.subtask_id: st for st in self.subtasks}
        in_degree = {st.subtask_id: 0 for st in self.subtasks}
        for st in self.subtasks:
            for dep in st.dependencies:
                if dep in in_degree:
                    in_degree[st.subtask_id] += 1

        # Kahn's algorithm
        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        queue.sort(key=lambda sid: subtask_map[sid].order)

        ordered: List[SubTask] = []
        while queue:
            current_id = queue.pop(0)
            current = subtask_map[current_id]
            ordered.append(current)

            for st in self.subtasks:
                if current_id in st.dependencies:
                    in_degree[st.subtask_id] -= 1
                    if in_degree[st.subtask_id] == 0:
                        queue.append(st.subtask_id)
                        queue.sort(key=lambda sid: subtask_map[sid].order)

        return ordered


# ---------------------------------------------------------------------------
# Decomposition patterns
# ---------------------------------------------------------------------------

# Each pattern is (regex, strategy_name, decomposition_template)
# The template is a list of dicts with keys: description, tool, args, complexity
_DECOMPOSITION_PATTERNS: List[tuple[re.Pattern, str, List[Dict[str, Any]]]] = [
    (
        re.compile(r"\b(analyze|analyse|assess|evaluate|review)\b", re.IGNORECASE),
        "analysis",
        [
            {
                "description": "Gather information and data related to the goal",
                "tool": "query_vector_store",
                "args": {},
                "complexity": 2,
            },
            {
                "description": "Search knowledge base for relevant context",
                "tool": "search_skills",
                "args": {},
                "complexity": 2,
            },
            {
                "description": "Perform analysis on the gathered data",
                "tool": "execute_code",
                "args": {},
                "complexity": 4,
            },
            {
                "description": "Synthesize findings and generate report",
                "tool": "run_workflow",
                "args": {},
                "complexity": 3,
            },
        ],
    ),
    (
        re.compile(r"\b(create|build|implement|develop|generate|write)\b", re.IGNORECASE),
        "creation",
        [
            {
                "description": "Research requirements and existing solutions",
                "tool": "search_skills",
                "args": {},
                "complexity": 2,
            },
            {
                "description": "Design the solution approach",
                "tool": "attention_route",
                "args": {},
                "complexity": 3,
            },
            {
                "description": "Implement the solution",
                "tool": "execute_code",
                "args": {},
                "complexity": 5,
            },
            {
                "description": "Test the implementation",
                "tool": "execute_code",
                "args": {},
                "complexity": 3,
            },
            {
                "description": "Validate and document the result",
                "tool": "run_workflow",
                "args": {},
                "complexity": 2,
            },
        ],
    ),
    (
        re.compile(r"\b(debug|fix|repair|resolve|troubleshoot)\b", re.IGNORECASE),
        "debugging",
        [
            {
                "description": "Reproduce and identify the issue",
                "tool": "execute_code",
                "args": {},
                "complexity": 3,
            },
            {
                "description": "Diagnose root cause",
                "tool": "causal_diagnose",
                "args": {},
                "complexity": 4,
            },
            {
                "description": "Implement the fix",
                "tool": "execute_code",
                "args": {},
                "complexity": 4,
            },
            {
                "description": "Verify the fix resolves the issue",
                "tool": "execute_code",
                "args": {},
                "complexity": 2,
            },
        ],
    ),
    (
        re.compile(r"\b(research|investigate|explore|study|find)\b", re.IGNORECASE),
        "research",
        [
            {
                "description": "Search knowledge base for relevant information",
                "tool": "query_vector_store",
                "args": {},
                "complexity": 2,
            },
            {
                "description": "Query the semantic knowledge graph",
                "tool": "knowledge_graph_query",
                "args": {},
                "complexity": 3,
            },
            {
                "description": "Search for related patterns in collective memory",
                "tool": "collective_memory_query",
                "args": {},
                "complexity": 2,
            },
            {
                "description": "Synthesize research findings",
                "tool": "run_workflow",
                "args": {},
                "complexity": 3,
            },
        ],
    ),
    (
        re.compile(r"\b(secur|protect|guard|harden|audit)\b", re.IGNORECASE),
        "security",
        [
            {
                "description": "Assess current security posture",
                "tool": "get_system_health",
                "args": {},
                "complexity": 2,
            },
            {
                "description": "Scan for vulnerabilities and anomalies",
                "tool": "causal_diagnose",
                "args": {},
                "complexity": 4,
            },
            {
                "description": "Apply security hardening measures",
                "tool": "execute_code",
                "args": {},
                "complexity": 4,
            },
            {
                "description": "Verify security improvements",
                "tool": "get_system_health",
                "args": {},
                "complexity": 2,
            },
        ],
    ),
    (
        re.compile(r"\b(plan|schedule|organize|coordinate|orchestrate)\b", re.IGNORECASE),
        "planning",
        [
            {
                "description": "Identify all required tasks and dependencies",
                "tool": "search_skills",
                "args": {},
                "complexity": 3,
            },
            {
                "description": "Route tasks to appropriate services",
                "tool": "attention_route",
                "args": {},
                "complexity": 3,
            },
            {
                "description": "Create the execution workflow",
                "tool": "register_workflow",
                "args": {},
                "complexity": 4,
            },
            {
                "description": "Execute and monitor the plan",
                "tool": "run_workflow",
                "args": {},
                "complexity": 3,
            },
        ],
    ),
    (
        re.compile(r"\b(predict|forecast|estimate|anticipate)\b", re.IGNORECASE),
        "prediction",
        [
            {
                "description": "Gather historical data and context",
                "tool": "collective_memory_query",
                "args": {},
                "complexity": 2,
            },
            {
                "description": "Build causal model of the system",
                "tool": "causal_predict",
                "args": {},
                "complexity": 4,
            },
            {
                "description": "Generate predictions with confidence intervals",
                "tool": "meta_learn_adapt",
                "args": {},
                "complexity": 3,
            },
        ],
    ),
]


# ---------------------------------------------------------------------------
# Task Decomposer
# ---------------------------------------------------------------------------


class TaskDecomposer:
    """
    Decomposes high-level goals into structured, executable subtasks.

    Uses pattern matching to select an appropriate decomposition strategy,
    then instantiates SubTask objects with suggested tools and arguments.

    Usage:
        decomposer = TaskDecomposer()
        decomposition = await decomposer.decompose("Analyze the codebase for security vulnerabilities")
        for subtask in decomposition.get_execution_order():
            print(f"  {subtask.order}. {subtask.description} (tool: {subtask.suggested_tool})")
    """

    def __init__(self, max_subtasks: int = 15) -> None:
        self._max_subtasks = max_subtasks

    async def decompose(
        self,
        goal_description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Decomposition:
        """
        Decompose a goal description into a list of subtasks.

        Args:
            goal_description: the high-level goal to decompose
            context: optional context dict with agent_id, available tools, etc.

        Returns:
            A Decomposition containing the ordered subtasks.
        """
        context = context or {}

        # Try pattern matching first
        for pattern, strategy, template in _DECOMPOSITION_PATTERNS:
            if pattern.search(goal_description):
                logger.debug(
                    "Decomposing goal with strategy '%s': %s",
                    strategy,
                    goal_description[:80],
                )
                return self._build_decomposition(
                    goal_description,
                    strategy,
                    template,
                    context,
                )

        # Fall back to generic decomposition
        logger.debug("Using generic decomposition for: %s", goal_description[:80])
        return self._build_generic_decomposition(goal_description, context)

    # -------------------------------------------------------------------
    # Internal: build decomposition from template
    # -------------------------------------------------------------------

    def _build_decomposition(
        self,
        goal_description: str,
        strategy: str,
        template: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Decomposition:
        """Build a Decomposition from a matched template."""
        subtasks: List[SubTask] = []
        prev_id: Optional[str] = None

        for i, step in enumerate(template[: self._max_subtasks]):
            subtask = SubTask(
                description=step.get("description", f"Step {i + 1}"),
                suggested_tool=step.get("tool", ""),
                tool_args={**step.get("args", {}), "goal": goal_description},
                complexity=step.get("complexity", 3),
                order=i,
            )

            # Chain dependencies: each step depends on the previous
            if prev_id is not None and step.get("chain", True):
                subtask.dependencies.add(prev_id)

            subtasks.append(subtask)
            prev_id = subtask.subtask_id

        return Decomposition(
            goal_description=goal_description,
            subtasks=subtasks,
            strategy=strategy,
            estimated_total_complexity=sum(st.complexity for st in subtasks),
        )

    def _build_generic_decomposition(
        self,
        goal_description: str,
        context: Dict[str, Any],
    ) -> Decomposition:
        """
        Build a generic plan-execute-verify decomposition for goals
        that don't match any known pattern.
        """
        generic_template = [
            {
                "description": f"Plan approach for: {goal_description}",
                "tool": "search_skills",
                "args": {},
                "complexity": 2,
            },
            {
                "description": f"Execute primary task: {goal_description}",
                "tool": "execute_code",
                "args": {},
                "complexity": 4,
            },
            {
                "description": f"Verify outcome of: {goal_description}",
                "tool": "run_workflow",
                "args": {},
                "complexity": 2,
            },
        ]

        return self._build_decomposition(
            goal_description,
            "generic",
            generic_template,
            context,
        )
