# Cryptex security assurance — Phase 1 (review branch)

Tracking: #1441. Ownership: Cryptex / Renik. Scope: workers/cryptex and one Traefik ingress mapping.
Status: **draft integration; no production activation**.

## Why
An absent scanner must not return the same business result as a scanner that ran successfully. Before this change, the offline stub returned a negative finding and the worker marked it as completed. OpenVAS only registered a target and YARA without rules could report negative findings. Heterogeneous engines were treated as equivalents for unrelated scan types.

## Contract
- `completed` means a relevant detector performed a substantive operation and returned a boolean detection result. This is detection coverage, **not proof that the target is universally free of threats**.
- `inconclusive` means scanning was unavailable, only queued, unsupported, or did not run. API field `ok` becomes false. Consumers must treat this as **not cleared**, including at any automated release gate.
- `failed` represents attempts exhausted due to errors/timeouts; this also cannot authorise a release or remediation.
- The SQLite status column already stores text and does not require a table migration. Audit downstream clients, reports, queries and dashboards for the new status before release.
- A hit in the internal IOC database may positively confirm a threat, but an internal miss alone is not sufficient coverage.
- OpenVAS `create_target` is only target registration, not a completed scan. Full GMP task lifecycle, polling and findings ingestion remain a separate work item.
- Engine health indicates infrastructure responsiveness; an inconclusive/queued finding alone does not make a responsive engine unhealthy.

## Ingress and TLS
- The worker serves `/scan`, `/engines`, `/scans`, `/intel`; the production Traefik router matches `/cryptex`. A path-strip middleware is proposed but must be tested end-to-end with host, router/service priorities, authorisation and the actual Docker deployment.
- The API has a public `/health` route, but other endpoints preserve the existing fail-closed internal-secret guard. Evaluate whether the health route should be internal-only.
- `CRYPTEX_TLS_VERIFY` defaults to enabled. Trust an internal CA using the platform's certificate-store path. Insecure override requires explicit, time-limited development approval; never carry it silently into production.
- Docker Compose already sets `CRYPTEX_PORT=8053`; the code's fallback port is aligned. No network or provider credentials were accessed to verify trust roots.

## Governance and rollout
1. Run focused unit/integration tests with synthetic targets. Confirm no external calls and no actual vulnerability scan.
2. Run repository lint/security workflows, build worker image, run Dev/UAT with mock MISP/Wazuh/OpenVAS and Traefik route smoke tests. **Not yet performed.**
3. Audit all consumers of status and `ok`, especially Infinity Node, Observatory, The Lab and CI release gates.
4. Require ownership and written approval before active external scanning, network blocking, remediation, secrets rotation or production promotion.
5. If needed, roll back by reverting the PR (including Traefik label and API status changes); examine any result records written with the new `inconclusive` value before reverting clients.

## Deferred
Durable Temporal triage, KEV/EPSS correlation, NVIDIA acceleration, YCloud alerts, live ingestion, and privileged remediation remain unconnected to production; they are not implied by this PR.
