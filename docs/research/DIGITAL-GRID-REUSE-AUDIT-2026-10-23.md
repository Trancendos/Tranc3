# The Digital Grid — adjacent repository reuse assessment
**Date:** 2026-10-23
**Related review:** [Digital Grid research](./DIGITAL-GRID-DISCOVERY-2026-10-23.md) · [Issue #1431](https://github.com/Trancendos/Tranc3/issues/1431)

This document records a *targeted* code/README review of neighboring repositories. “Present in source” is **not** “deployed, tested, or suitable for direct adoption”.

| Existing repository | Current repository state | Found code | Reuse verdict |
| --- | --- | --- | --- |
| [the-observatory](https://github.com/Trancendos/the-observatory) | Public, archived; substantive source tree | [integrationHealthMonitor.ts](https://github.com/Trancendos/the-observatory/blob/main/integrationHealthMonitor.ts), [messageBus.ts](https://github.com/Trancendos/the-observatory/blob/main/messageBus.ts), [dependencyAnalyzer.ts](https://github.com/Trancendos/the-observatory/blob/main/dependencyAnalyzer.ts), Dockerfile and tests | **Reuse by selective porting/test**, not by reactivating a second full service |
| [infinity-adminOS](https://github.com/Trancendos/infinity-adminOS) | Public, active | [HiveService.ts](https://github.com/Trancendos/infinity-adminOS/blob/main/packages/hive/src/HiveService.ts), [InfinityOneService.ts](https://github.com/Trancendos/infinity-adminOS/blob/main/packages/infinity-one/src/InfinityOneService.ts) | Consider typed service/capability classification and IAM, but test interoperability first |
| [the-nexus](https://github.com/Trancendos/the-nexus) | Public, archived | README describes integration hub | A concept/reference, not yet evidence of useful active connector runtime |
| [chronos-ai](https://github.com/Trancendos/chronos-ai) | Public, archived | Minimal scheduling README | No demonstrated Temporal runtime to reuse from this review |
| Shared-core repository | Private, archived | Generic types/library README | Investigate current Tranc3 Dimensionals build context instead of adopting archived code |
| RepoFactory repository | Private, unarchived, very small | Only a README from permitted source inspection | No substantive reusable template generator demonstrated in that repository |

## Code-level findings
**Observatory — health-check mock risk (high priority).** In the existing integrationHealthMonitor.ts, GitHub, Notion, Linear, database and Stripe checks have TODO comments and return a constant **success: true** result. They cannot establish real connector health. Do **not** import or expose these probes as genuine engine readiness. Implement signed, rate-limited, timeout-bounded real capability probes with separate **configured / reachable / authenticated / operational** stages and test their failure cases.

**Observatory — message bus (prototype-grade).** messageBus.ts is a typed EventEmitter with capped in-memory history. Good event naming and message envelope inspiration, but no evidence there of durable queueing, acknowledgements, replay/idempotency, persistent tracing or process-restart recovery. Adopt only after those gaps are tested or use it for local noncritical UI notifications.

**Observatory — dependency analysis (selective).** dependencyAnalyzer.ts includes dependency graph and circularity types and filesystem scanning. Evaluate its parsing accuracy, fixed path assumptions and false positives with test fixtures before reusing in Grid's CMDB and Change Impact Compass.

**Infinity adminOS — routing taxonomy.** HiveService.ts defines typed data classifications, statuses, message priorities, routing strategies and service node metadata. These are useful vocabulary candidates for Grid's service/capability registry; do not equate them with an enforced security policy until a live authorization boundary and tests prove one. The broad README security/compliance statements are unverified by this targeted review.

**Archived vs active distinction.** An archived repository may contain valuable source but should be treated as a *library for audited extraction*, not automatically as a standalone dependency to re-deploy. Compare licence/provenance, tests, security, API shapes and ownership before porting.

## Actionable reuse shortlist
1. **P0:** Add a “no synthetic health” gate across all workflow adapters and connector cards. Unit tests must force each mocked check to fail when no live implementation is configured.
2. **P1:** Port Observatory event envelope into canonical Grid run/step events after schema compatibility tests; keep persistent events inside the chosen source of truth.
3. **P1:** Evaluate HiveService typed classification against Grid node authorisation; explicitly model identities, scopes, approvals and allowed egress.
4. **P2:** Use dependencyAnalyzer’s graph types as research input for a repo/service dependency viewer, with a representative fixture suite.
5. **P2:** Retain archived Nexus and Chronos concepts as historical references. Do not advertise them as connected or operational services.

**Next proof required:** An isolated end-to-end Grid workflow showing a working, actually contacted GitHub connector probe, an intentionally failing service probe, a persisted run and correct incident event; attach evidence to #1431.

**Read-only review completed:** No code from these repositories was copied, installed, executed or deployed here.
