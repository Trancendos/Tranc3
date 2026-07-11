# AI-to-AI Relationship Matrix, Activity Feed & Location Brochure

> **Truthfulness:** this doc describes `src/relations/` as written — a real, tested, SQLite-backed
> module mounted at `/relations` in `api.py`. Identity scope, scoring model, and known
> simplifications are stated plainly below rather than implied to be more complete than they are.

## 1. What this is

A **living relationship layer** across the platform's 43 Locations and their Lead AIs, answering
three questions:

1. **How do two AIs get along?** — a pairwise trust/relationship score (`-100` fully blocked to
   `+100` fully trusted), seeded from Job Description / Pillar proximity and nudged by recorded
   activity. No AI is ever permanently locked out — every score decays toward its baseline when
   idle, and a single positive interaction can always start moving a blocked relationship back up.
2. **What has been happening, and where?** — an append-only activity feed: an AI tagging itself
   into a Location, two AIs chatting, an AI performing a notable action at a Location ("raided the
   bank", "helped repair a policy"), or a system event (e.g. a Role Registry reassignment).
3. **What's a Location like right now?** — a per-Location "brochure": visit stats, sentiment
   breakdown (good/bad/neutral), top visitors, recent highlights, and flavor text assembled from
   the current resident's personality profile — a holiday-brochure-style snapshot of a Location's
   character, derived entirely from real recorded activity, not scripted copy.

## 2. Identity scope (v1)

The relationship matrix operates on the platform's **39 canonical Lead AI names**
(`src/entities/platform.py`'s `lead_ai` field) — the same identity space the Role Assignment
Registry (`docs/governance/LOCATION-FUNCTIONS.md`) already uses. This is a deliberate v1 scope
decision, not a limitation baked into the schema:

- Agents and Bots (Tier 4/5) are **not** globally unique identities today — every Location has its
  own generic "Agent Alpha"/"Bot 01", so "Agent Alpha talked to Agent Alpha" would be ambiguous
  without a namespaced ID (e.g. `"The Spark:Agent Alpha"`).
- `ai_relationships` and `activity_events` both store **free-text identity strings** — extending to
  namespaced Agent/Bot IDs later is a data-modelling choice (what string you pass in), not a schema
  migration.
- 4 of the 39 Lead AI names are shared across two Locations each (e.g. Voxx leads both The Studio
  and Imaginarium). The pillar-proximity baseline seed (§4) resolves each name to whichever
  Location `PLATFORM_ENTITIES` iterates last for that name — a minor imprecision affecting only the
  *seeded baseline*, not recorded activity, and not distorting in practice since a Lead AI's
  duplicate Locations are typically in the same Pillar anyway.

## 3. Data model

Two SQLite tables (`data/relations_registry.db`, zero-cost self-hosted, matching this platform's
architecture principles — same pattern as the Role Assignment Registry):

- **`ai_relationships`** — one row per *unordered* pair (`ai_a < ai_b` lexicographically, enforced
  in code): `score`, `updated_at`, `interactions_count`. A single scalar per pair, representing
  *mutual* relationship quality — this module does not model asymmetric "A trusts B but B distrusts
  A" relationships; that's a deliberate simplicity trade-off, not an oversight.
- **`activity_events`** — append-only: `ts`, `actor_ai`, `event_type`, `location`, `target_ai`,
  `sentiment`, `summary`, `details_json`. Never edited or deleted, matching the Role Registry's
  audit-history convention.

Event types: `location_tag` (an AI checking into a Location), `ai_interaction` (two AIs
interacting — the only type that nudges the relationship matrix), `action` (a Location-scoped deed
with no specific counterpart AI — feeds the brochure's sentiment stats, not the matrix), `system`
(automated platform events — see §6).

## 4. Scoring model

- **Baseline**: same-Pillar pairs seed at `+25` ("friendly"); different-Pillar pairs seed at `0`
  ("neutral"). AIs/identities the platform doesn't recognize (future Agent/Bot IDs, typos) fall
  back to a neutral `0` baseline rather than erroring.
- **Nudges**: an `ai_interaction` event with `sentiment="positive"` or `"negative"` moves the pair's
  score by a base delta (`±5`), scaled by both AIs' personality traits (§5) — more agreeable/
  empathetic AIs swing further positive; more assertive/neurotic AIs swing further negative.
  `sentiment="neutral"` interactions are recorded in the feed but don't move the score.
- **Decay**: every stored score decays toward its baseline with a ~10-day half-life, computed
  lazily at read time (no background job) — a score frozen by inactivity trends back toward neutral
  rather than staying artificially blocked or trusted forever.
- **Redemption is structural**: scores are clamped to `[-100, 100]` but never locked. A relationship
  driven to `-100` ("blocked") can always recover — every future positive interaction, or simple
  time passing (decay), moves it back up. There is no code path that makes a block permanent.
- **Permission tiers** (inclusive lower bound on each threshold):

  | Score range | Tier | Meaning |
  |---|---|---|
  | `≥ 60` | `trusted` | full access, unique trusted interactions |
  | `[20, 60)` | `friendly` | normal, cooperative access |
  | `[-20, 20)` | `neutral` | cautious/default access |
  | `[-60, -20)` | `restricted` | limited access |
  | `< -60` | `blocked` | blocked from that AI's Location — but redeemable |

## 5. Personality quirks (`src/relations/personality.py`)

Best-effort loader over `src/personality/profiles/*.json`, keyed by `code_name` (the same name used
by `lead_ai`). Not every Lead AI has a matching profile today — some spellings differ (e.g. "The
Guardian" in profiles vs. "The Guardian (Anchor: Orb of Orisis)" in `PLATFORM_ENTITIES`) — every
lookup falls back to a neutral trait set (`0.5` across the board) rather than raising, so scoring
and brochures work identically whether or not a profile exists; a matching profile only adds
flavor and sharper nudges, it's never required.

- `positivity_multiplier` — driven by `agreeableness`/`empathy` (≈0.7×–1.3×).
- `negativity_multiplier` — driven by `assertiveness`/`neuroticism` (≈0.7×–1.3×).
- Brochure flavor text pulls the resident's `description` and `style.tone` when a profile is found.

## 6. Automated trigger: Role Registry integration

`src/roles/registry.py`'s `assign_ai()`/`remove_ai()` each emit a best-effort `system` event into
the Relations feed after a successful (re)assignment or vacancy — e.g. *"Dorris Fontaine was
assigned as Chief Financial Officer of Royal Bank of Arcadia."* This is the one real, automated
integration point tying the two systems together: reassigning who holds a Location's Job
Description is exactly the kind of event the Activity Feed and Location Brochure exist to surface.

The call is wrapped in a bare `except Exception: pass` and imports `src.relations` lazily (inside
the method, not at module load time) — Role assignment must never fail because the Relations
module is unavailable, mid-migration, or simply not imported in a given test/runtime context. The
two modules remain independently testable; `tests/test_roles.py` does not depend on
`src/relations/` existing.

## 7. Live API (`/relations`, mounted in `api.py`)

| Method | Route | Purpose | Auth |
|---|---|---|---|
| GET | `/relations/feed` | Activity feed, filterable by `ai`/`location`/`limit` | none |
| GET | `/relations/insights` | Proactive observations (§8) | none |
| GET | `/relations/locations/{location}/brochure` | The Location brochure | none |
| GET | `/relations/{ai_a}/{ai_b}` | One pairwise relationship score | none |
| GET | `/relations/{ai}` | One AI's full relationship list (all 38 others) | none |
| POST | `/relations/events` | Record an activity event | **any authenticated caller** |

Read routes are public, matching the Role Registry's convention. `POST /relations/events` requires
authentication (any role, not admin-only) — it's meant to be called by the platform's own
orchestration/agent layer or an operator tool, not the public, since it's the one route that
mutates state; unlike Role assignment, recording an activity event isn't itself a governance action
requiring `admin`.

Like the Role Registry, the single-location brochure route uses FastAPI's `:path` converter
internally so "ChronosSphere / ArcStream" (the one canonical Location with a literal `/`) resolves
correctly — the route table above shows `{location}` because FastAPI's generated OpenAPI spec
strips the `:path` suffix from the parameter name in its public-facing output.

## 8. Proactive insights (`get_insights()`)

Computed over a rolling window (default 7 days), no stored history required — everything is derived
from the activity feed and current matrix state on each call:

- **`busiest_location`** — the Location with the most events this window.
- **`negative_activity_spike`** — any Location with 3+ negative-sentiment events this window.
- **`most_improved_relationship`** / **`deteriorating_relationship`** — the AI pair with the most
  net-positive / net-negative `ai_interaction` events this window.
- **`ai_at_risk`** — any AI currently `restricted` or `blocked` with 3+ other AIs — a nudge that
  positive interactions would help repair standing before it calcifies.

## 9. Brainstormed extensions (not built — ideas for later)

- **Namespaced Agent/Bot identities** (`"<Location>:Agent Alpha"`) to extend the matrix below the
  Lead AI tier, once a real need for Agent-to-Agent trust tracking emerges.
- **Directional trust** (A trusts B ≠ B trusts A) if the mutual-score simplification (§3) ever
  proves too coarse for a real scenario.
- **Location-to-Location relationships** (e.g. Cryptex and The Ice Box cooperating on a threat
  response) — currently only AI-to-AI and AI-to-Location (via the feed) are modelled.
- **Redemption arcs as a first-class concept** — e.g. a `/relations/{ai_a}/{ai_b}/history` endpoint
  (mirroring the Role Registry's `/history`) showing the score's trajectory over time, not just its
  current value — would make "AI X was blocked and earned its way back" visible, not just inferable
  from the raw feed.
- **Cross-linking into The Observatory** — activity events are exactly the kind of platform action
  The Observatory (`src/observability/`) exists to audit; a best-effort forward from
  `record_event()` into Observatory's event bus would give this feed the same durability guarantees
  Observatory already provides for the rest of the platform, without this module needing to
  reimplement them.
- **Brochure "seasonal" framing** — e.g. surfacing "this Location's best week" vs. "this Location's
  worst week" using the same sentiment-count aggregation already computed, no new data needed.
