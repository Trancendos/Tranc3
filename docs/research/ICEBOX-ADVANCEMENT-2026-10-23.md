# IceBox — Evidence-Driven Advancement Plan (2026-10-23)

**Entity:** PID-ICB / SRV-ICEBOX-001 | **Lead:** Neonach | **Pillar:** Security
**Canonical source:** Trancendos/Tranc3 `workers/ice-box-service/` and `src/security/ice_box/`.
**Review state:** Technical assessment, not a production deployment or a validated dynamic sandbox.

## 1. Verified current implementation

| Capability | Observed evidence | Assessment |
| --- | --- | --- |
| HTTP static scanning | `workers/ice-box-service/worker.py`, `POST /scan` | Implemented; needs integration/runtime test |
| Signature + entropy matching | `src/security/ice_box/analyser.py`, `signatures.py` | Implemented static rules; not an antivirus substitute |
| Quarantine metadata and release | `src/security/ice_box/quarantine.py` | SQLite; authenticated service routes in current source |
| Transport coupling | `src/security/warp_tunnel/tunnel.py` | Current worker imports WarpTunnel |
| Canonical service authentication | `Dimensionals/service_auth_fastapi.py` | Fail closed on missing INTERNAL_SECRET; previous doc-pack claims of unauthenticated writes are obsolete |
| Actual dynamic execution in guests | No guest/VM execution integration in current IceBox worker | NOT implemented |
| Automated runtime isolation and reversible VM snapshots | The agents/bots are role specifications | NOT proven |
| Existing standalone repo | `Trancendos/the-ice-box` | Archived, small, historically describes unrelated cold archive purpose |
| Compose production config | `docker-compose.production.yml` | Worker declared, but runtime, uptime, host and route NOT independently verified |

The Drive LOCATION-PROFILE.md lists port **8046**, not the old blueprint's 3026.

## 2. Confirmed delivery defects addressed in this proposal

1. **Dockerfile dependency closure:** `worker.py` imports `Dimensionals.service_auth_fastapi`, but its image originally omitted all `Dimensionals` source files. Dockerfile now copies the three specific auth modules/package files. This is an identified import-path defect; container build smoke testing remains outstanding.
2. **Quarantine durability:** `QuarantineStore` writes under the worker's `data/` working directory but production Compose lacked a persistent volume. The proposed `ice-box-quarantine` named volume mounts exactly that data directory and specifies `ICE_BOX_QUARANTINE_DB`. This prevents ordinary container replacement from removing the DB, but it is not an off-host backup.
3. Regression checks are added under `tests/test_ice_box_delivery.py`. They test package/Compose invariants; they are NOT a proof of successful Docker builds, real runtime auth or backup restore.

**Important operational gate:** The current auth dependency intentionally answers 503 if `INTERNAL_SECRET` is unset. Supply a unique non-empty secret through approved secret management before calling protected routes; do not commit it.

## 3. IceBox target capability decomposition

```text
Nexus / Bridge / WarpTunnel / internal user
    |
    v
Ingress gate: service authentication, content limits, provenance, hash,
             idempotency key, classification, immutable event ID
    |
    v
Static triage: existing regex + entropy engine
          --> optional ClamAV / YARA-X / file-type metadata adapters
    |
    +---- high risk / unknown --> quarantined artifact and metadata
    |                           encrypted storage / operator review
    |
    +---- authorised sandbox queue (DISABLED BY DEFAULT)
                                |
                                v
                        dedicated isolated host/VM
                        network denied by default
                        time / memory / I/O limits
                        clean snapshot before sample
                        verified reset after sample
                                |
                                v
                        behavior report, timeline,
                        rule matches, IoCs (non-executable)
    |
    v
Neonach decision support + Guardian policy gate
    |
    v
Observatory evidence / audit; Cryptex defensive IoCs
    |
    v
Human-reviewed release OR retention expiry; never auto-release on AI verdict
```

**No direct execution of untrusted samples in the application container.**
Do not claim containerisation alone constitutes malware isolation.

## 4. Data ownership, schema and chain of custody

Proposed minimal records (not yet migrated):

