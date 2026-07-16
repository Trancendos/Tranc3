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

The route table above shows `{location}`, matching what FastAPI's generated OpenAPI spec (and
therefore `/docs`, SDK generators, etc.) actually displays — FastAPI strips the `:path` converter
suffix from the path-parameter name in its OpenAPI output. The underlying implementation still
uses `:path` internally (see below) so it works correctly; only the public-facing route
notation differs from the source code.

All four single-location routes use FastAPI's `:path` converter (not the default segment
converter) because **ChronosSphere / ArcStream** — one of the 43 canonical locations — contains a
literal `/`. `role_history`/`assign_role`/`unassign_role` are registered before the bare `get_role`
route in `src/roles/routes.py` so their trailing `/history` and `/assign` literals are matched
correctly instead of being swallowed by the unsuffixed route's greedy path segment.

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

## 6. Key metrics & escalation paths (seed data, 14 of 43 Locations)

Per-role operating targets and escalation triggers for the Job Description holder to track day
to day, seeded for the Locations where this level of detail was available. Not yet populated for
the remaining Locations — add a row here when a Job Description gets this level of definition,
following the same shape. `assigned_ai` matches §2's seed state; escalation paths refer to "the
location's Tier 2 Prime sponsor" generically rather than naming one, since Tier 2 Prime sponsorship
is assigned separately (see `master-schema.md` §SCHEMA-CORE-001) and is out of scope for this file.

| Location | Assigned AI (seed) | Key Metrics | Escalation Path |
|---|---|---|---|
| **Infinity** | The Guardian (Anchor: Orb of Orisis) | Authentication success rate 99.99%; MTTD anomaly < 5 min; access review completion 100%; security incidents 0; token generation latency < 100ms | SEV-1 security incident → immediate escalation; compliance violation → Tier 2 Prime sponsor; policy change → Tier 2 Prime sponsor approval |
| **The Lab** | The Dr. & Slime | Compilation success rate 99.95%; average compilation time < 2 min; queue depth < 100 jobs; developer satisfaction > 90%; code coverage > 80%; incident MTTR < 30 min | Compilation failure > 5 min → immediate investigation; performance degradation > 20% → optimization sprint; quality metric drop → root cause analysis; SEV-1 → immediate escalation to Tier 2 Prime sponsor |
| **The Workshop** | Larry Lowhammer | Repository availability 99.99%; response time < 500ms; backup success 100%; RTO < 15 min; RPO < 5 min; artifact storage utilization < 80% | Repository unavailable > 5 min → immediate investigation (see `deploy/forgejo/RUNBOOK.md`); backup failure → immediate remediation; data loss incident → SEV-1 escalation; compliance violation → Tier 2 Prime sponsor |
| **The Observatory** | Norman Hawkins | Audit log availability 99.99%; audit log latency < 1s; compliance score 100%; critical audit findings 0; monitoring coverage 100%; alert accuracy > 95% | Audit log failure → immediate escalation; compliance violation → Tier 2 Prime sponsor; data loss → SEV-1 incident; privacy breach → immediate escalation |
| **The Void** | Prometheus | Vault availability 99.99%; secret rotation success 100%; encryption key rotation 100%; backup success 100%; security incidents 0; compliance violations 0 | Vault unavailable → immediate escalation (highest blast radius — see `docs/architecture/ea-workbook/runbooks.md`); encryption key loss → SEV-1; security breach → immediate escalation; compliance violation → Tier 2 Prime sponsor |
| **Cryptex** | Renik | MTTD < 5 min; MTTR < 30 min; vulnerability detection rate > 95%; false positive rate < 5%; critical security incidents 0; compliance violations 0 | Threat detected → immediate investigation; security incident → SEV-1 escalation; malware detected → immediate containment; compliance violation → Tier 2 Prime sponsor |
| **The HIVE** | The Queen | Data transport availability 99.99%; throughput > 1GB/s; packet loss < 0.1%; latency < 50ms; data integrity 100%; RTO < 15 min | Data transport unavailable → immediate investigation; data loss → SEV-1 incident; data integrity issue → immediate investigation; performance degradation > 20% → investigation |
| **Luminous** | Cornelius MacIntyre | Orchestration availability 99.99%; workflow execution success > 99%; workflow latency < 1s; service coordination success > 99%; automation execution success > 99%; reliability > 99.9% | Orchestration unavailable → immediate investigation; workflow failure rate > 1% → investigation; performance degradation > 20% → optimization; compliance violation → Tier 2 Prime sponsor |
| **The Lighthouse** | Rocking Ricki | Token generation success 99.99%; token validation latency < 50ms; token revocation success 100%; security incidents 0; compliance violations 0; token usage accuracy 100% | Token generation failure → immediate investigation; token security breach → SEV-1 incident; compliance violation → Tier 2 Prime sponsor; performance degradation > 20% → investigation |
| **The Academy** | Shimshi | Training completion rate > 95%; knowledge base coverage 100%; documentation accuracy 100%; learning satisfaction > 90%; certification pass rate > 85%; onboarding success rate > 95% | Knowledge base unavailable → immediate investigation; training failure → investigation; documentation gap → update request; compliance violation → Tier 2 Prime sponsor |
| **Arcadia** | Lilli SC | Frontend availability 99.95%; page load time < 2s; user satisfaction > 90%; accessibility score > 95%; performance score > 90%; error rate < 0.1% | Frontend unavailable > 5 min → immediate investigation; performance degradation > 20% → investigation; user satisfaction drop → investigation; accessibility violation → remediation |
| **Tranquility** | Savania | Service availability 99.95%; user satisfaction > 90%; data privacy 100%; HIPAA compliance 100%; biometric accuracy > 99%; support response time < 1 hour | Service unavailable → immediate investigation; data privacy breach → SEV-1 incident; HIPAA violation → immediate escalation; user safety concern → immediate escalation |
| **The Studio** | Voxx | Tool availability 99.95%; rendering performance < 1s; user satisfaction > 90%; collaboration success > 95%; asset management accuracy 100%; performance score > 90% | Tool unavailable > 5 min → immediate investigation; performance degradation > 20% → investigation; user satisfaction drop → investigation; data loss → SEV-1 incident |
| **The Library** | Zimik | Knowledge base availability 99.95%; search success rate > 95%; content accuracy 100%; user satisfaction > 90%; content currency 100%; usage growth > 20% quarterly | Knowledge base unavailable → immediate investigation; search failure → investigation; content accuracy issue → update request; compliance violation → Tier 2 Prime sponsor |

