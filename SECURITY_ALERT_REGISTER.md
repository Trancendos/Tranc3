---
title: "Security Alert Register"
category: Reference
last-reviewed: 2026-07-31
status: complete
---

# Security Alert Register

Every security-scanner finding that is not silently outstanding gets a row here,
with an explicit disposition and the reasoning behind it. The point is that a
suppressed alert stays *reviewable*: anyone can see what was decided, why, on
what evidence, and when it should be looked at again.

Read by `scripts/security_score.py` (`_register_complete()`), which contributes
12 points to the Security dimension of the production readiness scorecard.

## Dispositions

| Code | Meaning |
|---|---|
| **FIX** | Genuine finding, remediated. The change is in the repo. |
| **FP** | False positive. The scanner's pattern matched, the underlying condition does not hold. Justified below, not merely asserted. |
| **ACCEPT** | Genuine risk, consciously accepted with compensating controls and a review date. Owner named. |
| **SUPPRESS** | Genuine finding with no available remedy (no patched release exists). Not exploitable in our usage. Re-evaluated when upstream ships a fix. |

A disposition is not a dismissal. `FP` requires an argument for why the scanner
is wrong; `ACCEPT` requires controls and a review date; `SUPPRESS` requires both
a reason no fix is possible and a trigger for revisiting.

---

## Open entries

### SEC-001 — sentencepiece heap overflow

| Field | Value |
|---|---|
| **Disposition** | **FIX** |
| **ID** | CVE-2026-1260 (GHSA-38vq-g6vr-w8wf) |
| **Scanner** | Trivy / pip-audit |
| **Component** | `sentencepiece` |
| **Recorded** | 2026-07-31 |

Remediated by pinning `sentencepiece==0.2.1` in `requirements.txt`; the 0.2.1
release notes state explicitly that it addresses a heap overflow. The alert
still appears because Trivy's database has not yet recorded 0.2.1 as the fixed
version, so the residual finding is suppressed via `.trivyignore`. The
*vulnerability* is fixed; only the scanner's view of it is stale.

### SEC-002 — SQL injection vector in activity feed query

| Field | Value |
|---|---|
| **Disposition** | **FP** |
| **ID** | B608 (bandit, medium severity) |
| **Scanner** | bandit, via `scripts/pre_deploy_quality_gate.py` |
| **Location** | `src/relations/registry.py` — `RelationsRegistry.get_feed()` |
| **Recorded** | 2026-07-31 |

`get_feed()` builds a `WHERE` clause by joining fragments from a local `clauses`
list, then interpolates it into the query with an f-string. B608 fires on that
interpolation.

It is a false positive because **no caller value reaches the SQL text**.
`clauses` is local to the method and only ever receives three hardcoded string
literals — `"(actor_ai = ? OR target_ai = ?)"`, `"location = ?"` and
`"ts >= ?"`. Every user-supplied value (`ai`, `location`, `since_ts`, `limit`)
is bound through a `?` placeholder in `params`, and `limit` is additionally
bounds-checked (`if limit <= 0: raise ValueError`) before use. Verified by
reading every `clauses.append` in the file; there are no others.

Marked `# nosec B608` at the call site with the same reasoning inline. If a
future change appends a non-literal fragment to `clauses`, this disposition is
void and the suppression must be removed.

### SEC-003 — hostIPC on nanoservice deployments

| Field | Value |
|---|---|
| **Disposition** | **ACCEPT** |
| **ID** | hostIPC / shared `/dev/shm` (Trivy KSV / Kubernetes policy) |
| **Components** | `nsa-broker`, `shi-gateway`, `dnf-orchestrator` |
| **Owner** | Platform / The Citadel |
| **Accepted** | 2026-06-14 |
| **Next review** | 2026-09-14 |

Three nanoservice deployments set `hostIPC: true` with a `hostPath` volume for
`/dev/shm` (`flux/base/deployments.yaml` and
`src/nanoservices/igi_gitops/flux/base/deployments.yaml`). They coordinate over
POSIX shared memory, and without a shared IPC namespace the
broker/gateway/orchestrator pipeline does not function.

Accepted with compensating controls: non-root UIDs, dropped capabilities,
`allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault`, no
`privileged`, no `hostPID`, NetworkPolicy ingress restrictions, and no public
exposure of nanoservice ports. Full threat model and control list in
[`docs/HOSTIPC_RISK_ACCEPTANCE.md`](docs/HOSTIPC_RISK_ACCEPTANCE.md).

### SEC-004 — diskcache unsafe pickle deserialization

| Field | Value |
|---|---|
| **Disposition** | **SUPPRESS** |
| **ID** | CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v) |
| **Scanner** | Trivy / pip-audit |
| **Component** | `diskcache <= 5.6.3` — `workers/cache-service` |
| **Recorded** | 2026-07-31 |
| **Re-evaluate** | On any `diskcache` release above 5.6.3 |

There is no fixed version to upgrade to: 5.6.3 is the latest release and the
advisory lists no patched version, so this cannot be dispositioned `FIX`.

Not exploitable as used. `workers/cache-service/worker.py` opens the cache with
a hardened `_NoPickleJSONDisk` (a `JSONDisk` subclass) that serialises and reads
values as JSON *and* hard-rejects the base `Disk` pickle read paths — both
`MODE_PICKLE` values and non-raw keys — so a tampered or legacy pickle row
raises and is treated as a cache miss rather than reaching `pickle.load()`.
Verified with an adversarial `MODE_PICKLE` injection test. The finding persists
only because scanners match the package version and are blind to the serializer
actually in use. Suppressed via `.trivyignore`; drop the ignore when a patched
release ships.

---

## Closed entries

None yet. Entries move here when the finding is resolved at source — for
`FP` and `SUPPRESS`, that means the upstream scanner no longer reports it *with
every local suppression removed*; for `ACCEPT`, that the underlying requirement
has gone away.

The distinction matters because most entries here carry a local ignore
(`# nosec B608` for SEC-002, `.trivyignore` for SEC-001 and SEC-004). A local
ignore silences the scanner without changing the underlying condition, so a
green scan taken *with* those ignores in place is not evidence of anything. To
close an entry, drop its suppression and confirm the scanner is quiet on its
own — for a `SUPPRESS` that normally means a patched release shipped and the
pin moved; for an `FP`, that the scanner's rule stopped matching.

---

## Review cadence

Reviewed quarterly alongside `.trivyignore`, and whenever
`scripts/security_score.py` or the pre-deploy quality gate reports a new
medium-or-above finding. Any entry past its **Next review** date should be
treated as expired rather than still-accepted.