- `Case`: case_id, created_at, submitted_by_verified_identity, origin_service, request_trace_id, policy_version, state.
- `Artifact`: artifact_id, sha256, byte_length, mime_detected, encrypted_storage_locator, classification, ingress_time.
- `Scan`: scan_id, engine, engine_version, signature_version, verdict, score, elapsed_ms, findings_json.
- `SandboxRun`: run_id, host_id, image_digest, snapshot_id, egress_profile, started_at, ended_at, reset_verified, event_trace_id.
- `Evidence`: evidence_id, case_id, kind, content_hash, signed_manifest_locator, captured_at, source_agent.
- `ReleaseDecision`: decision_id, case_id, reviewer_identity_from_auth, second_approver_identity_if_required, reason, policy_version, timestamp.
- `RetentionPolicy`: rule_id, data_classification, retention_period, legal_hold, purge_method.

Suggested states: `submitted -> statically_scanned -> quarantined -> (sandbox_queued -> sandbox_running -> sandbox_review) -> [released | retained | purged]`. Any failed validation, host-reset failure, unknown state or external dependency outage defaults to quarantine and records the reason. Explicitly separate *metadata only* versus *binary payload stored*; today's `QuarantineStore` persists metadata, not captured malicious binary bytes.

## 5. Priority stack / comparative research

| Candidate | Intended contribution | Decision |
| --- | --- | --- |
| Current Tranc3 FastAPI + SQLite | Preserve existing service API, audit and single-worker state | KEEP |
| ClamAV | Open-source AV signature scan for suspicious files | P2: optional, isolated scan adapter |
| YARA-X | Typed signature rules and scan results; more efficient rule management | P2: optional, evaluate rule parity and licence |
| Assemblyline 4 | Modular file triage, case processing and evidence-oriented pipeline | STUDY before replacing existing routing (larger operational footprint) |
| CAPE Sandbox | Dynamic guest behaviour, unpacking and configuration extraction | P3: dedicated sandbox host only |
| DRAKVUF Sandbox | VM introspection and agentless behavioral inspection | P3: hardware-gated alternative |
| Original cuckoosandbox/cuckoo | Historical foundation referenced in CLAUDE.md | DO NOT adopt as maintained default: repository archived |
| Temporal workflow engine | Durable coordination of long-lived scan/review jobs | EVALUATE only if local simpler queue cannot meet retry/replay demands |
| NVIDIA acceleration | Optional AI-assisted classification or embeddings | NOT required for static scanning, prefer CPU-first |

Primary upstream references:
- https://github.com/cuckoosandbox/cuckoo
- https://github.com/CybercentreCanada/assemblyline
- https://cybercentrecanada.github.io/assemblyline4_docs/overview/how_it_works/
- https://capev2.readthedocs.io/en/latest/introduction/what.html
- https://github.com/CERT-Polska/drakvuf-sandbox
- https://github.com/virustotal/yara-x
- https://docs.clamav.net/manual/Usage

## 6. Ecosystem contracts

- **The Lighthouse/Guardian:** central identity, zero-trust admission and approval policy. Never trust free-text `reviewed_by` as a verified human identity.
- **The Nexus/Bridge/Pheromone:** hand-off only signed reference identifiers, hashes and content classification. Binary payload remains in guarded storage and is fetched only by authorised workers.
- **The Warp Tunnel:** current scan routing; eliminate double scanning and divergent verdict logic once shared contracts exist.
- **Cryptex:** share reviewed defensive indicators with Wazuh/MISP; do not auto-submit proprietary files to public threat-intelligence services.
- **The Observatory:** append structured events with trace ID, case ID, rule version and outcome; never log raw suspicious content or secrets.
- **The Library:** documentation, manifests, forensic records with provenance and access policy.
- **The Workshop/Lab:** isolated test fixtures and test outputs, not direct production malware execution.
- **Infinity Transfer Hub:** preserve three-stream separation (AI / users / files) and rejoin only at policy-controlled trust boundaries.

## 7. Requested apps, connectors and skills: fit-for-purpose screening

**Directly actionable via available connected tool surfaces:** Google Drive (source truth); GitHub (code and PRs); ArmorCodex (agent execution rules); Unblocked (read-only code context); Netlify/Sticklight (dashboard prototyping only, no malicious payload processing); DNS Inspector/Domain Scan (public domain posture); Gateway/SentinelX (authorised operator infrastructure); KERNEL (browser inspection); Lockbox (secure secret/file hand-off); omgskills (skill discovery); Werify (WhatsApp archive, low relevance).

