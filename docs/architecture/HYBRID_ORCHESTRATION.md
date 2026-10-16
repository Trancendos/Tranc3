# Hybrid Agent Orchestration Architecture

**Status**: Design for v0.9.0 MVP (aligned with existing codebase)  
**Location**: Builds on `src/agents/`

---

## 1. Important Alignment Note

TRANC3 already has a mature agent system:

| Existing Component | File | Role |
|--------------------|------|------|
| `AgentOrchestrator` | `src/agents/orchestrator.py` | Task queue, SQLite persistence, governance FSM gating |
| `AgentType` / `AgentProfile` | `src/agents/agent_types.py` | Specialist profiles (GENERAL, RESEARCHER, CODER, PLANNER, ANALYZER, ORCHESTRATOR, GUARDIAN) |
| Goal management | `src/agents/goal_manager.py` | Goal tracking |
| Task decomposition | `src/agents/task_decomposer.py` | Breaking goals into subtasks |
| Memory stream | `src/agents/memory_stream.py` | Episodic memory |
| Tool bridge | `src/agents/tool_bridge.py` | MCP / tool integration |
| Runtime | `src/agents/agent_runtime.py` | Agent execution runtime |

**The hybrid design for v0.9.0 does not replace these components.**  
It evolves them by adding clearer autonomy (accept/decline + short-lived helper roles) and explicit re-planning on staleness/events, while keeping the existing governance, persistence and profile systems.

---

## 2. Design Goals (Unchanged)

- Keep a **thin coordinating layer** that owns high-level planning and final responsibility.
- Give specialist agents **real autonomy** (accept / decline / invent short-lived helper roles).
- Trigger re-planning on **events or observation staleness** rather than continuous re-reasoning.
- Maintain a full **routing / audit path** for every decision.
- Continue to respect the existing AI Governance Constitution escalation FSM.

---

## 3. How the Hybrid Layer Maps to Existing Code

```
User / External Goal
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│     Existing + Extended Coordinating Layer                    │
│  • AgentOrchestrator (task queue + governance + persistence)  │
│  • GoalManager + TaskDecomposer (planning)                    │
│  • New: accept/decline + helper-role invention + staleness    │
└──────────────────────────────────────────────────────────┴──────────────────────────────────────────────────────────┐
             │                               │
             ▼                               ▼
┌───────────────────────────┐   ┌───────────────────────────┐
│  Specialist Agents             │   │  Existing Workers / MCP     │
│  (AgentProfile + Runtime)      │   │  Tool Clusters              │
│  • can accept / decline        │   │  • via tool_bridge           │
│  • invent short-lived helpers  │   │                            │
│  • reflect (already present)   │   │                            │
└───────────────────────────┴──────────────────────────────────────────────────────────┐
                             │
                             ▼
              Reflection + Re-planning on staleness / events
              (extends existing reflection_enabled flag)
```

---

## 4. Evolutionary Interfaces (src/agents/interfaces.py)

The file `src/agents/interfaces.py` introduced in this branch defines clean abstract contracts.  
These are **not** a competing system. They are intended to:

- Provide a stable, well-typed surface for the hybrid behaviours (accept/decline, helper roles, routing path).
- Be implemented by (or adapted onto) the existing `AgentOrchestrator` and agent runtimes.
- Avoid forcing a rewrite of the governance-aware, SQLite-persisted task queue.

Over time the concrete `AgentOrchestrator` can grow to satisfy the richer `Orchestrator` protocol, and agent wrappers can satisfy the `Agent` protocol, without breaking current callers.

---

## 5. Implementation Guidance for v0.9.0 MVP

1. **Do not replace** `AgentOrchestrator` or `AgentProfile`.
2. Extend the existing task model with optional fields for:
   - explicit accept/decline decisions
   - short-lived helper role metadata
   - richer routing_path / audit trail
3. Add a lightweight staleness / event-triggered re-plan hook that calls back into `GoalManager` + `TaskDecomposer`.
4. Keep the governance FSM gating exactly as it is today.
5. Use the existing `AgentType.ORCHESTRATOR` and `AgentType.PLANNER` profiles as the natural home for coordinating behaviour.

---

## 6. Success Criteria (aligned)

- [ ] Hybrid behaviours (accept/decline + helper roles + staleness re-plan) work on top of the current `AgentOrchestrator`.
- [ ] No parallel task queue or competing persistence layer is introduced.
- [ ] Existing governance checks continue to function.
- [ ] Full routing / decision path is available for audit.
- [ ] At least one multi-step goal can be completed using the extended hybrid flow.
