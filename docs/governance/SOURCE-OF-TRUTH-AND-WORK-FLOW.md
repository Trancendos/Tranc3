# Source of Truth & Work Flow (Action Plan)

**Status**: Active guidance for v0.9.0 and beyond  
**Purpose**: Stop AI-specific files (CLAUDE.md and similar) from becoming the primary source of truth. Route all durable knowledge and work through the proper platform locations.

---

## 1. The Problem We Are Solving

CLAUDE.md (and any equivalent AI-specific guidance files) have grown into large, living documents that many agents treat as the main reference. This creates:

- Duplication of knowledge that should live in Magna Carta, Town Hall, or The Library
- AI-specific to-do lists that are invisible to the rest of the platform
- Drift between what an AI "knows" and what the governed systems record
- Repeated mistakes because work is not flowing through CranBania / Town Hall Kanban and The Library

**Principle**: Smarter, not harder. One governed flow, not many private AI notebooks.

---

## 2. Canonical Sources of Truth (in priority order)

| Rank | Location | What belongs here | Owner / Mechanism |
|------|----------|-------------------|-------------------|
| 1 | **Magna Carta** (`compliance/magna-carta/`) | Constitutional rules, rights, non-negotiable governance | Compliance framework |
| 2 | **The Town Hall** (CranBania + `src/townhall/`) | Decisions, routing of work, Kanban / ITSM / PRINCE2 flow, authority records | Town Hall + CranBania boards |
| 3 | **The Library** (`src/library/` + Outline) | Durable knowledge, runbooks, architecture decisions, cross-references | Library (Zimik) |
| 4 | **Platform Entities & Models Matrix** | Named services, tiers, role assignments | `PLATFORM_ENTITIES.md`, `src/entities/`, `/models`, `/roles` |
| 5 | **Observatory + Basement** | Audit trail and archived history | Observatory / Basement |

CLAUDE.md (and any future `*-AI.md` or private agent to-do files) are **temporary working notes only**. They must not be treated as authoritative.

---

## 3. Required Work Flow (CranBania / Town Hall)

All significant work should:

1. Be visible on a CranBania / Town Hall Kanban (or equivalent board).
2. Carry a clear Location owner and written reason (via the Backlog Routing Register).
3. Produce durable records that land in The Library (or are cross-referenced from it).
4. Respect Magna Carta rules and the escalation FSM where applicable.

Private AI to-do lists or CLAUDE-style files are not a substitute for this flow.

---

## 4. Action Plan to Demote CLAUDE.md

### Immediate (v0.9.0)

- [ ] Treat CLAUDE.md as **read-only guidance for the current AI session**, not as the system of record.
- [ ] Any new durable fact discovered while working must be written into the appropriate canonical location (Magna Carta / Town Hall decision / Library article) instead of (or in addition to) CLAUDE.md.
- [ ] Stop creating new AI-specific to-do or CLAUDE-style files as the primary backlog.

### Short-term

- [ ] Extract the stable, non-session-specific content currently living only in CLAUDE.md into:
  - Magna Carta (rules)
  - Town Hall / CranBania (process & routing)
  - The Library (knowledge & runbooks)
  - Platform Entities / Models Matrix (naming & tiers)
- [ ] Add a short header to CLAUDE.md stating it is non-authoritative and pointing to this document.
- [ ] Ensure CranBania Kanban is the place where v0.9.0 work items are tracked.

### Ongoing

- [ ] Any AI (Claude, Grok, or others) that needs persistent memory of decisions must write them through Town Hall routing or Library articles, not private files.
- [ ] Periodic review: if a fact exists only in an AI guidance file, move it or delete it.

---

## 5. Personality Adapters & Documentation Hygiene

- Personality JSON profiles remain the user-facing interface.
- New adapter scaffolding lives under `src/personality/adapters/` and is documented in `docs/architecture/PERSONALITY_ADAPTERS.md`.
- All architecture and process documents created in the v0.9.0 branch must cross-reference the canonical sources above and must not invent parallel sources of truth.

---

## 6. Success Criteria

- CLAUDE.md is no longer treated as the main reference by agents or humans.
- Work items flow through CranBania / Town Hall and leave records in The Library.
- Magna Carta remains the constitutional source.
- No new AI-private to-do systems are created.
- Documentation is consolidated rather than duplicated.