**Conditional / discovery-stage:** Template Creator, Temporal, NVIDIA Skills, deep research, Servotab, Accoil Product Tracking, Awesome Maintainer Defense, C4 Investigator, Compound Engineering, CompText Evidence Platform, Bridge, Proxyman, Modal, Keystone, CrowdStrike Falcon/Fusion/Foundry. Availability as an independently usable connected app was not confirmed for each name. Use them only with an explicit, supported interface; do not infer that a name in an instruction means a connector is installed.

**Not fit for IceBox core security pipeline:** TokenOS dApp Builder (token/decentralised-app construction), Werify contact archive, general marketing/website builders, product analytics for non-security products.

Never pass raw threat samples, private source, telemetry, credentials or user content into an external plugin merely to make it easier to access.

## 8. Planned waves and acceptance gates

**Wave 0: Delivery repair (this draft PR).** Auth imports packaged, persistent DB volume, regression checks; build/run verification still required.
**Wave 1: Controlled Dev/UAT.** Non-prod Compose profile, genuine `GET /health`, authenticated `POST /scan`, quarantine and release with temporary DB, restart persistence, clean-room network testing.
**Wave 2: Security policy.** Workload identity, mandatory verified reviewer, two-person approval for critical release, signed audit, content/file size limits, bounded pagination, quotas and alerting.
**Wave 3: Threat-intelligence adapters.** ClamAV/YARA-X in opt-in isolated process; engine/rule version pinning, CI-safe synthetic test corpus, scoring calibration, false-positive review.
**Wave 4: Dynamic sandbox POC.** On designated offline-capable virtualization host, isolated networks, snapshot integrity, host protections, documented destruction and recovery; start with harmless simulated files. Do not introduce live threat samples before controls are proven.
**Wave 5: Ecosystem integration.** Nexus/Bridge/Infinity Transfer Hub contracts, Observatory and Cryptex delivery, offline replay, operator dashboard and recurring operational evidence.

### Minimum independent verification

- Test dependency closure and import `worker:app` *inside built container*.
- `docker compose -f docker-compose.production.yml config` succeeds with safe test env.
- Protected routes reject missing/wrong secret; approved caller can scan.
- Quarantine record survives container replacement and gets restored from an off-host backup.
- Dynamic sandbox tests (if deployed) prove deny-by-default egress and clean snapshot reset.
- The service is never marked “production-ready” without a reproducible run log, platform owner sign-off and rollback procedure.

## 9. Archive and migration guardrails

The existing `Trancendos/the-ice-box` repository is archived and its README describes cold storage; do not rename, unarchive or overwrite it by assumption. Keep the canonical application in `Tranc3` pending an explicit repository ownership/split decision.

The Google Drive `LOCATION-PROFILE.md` is generated; source-of-truth changes belong in generator inputs, then regenerate. Historical July doc-packs contain stale auth claims; this dated assessment supersedes them only where directly verified.

## 10. Skill discovery, 23 October 2026

The installed skills catalog was enumerated (**2,836** entries), then filtered against IceBox's engineering needs rather than treating every skill as a suitable runtime dependency.

| Discovered skill family | Concrete available skill | Use for IceBox |
| --- | --- | --- |
| Temporal | `temporal-developer`, `temporal-ops`, `temporal-cloud-setup`, `temporal-serverless` | Durable review workflows *if* a Temporal runtime is adopted. Installing a skill does not deploy a Temporal server. |
| NVIDIA | `nvidia-skill-finder` | Live NVIDIA skill-catalog routing for relevant GPU/classification acceleration. Not necessary for baseline static analysis. |
| Servotab | `servotab`, `plan`, `execute`, `debug`, `review`, `finish` | Bounded, risk-scaled implementation and verification discipline. |
| Awesome Maintainer Defense | `audit-repository-workflows` | Offline GitHub Actions and workflow trust-boundary audit when full repository checkout is available. |
| Compound Engineering | `ce-brainstorm`, plus related plan/review capabilities | Architecture alternatives, requirements and release planning. |
| Product Design | `index`, `audit`, `research`, `ideate`, `share` | Operator UX research and prototypes; this workflow requires Work mode. |
| Engineering Suite Build | `test-driven-development` | Regression-first delivery and reliable validation. |

