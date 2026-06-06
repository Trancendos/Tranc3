"""Roadmap Generator — Phase 9

AI-driven development roadmap generator that creates, prioritizes,
and tracks implementation roadmaps using SHI-powered reasoning
with heuristic fallback.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RoadmapPriority(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DEFERRED = "deferred"


class RoadmapStatus(Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskCategory(Enum):
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    PERFORMANCE = "performance"
    FEATURE = "feature"
    REFACTORING = "refactoring"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    RESEARCH = "research"
    INTEGRATION = "integration"
    DEPLOYMENT = "deployment"


@dataclass
class RoadmapTask:
    """A single task in the roadmap."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    description: str = ""
    category: TaskCategory = TaskCategory.FEATURE
    priority: RoadmapPriority = RoadmapPriority.MEDIUM
    status: RoadmapStatus = RoadmapStatus.PROPOSED
    phase: str = ""
    estimated_effort_hours: float = 0.0
    dependencies: List[str] = field(default_factory=list)
    assignee: str = ""
    tags: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    risk_score: float = 0.0
    impact_score: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "phase": self.phase,
            "estimated_effort_hours": self.estimated_effort_hours,
            "dependencies": self.dependencies,
            "assignee": self.assignee,
            "tags": self.tags,
            "acceptance_criteria": self.acceptance_criteria,
            "risk_score": self.risk_score,
            "impact_score": self.impact_score,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }


@dataclass
class RoadmapMilestone:
    """A milestone grouping multiple tasks."""

    milestone_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    phase: str = ""
    target_date: str = ""
    tasks: List[str] = field(default_factory=list)
    completion_percentage: float = 0.0
    status: RoadmapStatus = RoadmapStatus.PROPOSED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "milestone_id": self.milestone_id,
            "name": self.name,
            "description": self.description,
            "phase": self.phase,
            "target_date": self.target_date,
            "tasks": self.tasks,
            "completion_percentage": self.completion_percentage,
            "status": self.status.value,
        }


class PriorityCalculator:
    """Calculates task priority using multi-factor scoring."""

    def calculate(self, task: RoadmapTask, context: Dict[str, Any]) -> float:
        risk_weight = context.get("risk_weight", 0.3)
        impact_weight = context.get("impact_weight", 0.4)
        effort_weight = context.get("effort_weight", 0.2)
        dependency_weight = context.get("dependency_weight", 0.1)

        risk_score = task.risk_score / 10.0
        impact_score = task.impact_score / 10.0
        effort_score = max(0, 1.0 - (task.estimated_effort_hours / 100.0))
        dep_score = min(1.0, len(task.dependencies) / 5.0)

        return (
            risk_score * risk_weight
            + impact_score * impact_weight
            + effort_score * effort_weight
            + dep_score * dependency_weight
        )


class DependencyResolver:
    """Resolves task dependencies and produces valid execution order."""

    def topological_sort(self, tasks: List[RoadmapTask]) -> List[RoadmapTask]:
        task_map = {t.task_id: t for t in tasks}
        in_degree: Dict[str, int] = {t.task_id: 0 for t in tasks}
        graph: Dict[str, List[str]] = {t.task_id: [] for t in tasks}

        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id in graph:
                    graph[dep_id].append(task.task_id)
                    in_degree[task.task_id] += 1

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        sorted_ids: List[str] = []

        while queue:
            current = queue.pop(0)
            sorted_ids.append(current)
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        remaining = [tid for tid in in_degree if in_degree[tid] > 0]
        if remaining:
            logger.warning("Circular dependencies detected: %s", remaining)
            sorted_ids.extend(remaining)

        return [task_map[tid] for tid in sorted_ids if tid in task_map]

    def detect_circular(self, tasks: List[RoadmapTask]) -> List[List[str]]:
        task_ids = {t.task_id for t in tasks}
        visited: set = set()
        rec_stack: set = set()
        cycles: List[List[str]] = []

        adj: Dict[str, List[str]] = {t.task_id: [] for t in tasks}
        for t in tasks:
            for dep in t.dependencies:
                if dep in task_ids:
                    adj[dep].append(t.task_id)

        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            for neighbor in adj[node]:
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])
            path.pop()
            rec_stack.discard(node)

        for t in tasks:
            if t.task_id not in visited:
                dfs(t.task_id, [])

        return cycles


