# The Observatory — evidence-backed release hardening research

**Date:** 2026-10-23 · **Project:** PID-OBS / SRV-OBS-001  
**Scope:** zero-paid-runtime, self-hosted Tranc3 observability and audit paths.  
**State:** architecture review and implementation guidance; **not live-deployment evidence**.  
**Delivery:** [PR #1438](https://github.com/Trancendos/Tranc3/pull/1438) · [Tracking issue #1434](https://github.com/Trancendos/Tranc3/issues/1434).

## Executive decisions

1. **Retain the working SQLite-backed audit worker for now.** Continue a staged v1→v2 hash migration; require a tested backup and compatible rollback executable before deployment. Do not silently rewrite legacy events.
2. **Separate forensic audit storage from ordinary sampled telemetry.** Sampling or dropping noisy health traces is appropriate for diagnostic tracing, never for required forensic/audit events.
3. **Add protection *around* the hash chain.** A locally recomputable chain detects individual modifications, but privileged attackers can reconstruct history. Add independent, access-separated signed/time-stamped checkpoints, immutable backups where possible, audit-read access controls and alert escalation.
4. **Do not blindly upgrade the Collector.** `docker-compose.production.yml` currently pins `otel/opentelemetry-collector-contrib:0.96.0`, while `monitoring/otel-collector.yml` uses `logging` and `loki` exporters. Logging was removed from Collector v0.111.0 and the contrib Loki exporter from v0.131.0. A direct image bump without a configuration migration risks startup failure.
5. **Resolve repository-wide dependency consistency before feature expansion.** The version mismatch `opentelemetry-api==1.45.1` versus SDK/exporters `1.45.0` blocked pip installation; PR #1438 aligns the root API pin to `1.45.0` and keeps instrumentation `0.66b0`. CI must confirm.
6. **Do not introduce Temporal/NVIDIA/IoT complexity by default.** Temporal, GPU monitoring and SORACOM only earn a place with a measured reliability use case, licensed infrastructure, and operating budget. A local durable outbox is preferable for simple audit/event dispatch.

## Verified source and code matrix

| Finding | Evidence | Consequence | Planned gate |
|---|---|---|---|
| Audit v1 omitted severity/details from hash | `workers/audit-service/worker.py` | Historical records cannot prove those fields were unmodified | v2 migration; preserve legacy verification; note remaining risk |
| Audit worker has a runtime port split | Python default `8017` versus Docker command/exposure `8025` | Monitoring may target wrong port | Document deployed port, health endpoints, and checks |
| Root OpenTelemetry dependency mismatch | `requirements.txt` pins checked against `pip` error in PR CI | Pytest, merge gate and image build blocked | Pin lockstep, re-run CI |
| Collector has version-locked exporters | `monitoring/otel-collector.yml`, `docker-compose.production.yml` | New Collector might reject configuration | Rehearse new config against pinned target image before upgrading |
| Audit read/export surface needs authorization review | `workers/audit-service/worker.py` read endpoints | Potential data disclosure if exposed beyond private network | Inventory consumers, test fail-closed auth, redact exports |
| Event dispatch relies on synchronous writes | Audit POST calls `_connect`, `_chain_lock`, `BEGIN IMMEDIATE` | Cross-service replay requires idempotency and an outbox | Test repeated IDs, crashed publishers and deferred retries |
| Repo CI documentation topology is enforced | `docs/services/the-observatory/README.md` and CI register | New docs / tests require discoverable links and CMDB evidence | Regenerate register and link documentation |

## Primary sources (verified research)

- **SQLite WAL:** official WAL documentation describes checkpointing, persistence and the role of the `-wal` file in committed state. https://www.sqlite.org/wal.html
- **SQLite online backup:** use the backup API / `VACUUM INTO` rather than copying only the main database file while writers are active. https://www.sqlite.org/backup.html
- **SQLite synchronisation:** `FULL` in WAL mode adds a sync on commit and improves power-loss durability. https://www.sqlite.org/pragma.html#pragma_synchronous
- **OWASP Logging Cheat Sheet:** minimise PII/secrets, restrict log reads, protect integrity and monitor access. https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- **NIST SP 800-92:** logging management and planning; Revision 1 was still labelled an *initial public draft* in the official listing, so do not claim it is final. https://csrc.nist.gov/pubs/sp/800/92/r1/ipd
- **AWS transactional outbox pattern:** atomic database-write/outbox production plus idempotent consumers and ordered relay. Not an AWS dependency. https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
- **OpenTelemetry Collector logging exporter removal:** changed from `logging` to `debug` in v0.111.0. https://github.com/open-telemetry/opentelemetry-collector/issues/11337
- **OpenTelemetry contrib Loki exporter removal:** removal announced for v0.131.0; migrate to an OTLP exporter where supported. https://github.com/open-telemetry/opentelemetry-collector-contrib/releases/tag/v0.131.0
- **OTel Collector config:** validate against the exact distribution and release; consult installed components, not just syntax. https://opentelemetry.io/docs/collector/configuration/
- **W3C Trace Context:** propagate trace identifiers across services consistently. https://www.w3.org/TR/trace-context/
- **SLSA provenance:** secure build origin/attestations for later supply-chain hardening. https://slsa.dev/spec/v1.2/

## Prioritized delivery gates (no automatic merge)

**G0 — Correctness and reproducibility (current PR).**
- Full `pytest` on the checked-out repo; dedicated audit tests for corruption, v1/v2 migration, failure and restart; compare `/verify` against audit history.
- Confirm `requirements.txt` resolves and OTel consistency checker passes; Ruff, documentation topology, container build, image/SCA scans.
- Run affected audit worker Docker build with its named build contexts and compare startup/health.
- Show complete logs attached to one SHA. Do not infer success from a PR being mergeable.

**G1 — Forensic deployment hygiene.**
- Copy a real v1 database using SQLite's online backup API; keep independent restore point; migrate the *copy*; validate old/new records; rehearse rollback to a v2-aware build.
- Secure read/export APIs, redact sensitive event metadata, rate-limit ingress, bound retention and storage growth.
- Run both multi-process appends and fault injection (mid-transaction crash, WAL files retained, disk full, duplicate `event_id`, recover and reverify).

**G2 — Reliability.**
- Local outbox for downstream publishing in same database transaction, bounded retries and explicit dead-letter handling.
- Explicit idempotent consumer keyed by immutable `event_id` (with payload-hash validation on duplicate IDs); no automatic re-append of successful events.
- Emit machine-readable probe evidence; independently checkpoint chain tip and time; monitor gap/lag, failure counts and WAL size.

**G3 — Observability topology / UI.**
- Determine primary backend (Loki/Tempo/Prometheus versus SigNoz) from tested resource footprints, not preference.
- Design dashboards for service/dependency health, event ingest lag, audit chain integrity, trace linkage and incident chronology.
- Upgrade Collector only via a dual-config test on a pinned new release, replacing `logging` with `debug` and `loki` with compatible OTLP; validate/roll back.
- Route AI-assisted triage to The Watcher and The Scribe, with human approval for production modifications.

## Required proofs for LIVE designation

- Reachable authenticated API at documented endpoint and reproducible container startup.
- A known-good legacy-to-v2 migration and rollback restore, verified by full chain scan.
- Clean required CI including dependency, container, security and topology gates.
- Telemetry end-to-end from a real producer to at least one backend, with absence-of-data alerts.
- Continuous audit integrity probe with owner, alert sink, escalation route and observed successful check.
- Explicit approval to promote a pinned artifact, plus recorded deployment SHA and post-deployment checks.

**Do not claim immutable logging, exactly-once delivery, always-on monitoring, production-readiness, or 0-cost operation without evidence.** Runtime licence, resource, electricity, backup and storage costs still apply even if no recurring software licence is used.