An installed skill is an **instruction/workflow capability**, not proof of a deployed integration, reachable software service, or paid entitlement. Other named systems in the request require a documented connection before any live operation.

## 11. Automation integration increment — 2026-10-23

New software added **on this draft PR**, not necessarily deployed:

- `src/security/ice_box/automation_policy.py` provides a deterministic, pure-Python, conservative next-action planner. Clean/non-quarantined content receives a static allow advisory; suspicious/unknown or already-quarantined content requires human review; malicious content receives an urgent isolation-and-review advisory. No branch authorises automatic release or dynamic execution.
- `workers/ice-box-service/worker.py` returns `advisory_next_action` and `advisory_requires_review` from each existing `POST /scan` path. These fields are **advisory**, not an enforcement point: the pre-existing `allow` field retains its original scanner semantics. Clients should not treat an advisory as a clearance to process a threat.
- `integrations/icebox_temporal/activities.py` exposes a metadata-only, pure policy evaluation Activity. `worker.py` is an explicitly started, independent Temporal worker. There is no Temporal runtime or production worker configured by this PR, and the primary IceBox worker gains **no Temporal dependency**. If adopted, self-hosted Temporal Server and SDK versions must be checked against the chosen feature set (Standalone Activities requires SDK >=1.23.0 and Server >=1.31.0). Queue name: `icebox-metadata-policy-v1`. Do not submit raw content or customer data to Temporal history. A review workflow with Signal APIs is deferred until human identity and audit boundaries exist.
- `integrations/icebox_ycloud/alerts.py` constructs **but does not send** a queued static-template WhatsApp request for an urgent event only when the application is enabled, the recipient opted in, and the template is marked approved. Its default is disabled; the builder has no network transport, API key, YCloud account integration or webhook receiver. The template must contain no variables/media; do not put verdicts, case IDs or evidence in the message. The `externalId` is only a correlation ID, not an idempotency guarantee. An operator must independently verify approval, recipient eligibility and the YCloud provider account before real use. `POST https://api.ycloud.com/v2/whatsapp/messages` accepts a queued message, **not** a delivery confirmation. Do not automatically replay ambiguous submissions.
- `tests/test_ice_box_automation_policy.py` exercises policy outcomes, previously quarantined clean content, unknown and invalid verdict input, opt-in, template approval, safe request fields, and invalid identifiers using synthetic data. Offline tests were run separately; full GitHub CI and live integration evidence still apply.

### NVIDIA Skills routing

The official NVIDIA skill catalog was checked at `https://github.com/NVIDIA/skills`. **CPU-first** remains the deployment posture. Any GPU-based classification is opt-in research; do not upload malware, customer content or incident evidence to a hosted model without explicit security authorization. A future benchmark should compare exact same permitted synthetic corpus, measure false positives, inference latency, GPU memory, energy usage, and fallback parity with CPU analysis. No GPU runtime or CUDA package was added.

### Product Design workflow

Design intent: an IceBox operator experience with a dark-mode, mobile-friendly *quarantine list → case evidence → policy review → human release/retain/purge* journey. The Product Design plugin's full visual workflow is Work-mode-only; no interactive prototype, design screenshot, Figma artifact or published UI was produced by this source PR. The UX design must preserve the existing IAM boundary; a button must never be mistaken for proven authorisation.

### Verifiable limitations and approvals

- No external messages were sent, no provider keys were accessed, and no live API or VM malware execution was invoked.
- No autonomous release or production action is possible through the new automation policy or optional adapters.
- The metadata-only Temporal activity and the YCloud request builder are local artifacts, not a live end-to-end orchestration.
- Existing CI failures must be investigated; production readiness remains **OPEN** until full regression tests, Docker build, non-production acceptance, persistent-store restore and approvals pass.

### Source links

- Temporal standalone activity release: https://temporal.io/changelog/product-area/python-sdk
- NVIDIA verified skills: https://github.com/NVIDIA/skills
- YCloud queued message API: https://docs.ycloud.com/reference/whatsapp_message-send
- YCloud template lifecycle: https://docs.ycloud.com/reference/whatsapp_template-create