class SHIRoadmapAdvisor:
    """Uses SHI (Self-Hosted Inference) for AI-driven roadmap insights."""

    def __init__(self, shi_url: str = "http://localhost:7781"):
        self.shi_url = shi_url
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._available is None:
            try:
                import urllib.request

                req = urllib.request.Request(f"{self.shi_url}/health", method="GET")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    self._available = resp.status == 200
            except Exception:
                self._available = False
        return self._available

    def suggest_task_breakdown(self, task: RoadmapTask) -> List[RoadmapTask]:
        if not self.is_available():
            return self._heuristic_breakdown(task)
        try:
            import urllib.request

            prompt = f"Break down this task into subtasks: {task.title} — {task.description}"
            data = json.dumps({"prompt": prompt, "max_tokens": 512}).encode()
            req = urllib.request.Request(
                f"{self.shi_url}/v1/completions",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                text = result.get("choices", [{}])[0].get("text", "")
                return self._parse_subtasks(text, task)
        except Exception as e:
            logger.warning("SHI breakdown failed: %s, using heuristic", e)
            return self._heuristic_breakdown(task)

    def _heuristic_breakdown(self, task: RoadmapTask) -> List[RoadmapTask]:
        subtasks = []
        phases = ["Design & Planning", "Implementation", "Testing", "Documentation", "Integration"]
        for i, phase_name in enumerate(phases):
            subtasks.append(
                RoadmapTask(
                    title=f"{task.title} — {phase_name}",
                    description=f"{phase_name} phase for: {task.description}",
                    category=task.category,
                    priority=task.priority,
                    phase=task.phase,
                    estimated_effort_hours=task.estimated_effort_hours / len(phases),
                    dependencies=[subtasks[-1].task_id] if subtasks else [],
                    tags=task.tags + [phase_name.lower().replace(" ", "-")],
                ),
            )
        return subtasks

    def _parse_subtasks(self, text: str, parent: RoadmapTask) -> List[RoadmapTask]:
        lines = [l.strip().lstrip("0123456789.-) ") for l in text.split("\n") if l.strip()]
        subtasks = []
        for line in lines[:10]:
            if len(line) > 5:
                subtasks.append(
                    RoadmapTask(
                        title=line[:100],
                        description=f"Subtask of {parent.title}: {line}",
                        category=parent.category,
                        priority=parent.priority,
                        phase=parent.phase,
                        estimated_effort_hours=parent.estimated_effort_hours / max(1, len(lines)),
                        dependencies=[],
                        tags=parent.tags,
                    ),
                )
        return subtasks if subtasks else self._heuristic_breakdown(parent)


class RoadmapGenerator:
    """AI-driven roadmap generator for the Tranc3 ecosystem.

    Features:
    - SHI-powered task analysis and breakdown
    - Multi-factor priority scoring
    - Dependency resolution with cycle detection
    - Milestone tracking and progress reporting
    - Heuristic fallback when SHI unavailable
    """

    def __init__(self, shi_url: str = "http://localhost:7781"):
        self.shi_advisor = SHIRoadmapAdvisor(shi_url)
        self.priority_calculator = PriorityCalculator()
        self.dependency_resolver = DependencyResolver()
        self.tasks: Dict[str, RoadmapTask] = {}
        self.milestones: Dict[str, RoadmapMilestone] = {}
        self._id = str(uuid.uuid4())[:8]

    def add_task(self, task: RoadmapTask) -> str:
        self.tasks[task.task_id] = task
        logger.info("Added task %s: %s", task.task_id, task.title)
        return task.task_id

    def remove_task(self, task_id: str) -> bool:
        if task_id in self.tasks:
            del self.tasks[task_id]
            for t in self.tasks.values():
                if task_id in t.dependencies:
                    t.dependencies.remove(task_id)
            return True
        return False

    def update_task(self, task_id: str, **kwargs: Any) -> Optional[RoadmapTask]:
        task = self.tasks.get(task_id)
        if not task:
            return None
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = datetime.now(timezone.utc).isoformat()
        return task

    def add_milestone(self, milestone: RoadmapMilestone) -> str:
        self.milestones[milestone.milestone_id] = milestone
        return milestone.milestone_id

    def prioritize(self, context: Optional[Dict[str, Any]] = None) -> List[RoadmapTask]:
        ctx = context or {}
        scored = []
        for task in self.tasks.values():
            score = self.priority_calculator.calculate(task, ctx)
            task.metadata["priority_score"] = score
            scored.append((score, task))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored]

    def resolve_dependencies(self) -> List[RoadmapTask]:
        return self.dependency_resolver.topological_sort(list(self.tasks.values()))

    def detect_circular_dependencies(self) -> List[List[str]]:
        return self.dependency_resolver.detect_circular(list(self.tasks.values()))

    def break_down_task(self, task_id: str) -> List[RoadmapTask]:
        task = self.tasks.get(task_id)
        if not task:
            return []
        subtasks = self.shi_advisor.suggest_task_breakdown(task)
        for sub in subtasks:
            self.tasks[sub.task_id] = sub
        return subtasks

    def get_milestone_progress(self, milestone_id: str) -> Dict[str, Any]:
        milestone = self.milestones.get(milestone_id)
        if not milestone:
            return {"error": "Milestone not found"}
        total = len(milestone.tasks)
        completed = sum(
            1
            for tid in milestone.tasks
            if self.tasks.get(tid, RoadmapTask()).status == RoadmapStatus.COMPLETED
        )
        milestone.completion_percentage = (completed / total * 100) if total > 0 else 0
        return {
            "milestone_id": milestone_id,
            "name": milestone.name,
            "total_tasks": total,
            "completed_tasks": completed,
            "completion_percentage": milestone.completion_percentage,
            "status": milestone.status.value,
        }

    def generate_roadmap(self, phase: Optional[str] = None) -> Dict[str, Any]:
        tasks = list(self.tasks.values())
        if phase:
            tasks = [t for t in tasks if t.phase == phase]
        prioritized = self.prioritize()
        ordered = self.resolve_dependencies()
        cycles = self.detect_circular_dependencies()
        phase_tasks = [t for t in prioritized if not phase or t.phase == phase]

        return {
            "roadmap_id": self._id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "total_tasks": len(self.tasks),
            "phase_tasks": len(phase_tasks),
            "prioritized_tasks": [t.to_dict() for t in phase_tasks],
            "execution_order": [t.task_id for t in ordered],
            "circular_dependencies": cycles,
            "milestones": {mid: m.to_dict() for mid, m in self.milestones.items()},
            "shi_available": self.shi_advisor.is_available(),
        }

    def export_roadmap(self, phase: Optional[str] = None) -> str:
        return json.dumps(self.generate_roadmap(phase), indent=2)

    def import_roadmap(self, json_str: str) -> int:
        data = json.loads(json_str)
        count = 0
        for task_data in data.get("prioritized_tasks", []):
            task = RoadmapTask(
                task_id=task_data.get("task_id", str(uuid.uuid4())[:8]),
                title=task_data.get("title", ""),
                description=task_data.get("description", ""),
                category=TaskCategory(task_data.get("category", "feature")),
                priority=RoadmapPriority(task_data.get("priority", "medium")),
                status=RoadmapStatus(task_data.get("status", "proposed")),
                phase=task_data.get("phase", ""),
                estimated_effort_hours=task_data.get("estimated_effort_hours", 0),
                dependencies=task_data.get("dependencies", []),
                tags=task_data.get("tags", []),
            )
            self.tasks[task.task_id] = task
            count += 1
        return count
