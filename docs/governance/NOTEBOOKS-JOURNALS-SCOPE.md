---
title: "Notebooks / Journals for AIs and Agents — Scoping Doc"
category: Reference
last-reviewed: 2026-07-31
status: needs-update
---

# Notebooks / Journals for AIs and Agents — Scoping Doc

> **What this is.** A design scope, not an implementation, for giving each named AI and Agent a
> personal Notebook/Journal, interconnected with the Kanban board tasks they're assigned to. Per
> the user's own earlier framing, this needed "a dedicated pass" rather than being built ad hoc —
> this is that pass. Nothing here is built yet.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. A naming collision to resolve first

**CranBania already has a "Journal" concept** (`lib/journal.ts`, `JournalEntry` type in
`lib/types.ts`) — but it means something different from what's being proposed here. CranBania's
Journal is a **per-card audit trail**: every `Card` accumulates `JournalEntry` records of type
`created` / `moved` / `updated` / `comment` / `code_change` / `webhook` / `worktree` / `sla`, each
with an `actor`, timestamp, and message. It's a system-generated activity log attached to a task,
not a personal space an AI writes freeform thoughts into.

What's being proposed here — a Notebook/Journal *belonging to* an AI or Agent, existing
independently of any one task — is a genuinely new concept. To avoid confusion with the existing
term, this doc calls it a **Notebook** throughout, reserving "Journal" for CranBania's existing
per-card log.

## 2. What already exists to build on

- **`src/relations/registry.py`'s Activity Feed** (`AI-RELATIONSHIP-MATRIX.md`) — the closest
  existing thing to a notebook: an append-only feed of `activity_events` per AI, but it's built for
  *system-recorded* events (an AI tagging into a Location, an interaction, a Role Registry
  reassignment), not free-form personal notes an AI writes for itself.
- **CranBania's `Card.assignee`** (`lib/types.ts`) — a **free-text string**, not a namespaced ID.
  This is the exact same identity-namespacing gap `AI-RELATIONSHIP-MATRIX.md` §2 already flagged for
  Agents/Bots ("every Location has its own generic 'Agent Alpha'") — any Notebook-to-task linkage
  keyed on `assignee` inherits that same ambiguity and needs the same resolution (namespaced IDs
  like `"The Spark:Agent Alpha"`) before it can be trusted.
- **CranBania's 40+ MCP tools** (`workers/cranbania/`, Traefik `/townhall`) — the existing bridge
  between Tranc3 and CranBania; a Notebook feature would most naturally use this same bridge rather
  than inventing a new one.

## 3. Proposed shape (design only)

### 3.1 Data model

A `NotebookEntry`, structurally similar to CranBania's `JournalEntry` but author-initiated rather
than system-generated:

```text
NotebookEntry:
  id
  owner            # the AI or Agent's identity string (same namespacing caveat as §2)
  created_at
  content          # free text — the AI's own note
  visibility       # ai_private | operator | public (see §4, open question — audience,
                   # not just a scope: ai_private = only the owning AI; operator = human
                   # staff, matching the Role Registry's admin-only mutation convention;
                   # public = anyone, same audience as the Relations Activity Feed)
  linked_card_id?  # optional CranBania Card.id — the interconnection point
  linked_location? # optional — for notes not tied to a specific task
```

### 3.2 Where it lives

Two real options, not yet decided (see §4):

- **In Tranc3**, as a new SQLite-backed registry (`src/notebooks/registry.py`), following the exact
  pattern already used by Role/Access/Relations registries — zero-cost, self-hosted, one file per
  registry. `linked_card_id` would be an opaque foreign key into CranBania, resolved via CranBania's
  MCP tools when a note is displayed alongside its task.
- **In CranBania**, alongside `lib/journal.ts`, as a sibling concept (`lib/notebook.ts`) — keeps
  task-linked notes physically close to the Kanban data they reference, at the cost of Notebooks
  not existing for AIs that have no CranBania task at all.

### 3.3 The interconnection itself

Two directions, both cheap given the data model above:

1. **Task → Notebook**: viewing a Card in CranBania's Kanban board could show the assignee's
   Notebook entries filtered to `linked_card_id == card.id` — "what has this AI written about this
   specific task."
2. **Notebook → Task**: an AI's Notebook view could show all entries grouped by `linked_card_id`,
   resolving each to its Card's title/status via CranBania's MCP tools — "everything this AI has
   noted, organized by the task it relates to."

Neither direction requires new *transport* — both reuse the already-existing CranBania MCP bridge
rather than inventing a new one. That doesn't mean there's no remaining work: real Notebook read/
write API endpoints, authorization checks per `visibility` value (§4), CranBania UI panels to
actually render the linkage, bounded/paginated queries (an AI's Notebook could grow unbounded), and
MCP-call error handling all still need building on top of that transport.

## 4. Open questions — need a decision before building

- **Where does it live** — Tranc3 or CranBania (§3.2)? This determines the tech stack (Python/
  SQLite vs. TypeScript/CranBania's own persistence) and who owns the migration if it's wrong.
- **Visibility** — which of the three `visibility` values in §3.1 (`ai_private`, `operator`,
  `public`) is the right default, and is more than one ever allowed per entry? This is a governance
  decision, not a technical one — `ai_private` raises the question of who can audit it if something
  goes wrong, versus `public` being no different from the existing Activity Feed.
- **Does this replace or extend the Activity Feed** — should Notebook entries also emit into
  `src/relations/registry.py`'s feed (matching the Role Registry's existing best-effort integration
  pattern), or stay a separate, unintegrated system? Emitting into both risks duplication; staying
  separate risks the same fragmentation this whole matrix-brainstorming pass has been trying to
  resolve.
- **Wallboards** — referenced in the original request alongside Kanban boards, but no "Wallboard"
  term or concept was found anywhere in the CranBania codebase (grepped `.ts`/`.tsx`/`.md`, no
  matches). This may refer to a status-dashboard view within CranBania that doesn't exist yet
  itself, or be a term from a different tool not currently in this platform. Needs clarification
  before the Notebook↔Wallboard linkage half of the request can be scoped at all.

## 5. Recommended next step, if this is prioritized

Given the identity-namespacing gap in §2 is a prerequisite both here and for
`AI-RELATIONSHIP-MATRIX.md`'s own already-flagged extension, the lowest-risk sequencing is:

1. Resolve namespaced Agent/Bot identities first (benefits both this feature and the Relationship
   Matrix's own already-documented gap — not a new problem, this doc just makes it block two things
   instead of one).
2. Answer the open questions in §4 (a human decision, not something to guess into an implementation).
3. Build the smaller of the two location options first (§3.2) and prove the CranBania MCP round-
   trip works before committing to the other.

## 6. Cross-references

- `docs/governance/AI-RELATIONSHIP-MATRIX.md` §2 (identity-namespacing gap), §9 (its own
  brainstormed-not-built extensions list, which this feature is adjacent to but distinct from).
- CranBania `lib/journal.ts`, `lib/types.ts` (`JournalEntry`, `Card.assignee`) — the existing
  system this doc is careful not to duplicate or rename.
