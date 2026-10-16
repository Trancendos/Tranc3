# Town Hall Operating Procedure

**Status**: Active  
**Location**: The Town Hall (CranBania + `src/townhall/`)  
**Related**: `docs/governance/SOURCE-OF-TRUTH-AND-WORK-FLOW.md`, Magna Carta, The Library

---

## 1. Purpose

This procedure makes work on the Trancendos platform **visible, governed, and durable**.

It ensures that:
- Significant work is routed through The Town Hall / CranBania
- Every item has a clear Location owner, authority, reason, and solution pack
- Knowledge does not live only in AI session files (CLAUDE.md or similar)
- Magna Carta rules and the escalation FSM are respected
- Completed work leaves a record in (or cross-referenced from) The Library

---

## 2. Core Principles

1. **No invisible work** — If it matters, it appears on a CranBania / Town Hall board.
2. **One routing decision** — Location ownership is a Town Hall decision, recorded in the Backlog Routing Register. It is never a private AI choice.
3. **Separation of concerns**:
   - Evidence gathering is deterministic.
   - Routing judgement is a distinct step.
   - Policy / invariant checks cannot be overridden by a model.
4. **Durable records** — Outcomes and key decisions land in The Library or are explicitly cross-referenced from it.
5. **Smarter, not harder** — Prefer the existing CranBania + Town Hall + Library path over creating new AI-private to-do systems.

---

## 3. Required Fields for Every Routed Item

When an item is submitted to the Backlog Routing Register (`/townhall/routing` or CranBania equivalent) it must contain:

| Field | Description |
|-------|-------------|
| `item_id` | Stable identifier (e.g. TH-4) |
| `title` | Clear, concise title |
| `location` | One of the 43 platform Locations |
| `authority` | Named authority / Lead AI or role for that Location |
| `reason` | Written justification for the routing decision |
| `solution_pack` | Link or reference to architecture, runbook, or acceptance criteria |
| `priority` | P0 / P1 / P2 (or equivalent) |
| `acceptance_criteria` | What “done” looks like (list) |

Items that lack a valid Location or solution pack must remain `_unrouted_`. The count of unrouted items is a queue the Town Hall owes an answer to.

---

## 4. Recommended Kanban Columns (CranBania)

Use columns that reflect real agent and human work states:

1. **Backlog** — Defined but not yet ready
2. **Ready** — Fully specified, routed, and unblocked
3. **In Progress** — Actively being worked
4. **Blocked** — Cannot proceed (mandatory reason required)
5. **Review** — Awaiting verification or approval
6. **Done** — Acceptance criteria met; record handed to The Library where appropriate

**Blocked** is the most important column for agent work. Every blocked item must carry an explicit reason.

---

## 5. Autonomy Levels (Guidance)

| Level | Name | Behaviour |
|-------|------|-----------|
| L1 | Assist | AI recommends; human acts |
| L2 | Approve | AI prepares; human approves each consequential action |
| L3 | Supervise | AI acts within limits and is monitored |
| L4 | Autonomous | AI acts independently within strict policy bounds |
| L5 | Adaptive | AI may improve within controlled, governed boundaries |

Most new or high-impact work should start at L1–L2 until the Location and solution pack are proven.

---

## 6. Handling of AI Session Files (CLAUDE.md etc.)

- CLAUDE.md and similar files are **temporary working guidance only**.
- They are not the backlog, the constitution, or the knowledge base.
- Any durable fact discovered while using them must be written into Magna Carta, Town Hall, or The Library.
- See the non-authoritative header now present on CLAUDE.md and `docs/governance/SOURCE-OF-TRUTH-AND-WORK-FLOW.md`.

---

## 7. Daily / Periodic Hygiene

A short regular review (even 5–10 minutes) should check:

- Items stuck in **In Progress** longer than 2× their estimated duration
- Items in **Blocked** without a clear next action
- Count of `_unrouted_` items
- Whether completed items have left a Library record or cross-reference

---

## 8. Relationship to Other Systems

- **Magna Carta** — Supplies the non-negotiable rules that routing and execution must respect.
- **Escalation FSM** — Continues to gate Tier-4 and higher-risk actions.
- **The Library** — Receives durable knowledge and runbooks produced by completed work.
- **The Observatory** — Receives audit events (including `townhall.item.routed`).
- **CranBania** — The visible Kanban and operational surface of The Town Hall.

---

## 9. Success Criteria for This Procedure

- Significant work is visible on CranBania / Town Hall boards.
- Every routed item has Location, authority, reason, and solution pack.
- Unrouted count is actively managed rather than ignored.
- CLAUDE.md and similar files are no longer treated as the primary source of truth.
- Completed work leaves a trace in The Library.

---

## 10. Version

- Introduced as part of v0.9.0 Resilience & Adaptive Intelligence work.
- Owned by The Town Hall (Tristuran) with support from The Library and Magna Carta maintainers.
