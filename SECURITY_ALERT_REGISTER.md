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

### SEC-005 — mcp session-hijacking / host-validation advisories, unreachable behind semgrep's exact pin

| Field | Value |
|---|---|
| **Disposition** | **ACCEPT** |
| **ID** | PYSEC-2026-3481, PYSEC-2026-3482, PYSEC-2026-3483 (CVE-2026-52869, CVE-2026-52870, CVE-2026-59950) |
| **Scanner** | pip-audit |
| **Component** | `mcp==1.23.3` — transitive via `semgrep`, `requirements-security.txt` |
| **Blocked-by** | `semgrep` exact-pins `mcp==1.23.3` through 1.172.0 — patched mcp releases exist and cannot be installed |
| **Recorded** | 2026-08-21 |
| **Owner** | The Guardian (Marcus Magnolia) — Security pillar, SUITE-SEC |
| **Next review** | 2026-11-21 |
| **Re-evaluate** | On every `semgrep` bump — see the check below |

Patched releases exist (1.27.2 and 1.28.1) and **cannot be reached**: every semgrep
release through 1.172.0 exact-pins `mcp==1.23.3`, not a range, so overriding it fails
pip resolution rather than producing a patched install. The census therefore classifies
these three as `blocked` rather than `fixable` — a fix exists, but not for us.

The **Blocked-by** row above is what produces that classification, and it is the only
thing that can. `scripts/vulnerability_census.py` reads blocked ids from entries
carrying that row alone, never from register membership: an entry dispositioned
`SUPPRESS` for want of any patch (SEC-004) must start failing the gate the moment
upstream ships one, and would silently stop doing so if being *documented* were enough
to earn `blocked`. All three ids are written in full for the same reason — the
census's id pattern matches `CVE-YYYY-NNNN`, so a shorthand like "52869 / 52870"
would register only the first.

Not exploitable as used. All three are bugs in mcp's *server* transports — session
hijacking and missing Host/Origin validation in the SSE, WebSocket and
experimental-tasks paths. `semgrep` is invoked here purely as a CLI SAST scanner from
pre-commit and CI; it never starts an mcp server, so none of those code paths execute.

**This entry exists because the analysis was in the wrong place.** The same reasoning
already sat in a comment block at the foot of `requirements-security.txt`, where it was
correct, current and invisible: `scripts/vulnerability_census.py` reads dispositions
from this register and from `SECURITY.md`, and nowhere else. A risk documented somewhere
the control cannot read is, to that control, undocumented — which is how three
knowingly-carried findings would have reported as open. The requirements comment stays
as installation guidance; this register entry is what makes the disposition count.

**Re-check on every semgrep bump:** `pip download --no-deps semgrep==<version>` and grep
its `METADATA` for `Requires-Dist: mcp`. If the pin has moved to a range, or to 1.28.1 or
above, drop this entry and take the fix.

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

### SEC-006 — nltk ReDoS vulnerability

| Field | Value |
|---|---|
| **Disposition** | **ACCEPT** |
| **ID** | PYSEC-2026-3740 (CVE-2026-81726) |
| **Scanner** | pip-audit |
| **Component** | `nltk==3.10.3` — transitive |
| **Blocked-by** | Version `3.10.4` is not available in our environments |
| **Recorded** | 2026-09-02 |
| **Owner** | The Guardian (Sentinel) |
| **Next review** | 2026-12-02 |
| **Re-evaluate** | On next requirements bump |

NLTK version 3.10.3 has a known ReDoS vulnerability. While a fix exists (3.10.4+), it cannot be currently resolved by `pip` in our CI environment constraints. The risk is accepted because `nltk` is only used locally via `query_expansion.py` and not exposed to arbitrary external regex compilation directly. Will upgrade once the package is resolvable.