Two roles from the source material were deliberately **not** included here because their metrics
targeted a Job Description that doesn't match this file's canonical assignment: a "Solarscene —
infrastructure operations" set (Solarscene's actual assigned Location per §2 is API Marketplace /
Head of API Integrations, not infrastructure) and a "Dorris Fontaine — API marketplace" set
(Dorris's actual assigned Location is Royal Bank of Arcadia / Chief Financial Officer). Attaching
either set to its mismatched Location would have been misleading rather than useful.

---

## Verification Log

| Date | Verifier | Result |
|---|---|---|
| 2026-07-11 | Claude (session) | Confirmed `JOB_DESCRIPTIONS` covers exactly the same 43 keys as `PLATFORM_ENTITIES`; manually exercised `RoleRegistry` (seed, get, assign, reassign, remove, re-assign-after-removal, history ordering, reconnect-idempotency) against a temp SQLite file — all behaviors verified correct. `pytest` unavailable in this sandbox; `tests/test_roles.py` added for CI to run. |
| 2026-07-16 | Claude (session) | Added §6 (Key metrics & escalation paths) from externally-supplied role material; cross-checked every entry against this file's §2 seed assignments before including it, and excluded two entries (Solarscene, Dorris Fontaine) whose source metrics targeted a different Job Description than their canonical assignment here. Did not adopt the source material's Tier 1/2/3 org-chart, which conflicted with `master-schema.md`'s `PID-PRIME-XXX` tier assignments. |
