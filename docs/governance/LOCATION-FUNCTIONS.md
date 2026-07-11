# Location Functions & Job Descriptions Registry

> **What this is.** A report on every one of the platform's 43 named Locations (`PLATFORM_ENTITIES.md`)
> — its primary function, the functional **Job Description** (role title) that sits over that
> function, and which AI is currently assigned to hold it. Unlike the rest of `docs/services/*`
> (which documents *code*), this document is grounded in a live, mutable registry: the table below
> reflects the seed state (`assigned_ai` = each entity's canonical `lead_ai`); the actual live state
> is queryable and changeable at runtime — see "Live API" below.

**Code:** `src/entities/platform.py` (`JOB_DESCRIPTIONS` dict, `get_job_description()`),
`src/roles/registry.py` (`RoleRegistry`, SQLite-backed), `src/roles/routes.py` (HTTP API, mounted
in `api.py` at `/roles`).
**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-11

---

## 1. Model

Three things, kept deliberately distinct:

| Concept | What it is | Where it lives | Mutability |
|---|---|---|---|
| **Location** | One of the 43 canonical platform entities | `PLATFORM_ENTITIES` dict | Fixed (adding a 44th is a platform-level change, not a role reassignment) |
| **Job Description** | The functional, executive-style title for that Location's Tier-3 role (e.g. "Chief Financial Officer") | `JOB_DESCRIPTIONS` dict, `src/entities/platform.py` | Fixed per Location; editing the title itself is a code change, not an API call |
| **Assigned AI** | The specific AI/persona currently holding that Job Description | `role_assignments` table, `src/roles/registry.py` (SQLite, `data/role_registry.db`) | **Mutable at runtime** via the API below — add, remove, or reassign at any time |

This mirrors the existing `lead_ai` field on `LocationEntity`, but deliberately does not replace
it: `lead_ai` remains the *canonical, documented* name (used throughout `CLAUDE.md`,
`PLATFORM_ENTITIES.md`, and every `docs/services/*/README.md` pack); the registry's `assigned_ai`
is the *live, operational* holder, seeded from `lead_ai` but free to diverge once an operator
reassigns it. Treat `lead_ai` as "who this role was designed for" and the registry as "who
actually holds it right now."

## 2. Master table (seed state)

| Location | Pillar | Primary Function | Job Description | Assigned AI (seed) |
|---|---|---|---|---|
| **The Nexus** | Architectural | AI Communication Gateway & AI, Agent, and Bot / Worker Transfer Hub | Chief Communications Officer | Nexus-Prime |
| **The HIVE** | Architectural | Data Transport Hub | Head of Data Transport & Swarm Operations | The Queen |
| **Arcadia** | Commercial / Financial | Post-Login User Frontend, Forum & Email Hub | Chief Community & Front-End Officer | Lilli SC |
| **Luminous** | Architectural | Core Platform Brain & Orchestration Engine | Chief Technology Officer | Cornelius MacIntyre |
| **The Town Hall** | Architectural | Governance & Compliance Center | Chief Governance Officer | Tristuran |
| **The Studio** | Creativity | Central Hub of the Creativity Center | Chief Creative Officer | Voxx |
| **Sashas Photo Studio** | Creativity | Photo & Image Generation Center | Head of Photo & Image Generation | Madam Krystal |
| **TranceFlow** | Creativity | 3D Modeling & Games Creation Studio | Head of 3D & Game Development | Junior Cesar |
| **TateKing** | Creativity | Video Creation & Editing Platform | Head of Video Production | Benji Tate & Sam King |
| **Fabulousa** | Creativity | Styling, UX, UI & Design Center | Chief Design Officer | Baron Von Hilton |
| **Imaginarium** | Creativity | Omni-Creative Masterpiece Wizard | Chief Creative Orchestration Officer | Voxx |
| **The Digital Grid** | Development (Code) | Workflow Platform | Head of Workflow Engineering | Tyler Towncroft |
| **The Lab** | Development (Code) | Code Creation Platform | Chief Engineering Officer | The Dr. & Slime |
| **The Workshop** | Development (Code) | Repository Storage (Forgejo) | Head of Source Control & CI/CD | Larry Lowhammer |
| **The Chaos Party** | Development (Code) | Central Testing Platform (Wonderland Theme) | Head of Quality Assurance & Testing | The Mad Hatter |
| **The Artifactory** | Commercial / Financial | Central Artifact Repository Library (JFrog style) | Head of Artifact Management | Lunascene |
| **API Marketplace** | Commercial / Financial | Central Integration Hub (APIs, Webhooks, OAuth) | Head of API Integrations | Solarscene |
| **Royal Bank of Arcadia** | Commercial / Financial | Financial & Operations Management | Chief Financial Officer | Dorris Fontaine |
| **Arcadian Exchange** | Commercial / Financial | Procurement & Resource Trading | Chief Procurement Officer | The Porter Family |
| **The Observatory** | Knowledge | Audit Log & Monitoring Platform | Chief Audit & Monitoring Officer | Norman Hawkins |
| **The Library** | Knowledge | Knowledge Base & Wiki | Chief Knowledge Officer | Zimik |
| **The Academy** | Knowledge | Education & Skill Training | Head of Learning & Development | Shimshi |
| **DocUtari** | Knowledge | Document Management Hub | Head of Document Management | To be Defined |
| **The Basement** | Knowledge | Archived Information Store | Head of Archives | Gary Glowman (Glow-Worm) |
| **The Spark** | Knowledge | The MCP Skills Matrix | Head of AI Tooling | Imfy |
| **Infinity** | Security | Centralized Auth, Edge Auth (OAuth 2.0) & User Transfer | Chief Identity & Access Officer | The Guardian (Anchor: Orb of Orisis) |
| **The Void** | Security | Secrets Vault, Password Store & Sensitive Data Store | Chief Secrets & Vault Officer | Prometheus |
| **The Lighthouse** | Security | Cryptographic Token Applicator | Head of Cryptographic Token Services | Rocking Ricki |
| **The Warp Tunnel** | Security | Cryptographic Scanner & Automated Quarantine Transport | Head of Threat Scanning & Quarantine | Rocking Ricki |
| **Cryptex** | Security | Cyber Defense (Threat Intelligence, DDoS, CVE Scanning) | Chief Information Security Officer | Renik |
| **The Ice Box** | Security | Inception-Layered Sandbox Threat Isolation & Quarantine Centre | Head of Sandbox Threat Isolation | Neonach |
| **Warp Radio** | Commercial / Financial | Music & Audio Streaming Integration | Head of Audio & Streaming | Rocking Ricki |
| **The Dutchy** | DevOps | Intelligence (Predictive lore, market intelligence) | Chief Intelligence Officer | Predictive lore |
| **The Citadel** | DevOps | Strategic Ops (Main fortress for Think Tank/R&D/Temporal nodes) | Chief Operations Officer | Trancendos |
| **Think Tank** | DevOps | R&D Centre | Head of Research & Development | Trancendos |
| **Turing's Hub** | DevOps | Central Creation Forge (3D Avatar & AI Entity Generation) | Head of AI Entity Creation | Samantha Turing |
| **ChronosSphere / ArcStream** | DevOps | Task, Time and Scheduling Management | Head of Scheduling & Task Management | Chronos |
| **DevOcity** | DevOps | Development Operations | Head of DevOps | Kitty |
| **Tranquility** | Wellbeing | Wellbeing Central Hub | Chief Wellbeing Officer | Savania |
| **I-Mind** | Wellbeing | Sensitivity to Emotion Engine | Head of Emotional Intelligence | Elouise |
| **tAimra** | Wellbeing | Opt-in Digital Twin System & Life Assistant | Head of Digital Twin Services | tAImra |
| **VRAR3D** | Wellbeing | Standalone 3D / VR immersion | Head of Immersive Technology | Entari |
| **Resonate** | Wellbeing | Empathy Engine | Head of Empathy Engineering | Magdalena |

> **Worked example, per the original request:** Royal Bank of Arcadia → pillar **Commercial /
> Financial** → Job Description **Chief Financial Officer** → currently assigned to **Dorris
> Fontaine** (the canonical `lead_ai`). Reassigning that seat to a different AI does not change the
> Location or its Job Description — only `assigned_ai` and its history change.

## 3. Live API (`/roles`, mounted in `api.py`)

| Method | Route | Purpose | Auth |
|---|---|---|---|
| GET | `/roles/` | List all 43 current assignments | none |
| GET | `/roles/{location}` | Get one Location's current assignment | none |
| GET | `/roles/{location}/history` | Full reassignment history for one Location, newest first | none |
| POST | `/roles/{location}/assign` | Assign or reassign an AI — body `{"ai_name": "...", "reason": "..."}` | **admin role required** |
| DELETE | `/roles/{location}/assign` | Vacate the role (sets `assigned_ai` to `null`) — optional body `{"reason": "..."}` | **admin role required** |

Read routes are open, matching most other registry-style modules on this platform (The Library,
API Marketplace, etc.). Mutating routes require `role == "admin"` on the caller's JWT
(`Depends(get_current_user)`, same dependency used by DevOcity and others) — reassigning who holds
a platform-wide Job Description is a governance action, not a self-service, per-user operation.

Every assignment change is recorded in `role_assignment_history` (previous AI, new AI, timestamp,
who made the change, and an optional free-text reason) and is never overwritten — the full audit
trail is always retrievable via the `/history` route.

## 4. Persistence

SQLite file at `data/role_registry.db`, created and seeded on first use (module-level singleton
via `get_registry()`) — zero-cost, self-hosted, no external DB dependency, consistent with this
platform's architecture principles (`CLAUDE.md` § Architecture principles). Seeding is idempotent:
reopening an existing database does not re-seed or duplicate rows.

## 5. Adding a new Job Description or Location

This registry does not currently expose an API to add a 44th Location or change an existing
Location's Job Description title — both are treated as platform-definition changes (edit
`PLATFORM_ENTITIES` / `JOB_DESCRIPTIONS` in `src/entities/platform.py`, then let the registry
re-seed the new row on next startup), not operator-level reassignments. Only the *AI holding* a
Job Description is mutable at runtime, per the "Model" table in §1 above.

---

## Verification Log

| Date | Verifier | Result |
|---|---|---|
| 2026-07-11 | Claude (session) | Confirmed `JOB_DESCRIPTIONS` covers exactly the same 43 keys as `PLATFORM_ENTITIES`; manually exercised `RoleRegistry` (seed, get, assign, reassign, remove, re-assign-after-removal, history ordering, reconnect-idempotency) against a temp SQLite file — all behaviors verified correct. `pytest` unavailable in this sandbox; `tests/test_roles.py` added for CI to run. |
