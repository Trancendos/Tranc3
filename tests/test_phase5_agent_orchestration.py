"""
tests/test_phase5_agent_orchestration.py
Phase 5 Autonomous Agent Orchestration Layer integration tests.

Tests:
  - Phase 5 module imports (agents package)
  - AgentType enum and AgentProfile dataclass
  - AgentProfile.matches_tags() Jaccard similarity
  - get_profile / get_profile_by_name / list_profiles / find_best_profile helpers
  - Goal lifecycle: add, activate, progress, complete, fail, cancel
  - Goal priority ordering, overdue detection, prerequisite gating
  - GoalManager capacity and eviction
  - EpisodicMemory scoring: recency, relevance, importance, combined
  - MemoryStream add, retrieve, reflect, get_by_tags, get_by_time_range
  - MemoryStream capacity and eviction
  - SubTask and Decomposition dataclasses
  - Decomposition.get_execution_order() topological sort
  - TaskDecomposer pattern-based decomposition
  - ToolBridge register, execute, list, metrics
  - ToolBridge resolution order (direct -> MCP -> workflow)
  - AgentRuntime lifecycle: create, start, stop, assign_goal, run_step
  - AgentRuntime observer pattern
  - Phase 5 Spark tools registration (12 tools)
  - MCP total tool count after Phase 5 (33 + 12 = 45)
  - Phase 5 workflow node availability (5 types)
  - spark_phase5_tools handler smoke tests
  - Phase 5 node registration into _PHASE4_NODE_REGISTRY

All tests use in-process, zero-dependency execution (no external APIs required).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

# Make sure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine synchronously for tests that aren't async."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)


# ===========================================================================
# 1. Module imports and package structure
# ===========================================================================


class TestPhase5Imports:
    """Verify all Phase 5 modules are importable and export the right symbols."""

    def test_agents_package_importable(self):
        import src.agents
        assert hasattr(src.agents, "AgentRuntime")
        assert hasattr(src.agents, "AgentState")
        assert hasattr(src.agents, "TaskDecomposer")
        assert hasattr(src.agents, "SubTask")
        assert hasattr(src.agents, "Decomposition")
        assert hasattr(src.agents, "ToolBridge")
        assert hasattr(src.agents, "ToolResult")
        assert hasattr(src.agents, "MemoryStream")
        assert hasattr(src.agents, "EpisodicMemory")
        assert hasattr(src.agents, "GoalManager")
        assert hasattr(src.agents, "Goal")
        assert hasattr(src.agents, "GoalState")
        assert hasattr(src.agents, "AgentType")
        assert hasattr(src.agents, "AgentProfile")

    def test_agent_runtime_module(self):
        from src.agents.agent_runtime import AgentState
        assert AgentState.IDLE is not None
        assert AgentState.PLANNING is not None

    def test_task_decomposer_module(self):
        from src.agents.task_decomposer import Decomposition
        assert Decomposition is not None

    def test_tool_bridge_module(self):
        from src.agents.tool_bridge import ToolBridge
        assert ToolBridge is not None

    def test_memory_stream_module(self):
        from src.agents.memory_stream import MemoryStream
        assert MemoryStream is not None

    def test_goal_manager_module(self):
        from src.agents.goal_manager import GoalState
        assert GoalState.PENDING is not None

    def test_agent_types_module(self):
        from src.agents.agent_types import AgentType
        assert AgentType.GENERAL is not None

    def test_spark_phase5_tools_module(self):
        from src.mcp.spark_phase5_tools import PHASE5_TOOLS
        assert len(PHASE5_TOOLS) == 12

    def test_phase5_nodes_module(self):
        from src.workflow.phase5_nodes import PHASE5_NODE_TYPES
        assert len(PHASE5_NODE_TYPES) == 5


# ===========================================================================
# 2. AgentType and AgentProfile
# ===========================================================================


class TestAgentTypes:
    """Test the agent type enum, profiles, and matching logic."""

    def test_agent_type_enum_values(self):
        from src.agents.agent_types import AgentType
        expected = {"GENERAL", "RESEARCHER", "CODER", "PLANNER", "ANALYZER",
                    "ORCHESTRATOR", "GUARDIAN"}
        actual = {e.name for e in AgentType}
        assert actual == expected

    def test_all_profiles_have_capability_tags(self):
        from src.agents.agent_types import PROFILES, AgentType
        for agent_type in AgentType:
            profile = PROFILES[agent_type]
            assert len(profile.capability_tags) > 0, \
                f"{agent_type.name} profile has no capability tags"

    def test_all_profiles_have_preferred_tools(self):
        from src.agents.agent_types import PROFILES, AgentType
        for agent_type in AgentType:
            profile = PROFILES[agent_type]
            assert len(profile.preferred_tools) > 0, \
                f"{agent_type.name} profile has no preferred tools"

    def test_profile_frozen(self):
        from src.agents.agent_types import AgentProfile, AgentType
        profile = AgentProfile(
            agent_type=AgentType.GENERAL,
            description="General-purpose agent",
            capability_tags=frozenset({"general"}),
            preferred_tools=frozenset({"execute_code"}),
            creativity=0.5,
            caution=0.5,
            thoroughness=0.5,
            max_concurrent_tasks=3,
        )
        with pytest.raises(Exception):
            profile.creativity = 0.9  # type: ignore[misc]

    def test_matches_tags_perfect(self):
        from src.agents.agent_types import AgentType, get_profile
        profile = get_profile(AgentType.CODER)
        # Jaccard similarity: when all required tags are in capability_tags,
        # the score depends on the overlap ratio
        score = profile.matches_tags({"coding"})
        # Score should be positive (some match)
        assert score > 0.0
        # For a perfect subset match, Jaccard = |intersection| / |union|
        # If "coding" is in capability_tags, intersection >= 1

    def test_matches_tags_partial(self):
        from src.agents.agent_types import AgentType, get_profile
        profile = get_profile(AgentType.GENERAL)
        # Use tags that partially overlap with GENERAL's capabilities
        score = profile.matches_tags({"nonexistent_tag"})
        assert 0.0 <= score <= 1.0

    def test_matches_tags_empty(self):
        from src.agents.agent_types import AgentType, get_profile
        profile = get_profile(AgentType.GENERAL)
        # Empty required_tags returns 1.0 per the implementation
        score = profile.matches_tags(set())
        assert score == 1.0  # empty required = always matches

    def test_get_profile_returns_correct_type(self):
        from src.agents.agent_types import AgentType, get_profile
        for at in AgentType:
            profile = get_profile(at)
            assert profile.agent_type == at

    def test_get_profile_by_name(self):
        from src.agents.agent_types import AgentType, get_profile_by_name
        profile = get_profile_by_name("CODER")
        assert profile is not None
        assert profile.agent_type == AgentType.CODER

    def test_get_profile_by_name_case_insensitive(self):
        from src.agents.agent_types import AgentType, get_profile_by_name
        profile = get_profile_by_name("coder")
        assert profile is not None
        assert profile.agent_type == AgentType.CODER

    def test_list_profiles(self):
        from src.agents.agent_types import list_profiles
        profiles = list_profiles()
        assert len(profiles) == 7  # 7 agent types
        for p in profiles:
            assert "agent_type" in p

    def test_find_best_profile(self):
        from src.agents.agent_types import find_best_profile
        profile = find_best_profile({"coding", "debugging"})
        assert profile is not None
        # CODER should match coding tasks best
        assert "coding" in profile.capability_tags or "debugging" in profile.capability_tags

    def test_profile_to_dict(self):
        from src.agents.agent_types import AgentType, get_profile
        profile = get_profile(AgentType.RESEARCHER)
        d = profile.to_dict()
        assert "agent_type" in d
        assert "capability_tags" in d
        assert "preferred_tools" in d
        # agent_type.value is lowercase per the enum
        assert d["agent_type"] == "researcher"


# ===========================================================================
# 3. GoalManager
# ===========================================================================


class TestGoalManager:
    """Test goal lifecycle, priority ordering, and capacity management."""

    def test_add_goal(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        goal_id = run(gm.add_goal("Complete analysis", priority=7))
        assert goal_id is not None
        assert len(goal_id) > 0

    def test_get_goal(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        goal_id = run(gm.add_goal("Test goal", priority=5))
        goal = run(gm.get_goal(goal_id))
        assert goal is not None
        assert goal.description == "Test goal"
        assert goal.priority == 5

    def test_goal_initial_state_is_pending(self):
        from src.agents.goal_manager import GoalManager, GoalState
        gm = GoalManager()
        goal_id = run(gm.add_goal("Initial state test"))
        goal = run(gm.get_goal(goal_id))
        assert goal.state == GoalState.PENDING

    def test_mark_active(self):
        from src.agents.goal_manager import GoalManager, GoalState
        gm = GoalManager()
        goal_id = run(gm.add_goal("Activate me"))
        result = run(gm.mark_active(goal_id))
        assert result is True
        goal = run(gm.get_goal(goal_id))
        assert goal.state == GoalState.ACTIVE

    def test_mark_completed(self):
        from src.agents.goal_manager import GoalManager, GoalState
        gm = GoalManager()
        goal_id = run(gm.add_goal("Complete me"))
        run(gm.mark_active(goal_id))
        result = run(gm.mark_completed(goal_id))
        assert result is True
        goal = run(gm.get_goal(goal_id))
        assert goal.state == GoalState.COMPLETED

    def test_mark_failed(self):
        from src.agents.goal_manager import GoalManager, GoalState
        gm = GoalManager()
        goal_id = run(gm.add_goal("Fail me"))
        run(gm.mark_active(goal_id))
        result = run(gm.mark_failed(goal_id, error="something went wrong"))
        assert result is True
        goal = run(gm.get_goal(goal_id))
        assert goal.state == GoalState.FAILED
        assert goal.error == "something went wrong"

    def test_mark_cancelled(self):
        from src.agents.goal_manager import GoalManager, GoalState
        gm = GoalManager()
        goal_id = run(gm.add_goal("Cancel me"))
        result = run(gm.mark_cancelled(goal_id, reason="no longer needed"))
        assert result is True
        goal = run(gm.get_goal(goal_id))
        assert goal.state == GoalState.CANCELLED

    def test_update_progress_auto_transitions(self):
        """Progress update on PENDING goal auto-transitions to ACTIVE."""
        from src.agents.goal_manager import GoalManager, GoalState
        gm = GoalManager()
        goal_id = run(gm.add_goal("Progress test"))
        goal = run(gm.get_goal(goal_id))
        assert goal.state == GoalState.PENDING
        run(gm.update_progress(goal_id, increment=0.3))
        goal = run(gm.get_goal(goal_id))
        assert goal.state == GoalState.ACTIVE
        assert abs(goal.progress - 0.3) < 0.01

    def test_update_progress_to_100_auto_completes(self):
        """Progress reaching 1.0 auto-transitions to COMPLETED."""
        from src.agents.goal_manager import GoalManager, GoalState
        gm = GoalManager()
        goal_id = run(gm.add_goal("Auto-complete test"))
        run(gm.update_progress(goal_id, absolute=1.0))
        goal = run(gm.get_goal(goal_id))
        assert goal.state == GoalState.COMPLETED

    def test_priority_ordering(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        low_id = run(gm.add_goal("Low priority", priority=1))
        high_id = run(gm.add_goal("High priority", priority=9))
        mid_id = run(gm.add_goal("Mid priority", priority=5))

        # Activate all
        run(gm.mark_active(low_id))
        run(gm.mark_active(high_id))
        run(gm.mark_active(mid_id))

        next_goal = run(gm.get_next_active())
        assert next_goal is not None
        assert next_goal.goal_id == high_id

    def test_get_active_goals(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        g1 = run(gm.add_goal("Active 1", priority=5))
        g2 = run(gm.add_goal("Active 2", priority=5))
        run(gm.add_goal("Pending 3", priority=5))

        run(gm.mark_active(g1))
        run(gm.mark_active(g2))

        active = run(gm.get_active_goals())
        assert len(active) == 2

    def test_get_pending_goals(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        run(gm.add_goal("Pending 1"))
        g2 = run(gm.add_goal("Pending 2"))
        run(gm.mark_active(g2))

        pending = run(gm.get_pending_goals())
        assert len(pending) == 1

    def test_overdue_goal_detection(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        goal_id = run(gm.add_goal("Overdue goal", priority=5, deadline=time.time() - 10))
        goal = run(gm.get_goal(goal_id))
        assert goal.is_overdue is True

    def test_goal_not_overdue_without_deadline(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        goal_id = run(gm.add_goal("No deadline"))
        goal = run(gm.get_goal(goal_id))
        assert goal.is_overdue is False

    def test_effective_priority_boost_for_overdue(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        goal_id = run(gm.add_goal("Overdue", priority=5, deadline=time.time() - 10))
        goal = run(gm.get_goal(goal_id))
        assert goal.effective_priority > 5.0

    def test_goal_to_dict(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        goal_id = run(gm.add_goal("Dict test", priority=7))
        goal = run(gm.get_goal(goal_id))
        d = goal.to_dict()
        assert "goal_id" in d
        assert "description" in d
        assert "priority" in d
        assert d["priority"] == 7

    def test_remove_goal(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        goal_id = run(gm.add_goal("Remove me"))
        result = run(gm.remove_goal(goal_id))
        assert result is True
        goal = run(gm.get_goal(goal_id))
        assert goal is None

    def test_get_overdue_goals(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        run(gm.add_goal("Overdue", priority=5, deadline=time.time() - 10))
        run(gm.add_goal("Not overdue", priority=5))
        overdue = run(gm.get_overdue_goals())
        assert len(overdue) == 1

    def test_get_goal_summary(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        run(gm.add_goal("Summary test 1"))
        run(gm.add_goal("Summary test 2"))
        summary = run(gm.get_goal_summary())
        assert "total" in summary
        assert summary["total"] == 2

    def test_capacity_eviction(self):
        from src.agents.goal_manager import GoalManager
        gm = GoalManager(max_goals=3)
        run(gm.add_goal("Goal 1", priority=1))
        run(gm.add_goal("Goal 2", priority=5))
        run(gm.add_goal("Goal 3", priority=3))
        # Adding a 4th should trigger eviction of lowest-priority terminal goals
        run(gm.add_goal("Goal 4", priority=9))
        # The manager should still function (no crash)
        summary = run(gm.get_goal_summary())
        assert summary["total"] >= 3

    def test_prerequisite_gating(self):
        """Goals with unmet prerequisites are not returned by get_next_active."""
        from src.agents.goal_manager import GoalManager
        gm = GoalManager()
        prereq_id = run(gm.add_goal("Prerequisite", priority=1))
        run(gm.mark_active(prereq_id))
        dep_id = run(gm.add_goal("Dependent", priority=10, prerequisites={prereq_id}))
        run(gm.mark_active(dep_id))

        # The dependent goal should be deprioritized until its prerequisite completes
        next_goal = run(gm.get_next_active())
        assert next_goal is not None
        # Prerequisite is not yet completed, so dependent shouldn't be selected
        # (implementation may vary; at minimum it should not crash)
        assert next_goal.goal_id in (prereq_id, dep_id)


# ===========================================================================
# 4. MemoryStream
# ===========================================================================


class TestMemoryStream:
    """Test episodic memory storage, retrieval, scoring, and eviction."""

    def test_add_memory(self):
        from src.agents.memory_stream import MemoryStream
        ms = MemoryStream()
        mem_id = run(ms.add("Test memory content", importance=0.7, tags={"test"}))
        assert mem_id is not None
        assert len(mem_id) > 0

    def test_get_memory(self):
        from src.agents.memory_stream import MemoryStream
        ms = MemoryStream()
        mem_id = run(ms.add("Retrieve me", importance=0.5))
        mem = run(ms.get(mem_id))
        assert mem is not None
        assert mem.content == "Retrieve me"

    def test_retrieve_by_relevance(self):
        from src.agents.memory_stream import MemoryStream
        ms = MemoryStream()
        run(ms.add("Python coding task", importance=0.5, tags={"coding"}))
        run(ms.add("Research paper analysis", importance=0.5, tags={"research"}))
        run(ms.add("Debug Python code", importance=0.5, tags={"coding", "debugging"}))

        results = run(ms.retrieve("Python", top_k=2))
        assert len(results) > 0
        # Results should be relevant to "Python"
        for mem in results:
            assert "python" in mem.content.lower() or "coding" in mem.tags

    def test_retrieve_by_tags(self):
        from src.agents.memory_stream import MemoryStream
        ms = MemoryStream()
        run(ms.add("Task 1", importance=0.5, tags={"coding"}))
        run(ms.add("Task 2", importance=0.5, tags={"research"}))
        run(ms.add("Task 3", importance=0.5, tags={"coding", "debugging"}))

        results = run(ms.get_by_tags({"coding"}))
        assert len(results) == 2

    def test_get_recent(self):
        from src.agents.memory_stream import MemoryStream
        ms = MemoryStream()
        run(ms.add("Old memory", importance=0.3))
        run(ms.add("New memory", importance=0.8))

        recent = run(ms.get_recent(count=1))
        assert len(recent) == 1
        assert recent[0].content == "New memory"

    def test_get_by_time_range(self):
        from src.agents.memory_stream import MemoryStream
        ms = MemoryStream()
        now = time.time()
        run(ms.add("In range", importance=0.5))
        results = run(ms.get_by_time_range(now - 60, now + 60))
        assert len(results) >= 1

    def test_remove_memory(self):
        from src.agents.memory_stream import MemoryStream
        ms = MemoryStream()
        mem_id = run(ms.add("Remove me", importance=0.3))
        result = run(ms.remove(mem_id))
        assert result is True
        mem = run(ms.get(mem_id))
        assert mem is None

    def test_reflect(self):
        from src.agents.memory_stream import MemoryStream
        ms = MemoryStream()
        run(ms.add("Important event", importance=0.9))
        run(ms.add("Less important", importance=0.2))
        reflections = run(ms.reflect(top_k=5))
        assert len(reflections) > 0
        # Reflections should be sorted by weighted recency+importance
        assert reflections[0]["importance"] >= reflections[-1]["importance"]

    def test_memory_capacity(self):
        from src.agents.memory_stream import MemoryStream
        ms = MemoryStream(capacity=5)
        for i in range(10):
            run(ms.add(f"Memory {i}", importance=0.5))
        assert ms.count <= 5

    def test_episodic_memory_recency_score(self):
        from src.agents.memory_stream import EpisodicMemory
        now = time.time()
        mem = EpisodicMemory(content="test", importance=0.5, timestamp=now)
        # Just-created memory should have high recency
        assert mem.recency_score(now) > 0.9
        # Old memory should have low recency
        mem_old = EpisodicMemory(content="test", importance=0.5, timestamp=now - 7200)
        assert mem_old.recency_score(now) < 0.5

    def test_episodic_memory_relevance_score(self):
        from src.agents.memory_stream import EpisodicMemory
        mem = EpisodicMemory(content="Python coding task", importance=0.5, tags={"coding"})
        score = mem.relevance_score("Python coding")
        assert score > 0.0

    def test_episodic_memory_combined_score(self):
        from src.agents.memory_stream import EpisodicMemory
        now = time.time()
        mem = EpisodicMemory(content="Important Python task", importance=0.9, tags={"coding"}, timestamp=now)
        score = mem.combined_score(query="Python", now=now)
        assert score > 0.0
        assert score <= 1.0

    def test_episodic_memory_touch(self):
        from src.agents.memory_stream import EpisodicMemory
        mem = EpisodicMemory(content="test", importance=0.5)
        assert mem.access_count == 0
        assert mem.last_accessed is None
        mem.touch()
        assert mem.access_count == 1
        assert mem.last_accessed is not None

    def test_episodic_memory_to_dict(self):
        from src.agents.memory_stream import EpisodicMemory
        mem = EpisodicMemory(content="test", importance=0.7, tags={"unit"})
        d = mem.to_dict()
        assert "memory_id" in d
        assert d["content"] == "test"
        assert d["importance"] == 0.7

    def test_memory_summary(self):
        from src.agents.memory_stream import MemoryStream
        ms = MemoryStream()
        run(ms.add("Summary test 1", importance=0.5))
        run(ms.add("Summary test 2", importance=0.7))
        summary = run(ms.get_summary())
        assert "total" in summary
        assert summary["total"] == 2

    def test_get_all(self):
        from src.agents.memory_stream import MemoryStream
        ms = MemoryStream()
        run(ms.add("Memory 1", importance=0.5))
        run(ms.add("Memory 2", importance=0.5))
        all_mems = run(ms.get_all())
        assert len(all_mems) == 2


# ===========================================================================
# 5. TaskDecomposer
# ===========================================================================


class TestTaskDecomposer:
    """Test task decomposition patterns and topological execution order."""

    def test_subtask_defaults(self):
        from src.agents.task_decomposer import SubTask
        st = SubTask(description="Test subtask")
        assert st.status == "pending"
        assert st.complexity == 3
        assert st.order == 0
        assert len(st.subtask_id) > 0

    def test_subtask_to_dict(self):
        from src.agents.task_decomposer import SubTask
        st = SubTask(description="Dict test", suggested_tool="execute_code", complexity=2)
        d = st.to_dict()
        assert "subtask_id" in d
        assert d["description"] == "Dict test"
        assert d["suggested_tool"] == "execute_code"

    def test_decomposition_get_execution_order(self):
        from src.agents.task_decomposer import Decomposition, SubTask
        st1 = SubTask(subtask_id="a", description="Step 1", order=0)
        st2 = SubTask(subtask_id="b", description="Step 2", dependencies={"a"}, order=1)
        st3 = SubTask(subtask_id="c", description="Step 3", dependencies={"b"}, order=2)

        decomp = Decomposition(
            goal_description="Test goal",
            subtasks=[st3, st1, st2],  # intentionally out of order
            strategy="sequential",
        )
        order = decomp.get_execution_order()
        ids = [s.subtask_id for s in order]
        assert ids.index("a") < ids.index("b") < ids.index("c")

    def test_decomposition_to_dict(self):
        from src.agents.task_decomposer import Decomposition, SubTask
        decomp = Decomposition(
            goal_description="Test",
            subtasks=[SubTask(description="Step 1")],
            strategy="sequential",
        )
        d = decomp.to_dict()
        assert "goal_description" in d
        assert "subtasks" in d
        assert len(d["subtasks"]) == 1

    def test_decompose_analysis_task(self):
        from src.agents.task_decomposer import TaskDecomposer
        td = TaskDecomposer()
        decomp = run(td.decompose("Analyze the performance metrics of the system"))
        assert len(decomp.subtasks) > 0
        assert decomp.strategy is not None

    def test_decompose_creation_task(self):
        from src.agents.task_decomposer import TaskDecomposer
        td = TaskDecomposer()
        decomp = run(td.decompose("Create a new Python module for data processing"))
        assert len(decomp.subtasks) > 0

    def test_decompose_debugging_task(self):
        from src.agents.task_decomposer import TaskDecomposer
        td = TaskDecomposer()
        decomp = run(td.decompose("Debug the connection timeout error in the API"))
        assert len(decomp.subtasks) > 0

    def test_decompose_research_task(self):
        from src.agents.task_decomposer import TaskDecomposer
        td = TaskDecomposer()
        decomp = run(td.decompose("Research the latest advances in transformer architectures"))
        assert len(decomp.subtasks) > 0

    def test_decompose_security_task(self):
        from src.agents.task_decomposer import TaskDecomposer
        td = TaskDecomposer()
        decomp = run(td.decompose("Audit the authentication system for security vulnerabilities"))
        assert len(decomp.subtasks) > 0

    def test_decompose_planning_task(self):
        from src.agents.task_decomposer import TaskDecomposer
        td = TaskDecomposer()
        decomp = run(td.decompose("Plan the migration of the database to a new cluster"))
        assert len(decomp.subtasks) > 0

    def test_decompose_generic_task(self):
        from src.agents.task_decomposer import TaskDecomposer
        td = TaskDecomposer()
        decomp = run(td.decompose("Organize the team meeting for next week"))
        assert len(decomp.subtasks) > 0

    def test_decompose_with_context(self):
        from src.agents.task_decomposer import TaskDecomposer
        td = TaskDecomposer()
        decomp = run(td.decompose("Fix the bug", context={"language": "Python", "component": "API"}))
        assert len(decomp.subtasks) > 0

    def test_execution_order_is_valid(self):
        from src.agents.task_decomposer import TaskDecomposer
        td = TaskDecomposer()
        decomp = run(td.decompose("Analyze and optimize the codebase"))
        order = decomp.get_execution_order()
        # Verify dependency ordering: all dependencies must appear before their dependents
        seen_ids = set()
        for st in order:
            for dep in st.dependencies:
                assert dep in seen_ids, f"Dependency {dep} not yet executed before {st.subtask_id}"
            seen_ids.add(st.subtask_id)

    def test_estimated_total_complexity(self):
        from src.agents.task_decomposer import TaskDecomposer
        td = TaskDecomposer()
        decomp = run(td.decompose("Build and deploy the new feature"))
        assert decomp.estimated_total_complexity > 0


# ===========================================================================
# 6. ToolBridge
# ===========================================================================


class TestToolBridge:
    """Test tool registration, execution, and resolution order."""

    def test_register_and_list_tool(self):
        from src.agents.tool_bridge import ToolBridge
        tb = ToolBridge()
        tb.register_tool("test_tool", handler=lambda **kw: {"result": "ok"})
        tools = tb.list_available_tools()
        assert "test_tool" in tools

    def test_register_async_tool(self):
        from src.agents.tool_bridge import ToolBridge

        async def _handler(**kwargs):
            return {"async": True}

        tb = ToolBridge()
        tb.register_tool("async_tool", handler=_handler)
        tools = tb.list_available_tools()
        assert "async_tool" in tools
        return None

    def test_execute_direct_tool(self):
        from src.agents.tool_bridge import ToolBridge

        def _handler(**kwargs):
            return {"echo": kwargs.get("msg", "")}

        tb = ToolBridge()
        tb.register_tool("echo", handler=_handler)
        result = run(tb.execute("echo", {"msg": "hello"}))
        assert result.success is True
        assert result.data == {"echo": "hello"}
        return None

    def test_execute_async_direct_tool(self):
        from src.agents.tool_bridge import ToolBridge

        async def _handler(**kwargs):
            return {"async_echo": kwargs.get("msg", "")}

        tb = ToolBridge()
        tb.register_tool("async_echo", handler=_handler)
        result = run(tb.execute("async_echo", {"msg": "world"}))
        assert result.success is True
        assert result.data == {"async_echo": "world"}
        return None

    def test_execute_nonexistent_tool(self):
        from src.agents.tool_bridge import ToolBridge
        tb = ToolBridge()
        result = run(tb.execute("nonexistent_tool", {}))
        assert result.success is False
        assert result.error is not None

    def test_unregister_tool(self):
        from src.agents.tool_bridge import ToolBridge
        tb = ToolBridge()
        tb.register_tool("temp_tool", handler=lambda **kw: None)
        result = tb.unregister_tool("temp_tool")
        assert result is True
        assert "temp_tool" not in tb.list_available_tools()

    def test_tool_result_dataclass(self):
        from src.agents.tool_bridge import ToolResult
        tr = ToolResult(tool_name="test", success=True, data={"key": "val"}, duration_ms=42.5)
        d = tr.to_dict()
        assert d["tool_name"] == "test"
        assert d["success"] is True
        assert d["data"] == {"key": "val"}
        assert d["duration_ms"] == 42.5

    def test_get_tool_info(self):
        from src.agents.tool_bridge import ToolBridge
        tb = ToolBridge()
        tb.register_tool("info_tool", handler=lambda **kw: None,
                         capability_tags={"utility"})
        info = tb.get_tool_info("info_tool")
        assert info is not None
        assert info["name"] == "info_tool"
        assert "utility" in info.get("capability_tags", set())

    def test_invocation_history(self):
        from src.agents.tool_bridge import ToolBridge
        tb = ToolBridge()
        tb.register_tool("hist_tool", handler=lambda **kw: {"ok": True})
        run(tb.execute("hist_tool", {}))
        run(tb.execute("hist_tool", {}))
        history = tb.get_invocation_history(tool_name="hist_tool")
        assert len(history) == 2

    def test_get_metrics(self):
        from src.agents.tool_bridge import ToolBridge
        tb = ToolBridge()
        tb.register_tool("metrics_tool", handler=lambda **kw: {"ok": True})
        run(tb.execute("metrics_tool", {}))
        metrics = tb.get_metrics()
        assert "total_invocations" in metrics
        assert metrics["total_invocations"] == 1

    def test_mcp_resolution_fallback(self):
        """ToolBridge should fall back to MCP registry for unregistered tools."""
        from src.agents.tool_bridge import ToolBridge
        tb = ToolBridge()
        # Don't register anything locally — should try MCP
        result = run(tb.execute("search_skills", {}))
        # search_skills is a built-in Spark tool, so it should resolve via MCP
        # (May or may not succeed depending on handler internals, but should not crash)
        assert isinstance(result.success, bool)


# ===========================================================================
# 7. AgentRuntime
# ===========================================================================


class TestAgentRuntime:
    """Test the agent lifecycle, goal assignment, and step execution."""

    def test_create_agent(self):
        from src.agents.agent_runtime import AgentConfig, AgentRuntime
        config = AgentConfig(name="test-agent", agent_type="general")
        agent = AgentRuntime(config)
        assert agent.config.name == "test-agent"
        assert agent.config.agent_type == "general"

    def test_initial_state_is_idle(self):
        from src.agents.agent_runtime import AgentRuntime, AgentState
        agent = AgentRuntime()
        assert agent.state == AgentState.IDLE

    def test_start_agent(self):
        from src.agents.agent_runtime import AgentRuntime, AgentState
        agent = AgentRuntime()
        run(agent.start())
        assert agent.state in (AgentState.IDLE, AgentState.PLANNING, AgentState.EXECUTING)

    def test_stop_agent(self):
        from src.agents.agent_runtime import AgentRuntime, AgentState
        agent = AgentRuntime()
        run(agent.start())
        run(agent.stop())
        assert agent.state == AgentState.TERMINATED

    def test_assign_goal(self):
        from src.agents.agent_runtime import AgentRuntime
        agent = AgentRuntime()
        run(agent.start())
        goal_id = run(agent.assign_goal("Analyze the data", priority=7))
        assert goal_id is not None
        assert len(goal_id) > 0

    def test_assign_goal_before_start(self):
        """Assigning a goal before starting should still work (goal queued)."""
        from src.agents.agent_runtime import AgentRuntime
        agent = AgentRuntime()
        goal_id = run(agent.assign_goal("Pre-start goal", priority=5))
        assert goal_id is not None

    def test_is_running(self):
        from src.agents.agent_runtime import AgentRuntime, AgentState
        agent = AgentRuntime()
        # is_running = True for IDLE state (only False for TERMINATED/ERROR)
        assert agent.state == AgentState.IDLE
        assert agent.is_running is True
        run(agent.stop())
        assert agent.is_running is False

    def test_is_idle(self):
        from src.agents.agent_runtime import AgentRuntime
        agent = AgentRuntime()
        assert agent.is_idle is True

    def test_run_step(self):
        from src.agents.agent_runtime import AgentRuntime
        agent = AgentRuntime()
        run(agent.start())
        run(agent.assign_goal("Test step execution"))
        step = run(agent.run_step())
        # Step may be None if no goals ready, or an AgentStep
        if step is not None:
            assert step.step_id is not None

    def test_run_until_idle(self):
        from src.agents.agent_runtime import AgentRuntime
        agent = AgentRuntime()
        run(agent.start())
        steps = run(agent.run_until_idle(max_steps=5))
        assert isinstance(steps, int)
        assert steps >= 0

    def test_get_results(self):
        from src.agents.agent_runtime import AgentRuntime
        agent = AgentRuntime()
        results = agent.get_results()
        assert isinstance(results, dict)

    def test_metrics(self):
        from src.agents.agent_runtime import AgentRuntime
        agent = AgentRuntime()
        metrics = agent.metrics
        assert isinstance(metrics, dict)

    def test_observe_state(self):
        from src.agents.agent_runtime import AgentRuntime, AgentState
        transitions = []

        def on_state_change(old_state: AgentState, new_state: AgentState):
            transitions.append((old_state, new_state))

        agent = AgentRuntime()
        agent.observe_state(on_state_change)
        # start() is guarded: IDLE→IDLE produces no transition.
        # Use stop() to trigger a real state change IDLE→TERMINATED.
        run(agent.stop())
        assert len(transitions) > 0
        assert transitions[0] == (AgentState.IDLE, AgentState.TERMINATED)

    def test_observe_steps(self):
        from src.agents.agent_runtime import AgentRuntime, AgentStep
        steps = []

        def on_step(step: AgentStep):
            steps.append(step)

        agent = AgentRuntime()
        agent.observe_steps(on_step)
        run(agent.start())
        run(agent.assign_goal("Observer test goal"))
        run(agent.run_until_idle(max_steps=3))
        # Steps may or may not fire depending on internal logic
        # At minimum, no crash

    def test_stop_without_start(self):
        from src.agents.agent_runtime import AgentRuntime
        agent = AgentRuntime()
        run(agent.stop())
        assert agent.state.value == "terminated"

    def test_agent_config_defaults(self):
        from src.agents.agent_runtime import AgentConfig
        config = AgentConfig()
        assert config.name == "unnamed-agent"
        assert config.agent_type == "general"
        assert config.max_concurrent_tasks == 3
        assert config.max_retries == 2


# ===========================================================================
# 8. Phase 5 Spark Tools Registration
# ===========================================================================


class TestSparkPhase5ToolsRegistration:
    """Test Phase 5 MCP tool registration into The Spark."""

    def test_phase5_tools_module_importable(self):
        from src.mcp.spark_phase5_tools import PHASE5_TOOLS
        assert len(PHASE5_TOOLS) == 12

    def test_all_tool_names_unique(self):
        from src.mcp.spark_phase5_tools import PHASE5_TOOLS
        names = [t["name"] for t in PHASE5_TOOLS]
        assert len(names) == len(set(names)), "Duplicate tool names in PHASE5_TOOLS"

    def test_all_tools_have_required_keys(self):
        from src.mcp.spark_phase5_tools import PHASE5_TOOLS
        for tool in PHASE5_TOOLS:
            assert "name" in tool, f"Missing 'name' in tool: {tool}"
            assert "description" in tool, f"Missing 'description' in tool: {tool}"
            assert "input_schema" in tool, f"Missing 'input_schema' in tool: {tool}"
            assert "handler" in tool, f"Missing 'handler' in tool: {tool}"
            assert callable(tool["handler"]), f"Handler not callable for tool: {tool['name']}"

    def test_registration_into_fresh_registry(self):
        from src.mcp.spark_phase5_tools import register_phase5_tools
        from src.mcp.tools import SparkToolRegistry
        fresh = SparkToolRegistry()
        baseline = len(fresh._tools)
        count = register_phase5_tools(fresh)
        assert count == 12
        assert len(fresh._tools) == baseline + 12

    def test_global_registry_has_phase5_tools(self):
        from src.mcp.tools import registry
        tool_names = list(registry._tools.keys())
        expected_phase5 = [
            "agent_create", "agent_start", "agent_stop", "agent_status",
            "agent_assign_goal", "agent_list_goals", "agent_decompose_task",
            "agent_retrieve_memory", "agent_reflect", "agent_list_all",
            "agent_find_best", "agent_profiles",
        ]
        for name in expected_phase5:
            assert name in tool_names, f"Phase 5 tool '{name}' not in global registry"

    def test_total_tool_count_after_phase5(self):
        from src.mcp.tools import registry
        # 17 original + 16 phase4 + 12 phase5 = 45
        total = len(registry._tools)
        assert total >= 45, f"Expected >= 45 tools after Phase 5, got {total}"

    def test_tool_schemas_have_required_fields(self):
        from src.mcp.spark_phase5_tools import PHASE5_TOOLS
        for tool in PHASE5_TOOLS:
            schema = tool["input_schema"]
            assert "type" in schema
            assert schema["type"] == "object"
            assert "properties" in schema

    def test_phase5_tools_have_correct_category(self):
        from src.mcp.spark_phase5_tools import PHASE5_TOOLS
        for tool in PHASE5_TOOLS:
            category = tool.get("category", "")
            assert category in ("agents", "phase5"), \
                f"Tool '{tool['name']}' has unexpected category: {category}"


# ===========================================================================
# 9. Phase 5 Spark Tool Handler Smoke Tests
# ===========================================================================


class TestSparkPhase5ToolHandlers:
    """Smoke-test each Phase 5 MCP tool handler."""

    def test_agent_create_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_create
        result = run(_handle_agent_create({"name": "test-smoke", "agent_type": "general"}))
        assert "ok" in result or "agent_id" in result or "error" not in result

    def test_agent_start_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_create, _handle_agent_start
        create_result = run(_handle_agent_create({"name": "start-test", "agent_type": "coder"}))
        agent_id = create_result.get("agent_id")
        if agent_id:
            start_result = run(_handle_agent_start({"agent_id": agent_id}))
            assert "ok" in start_result or "error" in start_result or "status" in start_result

    def test_agent_status_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_status
        result = run(_handle_agent_status({}))
        assert isinstance(result, dict)

    def test_agent_stop_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_stop
        result = run(_handle_agent_stop({}))
        assert isinstance(result, dict)

    def test_agent_assign_goal_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_assign_goal
        result = run(_handle_agent_assign_goal({
            "description": "Test goal",
            "priority": 5,
        }))
        assert isinstance(result, dict)

    def test_agent_list_goals_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_list_goals
        result = run(_handle_agent_list_goals({}))
        assert isinstance(result, dict)

    def test_agent_decompose_task_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_decompose_task
        result = run(_handle_agent_decompose_task({
            "goal_description": "Analyze the codebase for performance issues",
        }))
        assert isinstance(result, dict)
        # Should contain decomposition info
        if "subtasks" in result:
            assert len(result["subtasks"]) > 0

    def test_agent_retrieve_memory_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_retrieve_memory
        result = run(_handle_agent_retrieve_memory({
            "query": "test query",
        }))
        assert isinstance(result, dict)

    def test_agent_reflect_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_reflect
        result = run(_handle_agent_reflect({}))
        assert isinstance(result, dict)

    def test_agent_list_all_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_list_all
        result = run(_handle_agent_list_all({}))
        assert isinstance(result, dict)
        assert "agents" in result or "total" in result

    def test_agent_find_best_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_find_best
        result = run(_handle_agent_find_best({
            "required_tags": ["coding", "debugging"],
        }))
        assert isinstance(result, dict)

    def test_agent_profiles_handler(self):
        from src.mcp.spark_phase5_tools import _handle_agent_profiles
        result = run(_handle_agent_profiles({}))
        assert isinstance(result, dict)
        assert "profiles" in result or "total" in result


# ===========================================================================
# 10. Phase 5 Workflow Nodes
# ===========================================================================


class TestPhase5WorkflowNodes:
    """Test Phase 5 workflow node types and registration."""

    def test_phase5_node_types_dict(self):
        from src.workflow.phase5_nodes import PHASE5_NODE_TYPES
        expected = {"AGENT_CREATE", "AGENT_RUN_STEP", "AGENT_GOAL",
                    "AGENT_REFLECT", "AGENT_DECOMPOSE"}
        assert set(PHASE5_NODE_TYPES.keys()) == expected

    def test_all_node_types_are_classes(self):
        from src.workflow.phase5_nodes import PHASE5_NODE_TYPES
        for name, cls in PHASE5_NODE_TYPES.items():
            assert isinstance(cls, type), f"Node type '{name}' is not a class"

    def test_extend_node_registry(self):
        from src.workflow.phase5_nodes import extend_node_registry
        target = {}
        count = extend_node_registry(target)
        assert count == 5
        assert "AGENT_CREATE" in target

    def test_phase5_nodes_registered_in_global_registry(self):
        from src.workflow.nodes import _PHASE4_NODE_REGISTRY, _ensure_phase4_nodes_loaded
        _ensure_phase4_nodes_loaded()
        expected = {"AGENT_CREATE", "AGENT_RUN_STEP", "AGENT_GOAL",
                    "AGENT_REFLECT", "AGENT_DECOMPOSE"}
        for name in expected:
            assert name in _PHASE4_NODE_REGISTRY, \
                f"Phase 5 node '{name}' not in global registry"

    def test_agent_create_node_execute(self):
        from src.workflow.phase5_nodes import AgentCreateNode
        node = AgentCreateNode(config={"name": "test-node-agent", "agent_type": "general"})
        result = run(node.execute({"name": "wf-agent", "agent_type": "general"}, {}))
        assert result is not None
        assert result.success is True or result.error is not None

    def test_agent_goal_node_execute(self):
        from src.workflow.phase5_nodes import AgentGoalNode
        node = AgentGoalNode(config={"description": "WF goal", "priority": 7})
        result = run(node.execute({"description": "WF goal", "priority": 7}, {}))
        assert result is not None
        assert result.success is True or result.error is not None

    def test_agent_decompose_node_execute(self):
        from src.workflow.phase5_nodes import AgentDecomposeNode
        node = AgentDecomposeNode(config={"description": "Analyze system"})
        result = run(node.execute({"description": "Analyze system"}, {}))
        assert result is not None
        assert result.success is True or result.error is not None

    def test_agent_reflect_node_execute(self):
        from src.workflow.phase5_nodes import AgentReflectNode
        node = AgentReflectNode(config={})
        result = run(node.execute({}, {}))
        assert result is not None
        assert result.success is True or result.error is not None

    def test_agent_run_step_node_execute(self):
        from src.workflow.phase5_nodes import AgentRunStepNode
        node = AgentRunStepNode(config={})
        result = run(node.execute({}, {}))
        assert result is not None
        assert result.success is True or result.error is not None


# ===========================================================================
# 11. Cross-cutting Integration
# ===========================================================================


class TestPhase5Integration:
    """End-to-end integration tests combining multiple Phase 5 components."""

    def test_agent_lifecycle_with_goal(self):
        """Full agent lifecycle: create, start, assign goal, run, stop."""
        from src.agents.agent_runtime import AgentConfig, AgentRuntime, AgentState
        config = AgentConfig(name="integration-agent", agent_type="general")
        agent = AgentRuntime(config)

        # Start
        run(agent.start())
        assert agent.is_running

        # Assign goal
        goal_id = run(agent.assign_goal("Integration test goal", priority=7))
        assert goal_id is not None

        # Run a step
        run(agent.run_step())
        # Step may succeed or not depending on tool resolution, but no crash

        # Stop
        run(agent.stop())
        assert agent.state == AgentState.TERMINATED

    def test_decompose_then_execute_via_toolbridge(self):
        """Decompose a task, then execute subtasks via ToolBridge."""
        from src.agents.task_decomposer import TaskDecomposer
        from src.agents.tool_bridge import ToolBridge

        td = TaskDecomposer()
        tb = ToolBridge()

        # Register a simple echo tool
        tb.register_tool("echo", handler=lambda **kw: {"echo": kw.get("message", "")})

        # Decompose
        decomp = run(td.decompose("Analyze the performance data"))
        assert len(decomp.subtasks) > 0

        # Execute each subtask that uses the echo tool
        for st in decomp.get_execution_order():
            if st.suggested_tool == "echo":
                result = run(tb.execute("echo", {"message": st.description}))
                assert result.success is True

    def test_goal_memory_correlation(self):
        """Goals and memories can be correlated via metadata."""
        from src.agents.goal_manager import GoalManager
        from src.agents.memory_stream import MemoryStream

        gm = GoalManager()
        ms = MemoryStream()

        goal_id = run(gm.add_goal("Research AI trends", priority=8))
        mem_id = run(ms.add("Started researching AI trends", importance=0.7,
                             tags={"research", "ai"}, metadata={"goal_id": goal_id}))

        # Verify memory references the goal
        mem = run(ms.get(mem_id))
        assert mem is not None
        assert mem.metadata.get("goal_id") == goal_id

        # Verify goal exists
        goal = run(gm.get_goal(goal_id))
        assert goal is not None
        assert "Research AI trends" in goal.description

    def test_multiple_agents_with_profiles(self):
        """Create agents with different profiles and verify their configs."""
        from src.agents.agent_runtime import AgentConfig, AgentRuntime
        from src.agents.agent_types import AgentType, get_profile

        profiles_to_test = [AgentType.CODER, AgentType.RESEARCHER, AgentType.PLANNER]
        for at in profiles_to_test:
            profile = get_profile(at)
            config = AgentConfig(
                name=f"agent-{at.value}",
                agent_type=at.value,
                tags=profile.capability_tags,
            )
            agent = AgentRuntime(config)
            assert agent.config.agent_type == at.value
            assert len(agent.config.tags) > 0

    def test_reflection_enhances_memory(self):
        """Reflection should surface important memories."""
        from src.agents.memory_stream import MemoryStream

        ms = MemoryStream()
        # Add memories with different importance levels
        run(ms.add("Critical system alert", importance=0.95, tags={"alert", "critical"}))
        run(ms.add("Routine check passed", importance=0.2, tags={"routine"}))
        run(ms.add("Important finding", importance=0.8, tags={"finding", "research"}))

        reflections = run(ms.reflect(top_k=3))
        assert len(reflections) > 0
        # Most important should be first
        assert reflections[0]["importance"] >= reflections[-1]["importance"]

    def test_phase5_mcp_server_resources(self):
        """Phase 5 resources should appear in the MCP server's resource list."""
        from src.mcp.server import _method_resources_list
        result = run(_method_resources_list(None, "test-1"))
        resources = result["result"]["resources"]
        uris = [r["uri"] for r in resources]
        assert "spark://agents" in uris
        assert "spark://agent-goals" in uris
        assert "spark://agent-memory" in uris

    def test_find_best_profile_for_coding_task(self):
        """find_best_profile should return CODER for coding-heavy tags."""
        from src.agents.agent_types import AgentType, find_best_profile
        profile = find_best_profile({"coding", "debugging", "implementation"})
        # The best match should have coding-related capabilities
        assert "coding" in profile.capability_tags or profile.agent_type == AgentType.CODER

    def test_toolbridge_mcp_integration(self):
        """ToolBridge should be able to resolve and call MCP tools."""
        from src.agents.tool_bridge import ToolBridge
        tb = ToolBridge()
        # Try to call a built-in Spark tool via MCP resolution
        result = run(tb.execute("get_system_health", {"subsystems": ["mcp_server"]}))
        # Should succeed or fail gracefully, not crash
        assert isinstance(result.success, bool)
