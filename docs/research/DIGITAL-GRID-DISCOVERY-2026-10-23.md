# The Digital Grid — discovery, integration and advancement report
**Research snapshot:** 2026-10-23
**Identity:** PID-DGR / AID-DGR-01
**Status:** Research and review completed; deployment/test evidence still required.
**Tracking:** [Tranc3 issue #1431](https://github.com/Trancendos/Tranc3/issues/1431)
**Scope:** Code-grounded GitHub examination, comparison to existing Drive design records, open-source/product research, capability and skill discovery. Not a full audit of every repository, all Drive content, or live running services.

## Executive decision
**Continue in Trancendos/Tranc3 and fix the existing workflow interfaces before adding an execution engine.** Retain the current monolith workflow DAG and the standalone 8010 worker as distinct, named surfaces until contracts and migration strategy are proven. The archived private “the-digitalgrid-studio” repository is not an active implementation. Treat the Stage-4 CI/CD/autohealing narrative as a proposed scope, not as already shipped.

The core value proposition is a **visual, accountable automation control plane** with:
1. A common, versioned workflow definition (graph plus node capability manifest).
2. Execution adapters with honest operational status and no simulated-success masquerading as real execution.
3. Event-driven integrations and credential-safe connectors.
4. Human approval, audit traces, rollback and incident reporting.
5. Templates, skills and capability discovery layered on top of a working engine.

## Source and implementation inventory
| Surface | Source | Code / evidence found | Judgment |
| --- | --- | --- | --- |
| Interactive editor | [DigitalGridPage](https://github.com/Trancendos/Tranc3/blob/main/web/src/components/workflow/DigitalGridPage.tsx), [useGridApi](https://github.com/Trancendos/Tranc3/blob/main/web/src/components/workflow/useGridApi.ts), [types](https://github.com/Trancendos/Tranc3/blob/main/web/src/components/workflow/types.ts) | Drag/drop nodes, edges, save/run calls, UI flow | Implemented source; functional integration **not yet proven** |
| Monolith API and executor | [routes.py](https://github.com/Trancendos/Tranc3/blob/main/src/workflow/routes.py), [builder.py](https://github.com/Trancendos/Tranc3/blob/main/src/workflow/builder.py), [executor.py](https://github.com/Trancendos/Tranc3/blob/main/src/workflow/executor.py) | DAG model, topological layering, event bus, REST API under /grid | Real code; currently uses in-memory workflow registry |
| Standalone worker | [workers/the-grid](https://github.com/Trancendos/Tranc3/tree/main/workers/the-grid) | FastAPI worker, SQLite state, 8 advertised adapters, Docker service on 8010 | Real code; requires integration and lifecycle tests |
| Old workflow worker | [workflow-engine-service](https://github.com/Trancendos/Tranc3/blob/main/workers/workflow-engine-service/worker.py) | Header explicitly says DEPRECATED, compatibility maintained; port 8034 | Keep until callers and features migrated |
| TypeScript domain implementation | [DigitalGrid hub](https://github.com/Trancendos/Tranc3/tree/main/tranc3-ts/src/hubs/digitalgrid) | AI, Weaver, EventBroker and Trigger/Action/Condition/Loop bots | Reusable candidate; no interoperability proof |
| Separate Studio repository | Trancendos/the-digitalgrid-studio | Repository metadata shows private, archived, minimal README | Do **not** select as canonical active runtime |
| Internal Drive design records | Location Profile, solution pack, and legacy System Spec | Conflicting port/scope narratives: 8010, 3014, 3049; development workflow vs Studio deployment matrix | Reconcile against code/compose; do not copy private Drive material into public repo |

### P0: the API contract is incompatible
1. Front-end GET/POST uses **/grid/workflows** on the *monolith* (not directly the standalone worker). The UI expects a save response containing **id** but monolith POST returns **registered** and **name**.
2. UI uses **nodes as an array** and edges with **sourceId/targetId**. Monolith WorkflowDefinition.from_dict expects a **node-ID-keyed object** and edges with **from/to/label**. An unadapted front-end POST will not parse correctly.
3. UI expects execution identifier **id**, monolith POST /grid/workflows/{id}/run returns **execution_id**. The standalone worker instead exposes POST /workflows/{id}/execute and yet another schema.
4. The monolith registry is in-memory while worker definitions are saved via its SQLite database. Selecting one persistence/execution source of truth is necessary before showing consistent history and restart recovery.
**Fix:** define a versioned workflow JSON Schema + standard endpoints and test a bidirectional TypeScript ↔ Python transformation. Test save → reload → execute → poll → cancel with real, deliberately failing, and simulated nodes.

### P0: correct execution semantics and security
- Standalone [service.py](https://github.com/Trancendos/Tranc3/blob/main/workers/the-grid/service.py) includes eight engine types (internal, n8n, Prefect, Temporal, Airflow, Dagster, Luigi, offline), **not eight verified working deployments**. Optional dependencies including temporalio, prefect and luigi are commented out in [requirements-worker.txt](https://github.com/Trancendos/Tranc3/blob/main/workers/the-grid/requirements-worker.txt).
- The offline fallback currently returns "completed" plus synthetic output. Replace this with explicit **simulated / no-external-execution** state and a visible UI banner. No workflow may claim a real external side effect was performed if it was not.
- All outbound HTTP/webhook node destinations require SSRF prevention: disallow loopback/link-local/internal metadata address ranges unless precisely authorised, pin DNS and enforce redirects policy, egress allowlist, credential handling and response limits. Implement secret redaction and deny arbitrary code.
- Add run-level idempotency keys, deterministic id allocation, cycle validation, bounded parallelism, real failure propagation, timeout/cancellation and trace IDs. Require approval for production/deployment actions.
- Production context has a named Docker build context for **Dimensionals** copied into the image; generic builds may miss it. Test actual Compose build/start/health plus simulated dependency outages.
- Existing independent issue: [#336 — injectable database/router per app](https://github.com/Trancendos/Tranc3/issues/336). Check its status and avoid duplicating work.

### P1: Temporal durable backend as an optional adapter
**Use:** Long-running/recoverable workflows, human approval checkpoints, retries, compensation (saga), heartbeats, timers and restart-safe execution. The official Temporal SDK distinguishes **Workflow code** (deterministic orchestration) from **Activities** (side effects). Separate queue and worker deployment must exist; a local CLI development server is not production HA.

**Specific existing problem:** The Temporal adapter starts workflow with an ID built from the *definition* ID (grid-{workflow_id}), which may collide on repeat runs, and immediately returns status "completed" with a Temporal run reference despite only starting the workflow. Fix with per-execution unique idempotent identity plus status synchronisation, cancellation and result collection.

**POC:** start a local Temporal dev server; install pinned SDK in an opt-in environment; run a workflow with two activities; terminate and restart the worker; prove history replay, retry bounds, signals and cancellation. Measure operational overhead before enabling production. Existing in-house executor remains default until this proves superior. Guide: https://docs.temporal.io/self-hosted-guide

### Engine choices: do not integrate everything by default
| Candidate | Strong fit | Boundary |
| --- | --- | --- |
| Existing Python DAG | Lightweight, low-cost, no new runtime | Needs persistence/recovery hardening |
| Temporal | Durable app workflows, approvals, recoverable execution | Requires server, state backend, workers, deterministic coding |
| Prefect | Python pipeline orchestration | Adds API/server burden and a second mental model |
| Kestra (Apache-2.0) | YAML/IaC workflows, event orchestration | Separate whole product; benchmark, don't embed prematurely |
| Trigger.dev (Apache-2.0) | Durable TypeScript jobs and approvals | Good comparison to TypeScript hub, different runtime topology |
| Activepieces core (MIT) | Prebuilt integrations and MCP-oriented pieces | Enterprise modules licensed separately; test piece licensing and version fit |
| React Flow (MIT) | Canvas/editor behaviors: zoom, selection, drag/drop | UI library, **not an executor**; evaluate replacing current bespoke canvas |
| n8n (Sustainable Use License) | Internal-use optional integration | **Not permissive OSS**; customer editing/embedding needs commercial licence |
| Argo Workflows | Kubernetes batch and deployment control plane | Avoid adding K8s only to obtain it |
| NVIDIA NeMo Agent Toolkit | Agent evaluation, instrumentation, profiling | Optional AI layer; no paid/GPU assumption |

Primary vendor sources: https://reactflow.dev/ ; https://support.n8n.io/article/can-i-use-your-license-for-my-use-case ; https://github.com/kestra-io/kestra ; https://github.com/triggerdotdev/trigger.dev ; https://github.com/activepieces/activepieces ; https://github.com/NVIDIA/NeMo-Agent-Toolkit .

## Connectors and ChatGPT capabilities
**Directly used this pass:** GitHub connector (authenticated Trancendos repos, code, issue) and Google Drive connector (user's supplied folder and related documents). These capabilities establish **read/write to permitted items only**; not filesystem/NAS runtime access.

**Existing relevant installed skills discovered:**
- Product Design skills: brief/context, research, audit, ideate, share. Full design/prototype Product Design workflows should be invoked in ChatGPT Work; a research recommendation is not a rendered product.
- Temporal Developer, Temporal Ops, Temporal Serverless, Cloud Setup: strong for validating self-hosted engine/SDK, live ops and separate serverless worker case.
- NVIDIA Skill Finder: can search the live official NVIDIA skills catalog (https://github.com/NVIDIA/skills). Good matches: nemo-retriever and nemo-retriever-mcp (document RAG), nemo-relay-plugin-observability (agent traces), rag-eval (evaluation). These are *catalog recommendations*, not installed capabilities until approved and installed.
- Template Creator: **creates an installable personal artifact template from a supported actual reference** such as a Google Doc, Slides, Sheet, Office file or image; this is distinct from an executable Digital Grid workflow template. Create a reference artefact first, then run its packaging workflow.
- Google Drive and Google Sheets skills: research, source ingestion, registers and reusable task/issue tracking.
- Code-quality and test-driven engineering skills: use after acceptance criteria are approved to implement incremental fixes.

**Connector opportunities to evaluate individually with access grants:** Notion or GitHub Issues as source of task truth; Figma/design systems for editor design; Vercel/Render/Railway for optional hosting (verify costs); Supabase/PostHog/observability for telemetry; GitHub and Drive ingest via APIs and least-privilege scopes; OpenTelemetry for traces; MCP for typed connector actions. Do not mirror private documents into a public repo and do not install third-party skills without explicit consent.

## Target architecture
1. **Discovery/CMDB:** each workflow node references a capability ID, connector, target service, data classification, approval policy, version and documented dependencies.
2. **Canvas + Template Registry:** visual flow builder, declarative versioned graph schema, offline drafts and structural validation.
3. **Gateway:** authN/authZ and capability/tenant policy; versioned contract and status stream.
4. **Execution Core:** a single ownership model, observable run records and explicit state machine; engine adapters operate only when checked healthy and functionally compatible.
5. **Safety Controller:** egress boundaries, secret leasing, audit, RBAC, staged approval, kill switch, shadow/simulation mode.
6. **Observatory + Recovery:** W3C traces, structured logs, runbook links, error-cause clusters, retries with bounded backoff, dead-letter/quarantine and rollback.
7. **Knowledge/Skills:** evidence-backed recommendations, connector catalogue, RAG for documentation, sandboxed helper agents; AI may propose code changes but cannot self-approve production deployments.
8. **Offline/NAS:** SQLite per worker, local-file templates and queued intent; never silently acknowledge queued actions as executed.

### Suggested layout
- **Overview:** plain-language current state, actions needed, recently failed workflows.
- **Canvas:** nodes palette, editable graph, validation/errors in context, keyboard and screen-reader support.
- **Execution Inspector:** timeline, state, inputs/outputs redacted, trace, retries, simulation badge and cancellation.
- **Connectors:** supported services, health, permissions, rate limits and data sharing.
- **Template Library:** verified templates only, with provenance and test fixtures.
- **Operations/Recovery:** incidents, impact, rollback, service dependencies, approvals and cost caps.

An **Empathy Mandate** user experience should turn raw exceptions into “What failed / impact / action / evidence” and avoid walls of log text, without concealing technical detail from experts.

## Research/ideastorm backlog
**P0 release-blocking**
- DG-01 Contract translator and JSON Schema (frontend ⇆ monolith ⇆ worker), Python/TS test fixtures.
- DG-02 False-completion elimination and engine health truthfulness.
- DG-03 Secrets/egress/RBAC/human-approval hardening.
- DG-04 End-to-end demo including failed run and offline simulation.
- DG-05 Drive file sharing review in **private workspace**. Never record private permission metadata or personal identities in this public repository.

**P1 value and reliability**
- DG-06 Retirement matrix for deprecated worker with source attribution and consumers.
- DG-07 Idempotent durable execution POC with Temporal only after baseline E2E succeeds.
- DG-08 MCP capability registry + connector test harness (mock and live-permitted modes).
- DG-09 Observability and incident correlation across GitHub, Grid and Observatory.
- DG-10 Local/NAS installer profile with backup/restore tests and clean rollback.

**P2 future-advancement concepts**
- DG-11 “Workflow Doctor” that explains likely failures, tests synthetic alternatives and proposes safe fixes.
- DG-12 “Template Forge”: JSON/YAML templates with schema version, author, license, hash, permissions, sample inputs/outputs, side-effect level, budget and conformance tests.
- DG-13 “Shadow Run”: simulate side effects and compare expected state; never imply deployment happened.
- DG-14 “Skill & Plugin Radar”: discover available skills, score trust/permissions/compatibility/version and recommend only validated candidates.
- DG-15 “Resilience Graph”: connector health and fallback edge view; fallback only when semantics and consent remain safe.
- DG-16 “Change Impact Compass”: show workflow, repository, service, asset and documentation dependency blast radius before release.

## Release gates / definition of done
| Gate | Verifiable proof |
| --- | --- |
| Contract | UI builds and round-trips a 3-node flow, reload preserves graph, test fixture shared Python/TS |
| Real execution | HTTP/mocked action and actual callback cause observed side effect, correlated to run ID |
| Failure | Inject timeout, 401, 429, circuit open, network outage; precise state and explanation |
| Offline | Offline workflow draft preserved; side effects explicitly simulated or queued, not “completed” |
| Security | Auth, least privilege, SSRF/private IP denial, secret masking, approval and replay protection tested |
| Durability | Restart mid-run with truthful result; Temporal POC only if selected |
| Operations | Documented startup/shutdown, Docker context, port mapping, logs, rollback, back-up restore |
| Economics | Zero paid dependency by default, documented runtime resources, licences and service quotas |

## Evidence classification
**Observed in source:** UI, monolith/worker code, API mismatch, optional Temporal SDK, deprecated worker notice, offline synthetic completion, GPU config as described in older matrix.

**Reported by repository documents but not independently live-verified:** production deployment, uptime, eight active engines, “complete” doc pack, CI/CD automatic deployment, self-healing and hardware availability.

**Proposed, not implemented here:** versioned unified schema, all new safety controls, Temporal POC, skill radar, Template Forge and enhanced UI.

**Next review:** validate a live run in an isolated environment and attach test output to issue #1431. No production deployment or customer data access performed in this research pass.
