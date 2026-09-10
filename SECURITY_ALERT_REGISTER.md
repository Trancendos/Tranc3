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
| **Suppressed-in** | `.trivyignore` — the vulnerability is FIXED at the pinned 0.2.1; what is silenced is Trivy's stale view of which release carries the fix |
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


### SEC-006 — nltk model-artifact path-sandbox bypass, no patched release

| Field | Value |
|---|---|
| **Disposition** | **SUPPRESS** |
| **ID** | PYSEC-2026-3740 (GHSA-8mgp-746c-j5xp, CVE-2026-81726) |
| **Scanner** | pip-audit |
| **Component** | `nltk==3.10.3` — transitive via `safety` (`nltk>=3.9`), `requirements-security.txt` |
| **Recorded** | 2026-09-03 |
| **Owner** | The Guardian (Marcus Magnolia) — Security pillar, SUITE-SEC |
| **Next review** | 2026-12-03 |
| **Re-evaluate** | On the census resolving any nltk version other than 3.10.3; on the advisory naming a fixed version (a SUPPRESS then means declining an available fix); on nltk becoming a declared runtime dependency; or on any change to how this repository uses nltk — a second import site, an import outside `nltk.corpus`, an import that runs at import time (including a lazy import inside a function the module calls itself), or any call handing nltk a path (`nltk.data.load`, `download`, `find`, `retrieve`). **Every one of these is enforced by `scripts/check_disposition_premises.py`**, which reads the census output, the runtime manifests and every Python file, rather than relying on anyone remembering |

**No patched release exists — as resolved today.** The premise checker reads the census output and fails the gate the moment either half of this stops being true: a different resolved version, or a `fix_versions` entry on the advisory. 3.10.3 is the latest version on PyPI, and the GHSA
record's range is `introduced: 0, last_affected: 3.10.3` — every published release is
affected. There is deliberately **no Blocked-by row**: a fix is not merely out of
reach, it does not exist, and that distinction is what keeps this entry failing the
gate again the day one ships.

The advisory data is internally inconsistent and it is worth writing down why, because
the next person to check will hit the same contradiction. The PYSEC-2026-3740 record
lists `fixed: 3.10.3`, which reads as "already fixed". The GHSA record for the same
finding lists `last_affected: 3.10.3`, which reads as "not fixed". OSV's query endpoint
settles it — asked directly whether `nltk 3.10.3` is affected, it returns
GHSA-8mgp-746c-j5xp. pip-audit follows the same merged data and reports
`fix_versions: []`. Treat the GHSA range as authoritative here; the PYSEC `fixed` value
appears to record the release that was *expected* to carry the fix.

Not exploitable as used. The vulnerable surface is the model-artifact APIs —
`TransitionParser.train` and the related read/write flows — which treat
caller-controlled model paths as ordinary filenames even when NLTK path security is
enforced. This repository has exactly one nltk import, `src/search/query_expansion.py`,
and it is a lazy `from nltk.corpus import wordnet` inside a `try`/`except` that returns
`[]` on any failure. It calls `wordnet.synsets()` and reads lemma names — corpus
lookup, no model artifact, no caller-supplied path. nltk is also not a declared runtime
dependency (it is absent from `requirements.txt`), so on a production install that
import raises and the keyword-heuristic fallback runs instead.

---

### SEC-007 — fflate unzipSync ZIP64 infinite loop, fix unreachable behind web's peer graph

| Field | Value |
|---|---|
| **Disposition** | **ACCEPT** |
| **ID** | GHSA-px8p-9vwx-vf98 |
| **Scanner** | npm audit (census `web` surface) |
| **Component** | `fflate@0.4.8` — transitive via `posthog-js`, `web/` |
| **Blocked-by** | `posthog-js` declares `fflate: ^0.4.8` through its latest release (1.425.1), and `web/`'s peer graph cannot be re-resolved to apply an override — see below |
| **Recorded** | 2026-09-03 |
| **Owner** | The Guardian (Marcus Magnolia) — Security pillar, SUITE-SEC |
| **Next review** | 2026-12-03 |
| **Re-evaluate** | When `web/`'s React 18 / react-router 8 peer conflict is resolved; when `posthog-js` widens its `fflate` range; or as soon as `web/` gains any fflate **decompression** path (`unzipSync`, `unzip`, `decompressSync`, `gunzipSync`, `inflateSync`, `unzlibSync`) or begins processing archives from an untrusted source. **Enforced by `scripts/check_disposition_premises.py`**, not left to memory |

A patched release exists — fflate 0.8.3 — so this is `blocked`, not `SUPPRESS`, and the
**Blocked-by** row above is what produces that classification.

**Why the fix is unreachable.** `posthog-js` declares `fflate: ^0.4.8`, a range that
excludes every patched release, and it still does so at 1.425.1 (verified against the
registry, not assumed) — so bumping `posthog-js` does not help. The remaining route is
an `overrides` entry, the mechanism `web/package.json` already uses for four other
packages. It cannot be applied cleanly: `npm install` fails ERESOLVE on clean `main`
before any override is added, because `react-router@8.3.1` requires React 19 while the
app pins `react@^18.3.1` (and `react-router-dom` sits on a different major, 7.18.3).
Forcing it through with `--legacy-peer-deps` succeeds but re-resolves the entire tree:
**982 package versions and roughly 16,000 lockfile lines changed**, measured, to
remediate one moderate advisory. That trade was rejected — an unreviewable whole-tree
rewrite carries more risk than the finding does.

CI is unaffected by the ERESOLVE because `frontend-build.yml` runs `npm ci
--ignore-scripts`, which replays the committed lockfile rather than re-resolving peers.
`make frontend` (`Makefile:150`) runs plain `npm install` and therefore does not work
today. Resolving that peer conflict is the prerequisite for *any* automated dependency
remediation in `web/`, this one included.

**Not exploitable as used — at the version `web/` installs.** The advisory is an
infinite loop in `unzipSync` when parsing malformed ZIP64 archives. `posthog-js` uses
fflate only to compress *outbound* payloads, and the evidence for that is the shipped
code, not the dependency graph.

That evidence was read from **one version**, and the conclusion is scoped to it. The
table below was measured on `posthog-js@1.422.5` — the version `web/package-lock.json`
resolves — and says nothing about any other release. A different version ships different
code, so a bump invalidates the measurement rather than inheriting it. Because CI has no
`node_modules` to re-read the call sites from, the lockfile pin is what makes the scope
checkable: `scripts/check_disposition_premises.py` fails if `posthog-js` moves off
1.422.5 or `fflate` off 0.4.8, which is the signal to re-measure before this acceptance
is relied on again.

| Evidence | Measured on `web/node_modules/posthog-js@1.422.5` — the version `web/package-lock.json` pins, enforced by `scripts/check_disposition_premises.py` |
|---|---|
| Sites that import fflate at all | 2 — `lib/src/request.js:77` and `lib/src/extensions/replay/external/lazy-loaded-session-recorder.js:97`, both `require("fflate")` |
| Symbols those sites call | `gzipSync`, `strToU8`, `strFromU8` (`request.js:143`, `lazy-loaded-session-recorder.js:170`) — compression and UTF-8 conversion only |
| Decompression entry points reached | **zero** — no `unzipSync`, `inflateSync`, `gunzipSync` or `unzlibSync` anywhere in the package |

No attacker-supplied archive is ever unzipped by `posthog-js@1.422.5`, so the vulnerable
function is never called by the code `web/` actually ships today. Stated no wider than
that: this is a measurement of one version's call sites, not a general property of
`posthog-js`, and not a prediction about its next release.

An earlier revision of this entry cited "18 references each to `strToU8` and
`gzipSync`" and `npm audit`'s `effects: []`. Both are corrected here. The 18 counted
`.js.map` source maps alongside the 2 real call sites, inflating the figure ninefold
without adding evidence. And `effects: []` does not mean what it was read to mean: it
lists the packages npm reports as vulnerable *because of* this one, so an empty list
says only that no dependent was separately flagged — `posthog-js` does depend on
fflate, and always did. The direct call-site evidence above is what carries this
disposition; the audit field never did.


---

### SEC-008 — `esbuild` and `ws` in the Cloudflare workers' dev toolchain

Recovered from a second, divergent copy of this register that lived at
`wiki-content/Security-SECURITY_ALERT_REGISTER.md` until 2026-09-04. These
two entries existed only there, so the canonical register carried no record
of them at all.

| Field | Value |
|---|---|
| **Disposition** | **FIX** |
| **IDs** | GHSA-67mh-4wv8-2f99 (`esbuild`), GHSA-3h5v-q93c-6h6q (`ws`) |
| **Scanner** | npm audit — `cloudflare/*` surfaces |
| **Component** | Both transitive through `wrangler`/`miniflare`, a devDependency. Neither reaches the Workers runtime. |
| **Remedy** | `overrides: {"esbuild": "0.28.2", "ws": "8.21.3"}` in every `cloudflare/*/package.json` that depends on wrangler, and the three committed `package-lock.json` files regenerated so `npm ci` resolves those versions |
| **Recorded** | 2026-09-04 (finding itself predates this register entry) |
| **Owner** | The Guardian (Marcus Magnolia) — Security pillar, SUITE-SEC |
| **Next review** | 2026-12-04 |
| **Re-evaluate** | When wrangler ships a release whose own dependency ranges satisfy both advisories, at which point the overrides can be dropped |

**The correction this entry carries.** The lost copy stated the overrides were
present in *all* CF `package.json` files. They were in one of seven —
`trancendos-api-gateway`. The other six (`infinity-void`, `tranc3-ai`,
`notifications-rotation`, `queue-rotation`, `search-rotation`,
`storage-rotation`) declare the same `wrangler` devDependency and carried no
override, so six of the seven surfaces the record claimed to cover were
unremediated for as long as the claim stood. All seven carry the overrides as
of this entry.

This is why a duplicated register is worse than a single one that is
incomplete: the copy nobody read asserted a remediation that the copy people
did read had never heard of, and neither was checked against the packages.
`scripts/check_doc_duplication.py` now fails on a second document claiming to
be the same register.

**Second correction, 2026-09-05: this entry was filed as SEC-006, which is
already the nltk entry above.** Two open findings sharing an ID is the same
failure mode one level down — a reference to "SEC-006" resolves to whichever
entry the reader reaches first, and a disposition recorded against it lands on
the wrong finding. Renumbered to SEC-008, and `scripts/check_doc_duplication.py`
— already a blocking step in `ci.yml`'s Service Topology job — now fails on a
repeated entry ID, so the next one cannot be filed silently. It goes there
rather than in `scripts/security_score.py` on purpose: the score docks points,
and a register whose IDs collide needs to stop a merge, not lose twelve.

**Third: the overrides were floors, not pins, and the lockfiles predated
them.** `>=0.25.0` and `>=8.21.0` clear the advisories, but they are ranges,
and `deploy-cloudflare.yml` runs `npm ci` — which installs the resolved tree
in `package-lock.json` and does not re-resolve against `overrides` at all. All
three committed locks carried esbuild 0.28.1 and ws 8.21.0/8.21.3: versions
that happened to satisfy the ranges, so nothing forced them and nothing would
have reported it if a future `npm install` had picked something else. The
overrides are now exact pins matching the repository root (`esbuild 0.28.2`,
`ws 8.21.3`) and the three locks are regenerated against them, so the version
that deploys is the version the record names. `tests/test_doc_duplication.py`
asserts both halves — that each override clears the advisory floor, and that
every locked resolution does too.

### SEC-009 — path traversal in storage-service (the five CodeQL "high" nobody could name)

| Field | Value |
|---|---|
| **Disposition** | **FIX** |
| **ID** | `py/path-injection` (CodeQL, security-severity 7.5) x5 |
| **Scanner** | CodeQL Advanced (`.github/workflows/codeql.yml`, language `python`) |
| **Location** | `workers/storage-service/worker.py` — `_local_put`, `create_bucket`, `delete_bucket` |
| **Recorded** | 2026-09-10 |

**How it was found matters as much as what it was.** The PR check "CodeQL"
reported *5 high / 14 medium* on ten consecutive commits of PR #1150 and never
said which. The SARIF existed only inside the job: uploaded to the Security tab
and discarded. So a control was running, reporting, and blocking, and no
reader — human or agent — could act on it. That is the same defect class this
branch keeps finding elsewhere, and it was sitting on the estate's own security
gate.

Fixed by retaining the SARIF as a build artifact (commit `515247a1`), then
downloading it and reading the alerts. All five are `py/path-injection` at
severity 7.5, all in one file:

| Line (at `3622d448`) | Site |
|---|---|
| 268, 269 | `_local_put` — `LOCAL_ROOT / bucket / key` |
| 501 | `create_bucket` — `(LOCAL_ROOT / req.name).mkdir(...)` |
| 516, 517 | `delete_bucket` — `shutil.rmtree(LOCAL_ROOT / bucket)` |

**They were not introduced by that pull request.** The flagged code is
byte-identical on `main` at the merge base (`5c69056c`). GitHub attributed them
to the PR because the PR edited an earlier part of the same file, and its own
summary says so: *"Alerts not introduced by this pull request might have been
detected because the code changes were too large."* The branch could not have
gone green on this check without fixing pre-existing defects — which is what
this entry does.

**The finding is real, and the third site is the serious one.** `key` is
declared `{key:path}`, so FastAPI hands over the raw remainder of the URL:

- `PUT /buckets/b/objects/..%2f..%2fanything` — arbitrary file **write**.
- `POST /buckets {"name": "../x"}` — the name comes from a JSON body, so it
  carries separators freely; a directory is created outside the object root and
  a matching row is written to SQLite.
- `DELETE /buckets/..` — `shutil.rmtree` on the object root's **parent**.
  `_ensure_bucket` does not stop it, because the bucket row exists: step two
  created it.

**Remediation.** All three sites now route through `_contained()`, which wraps
`safe_join` from the shared core (`Dimensional/path_validation.py`) — the same
helper `src/admin_os/files_manager.py` already uses. No new copy of the
validator was vendored: the storage-service Dockerfile already mounts the
shared core at `/app/Dimensional/` via the SFSC named build context, so the
import resolves in the container and in the test tree alike. `create_bucket`
validates *before* the insert, so SQLite and the filesystem cannot disagree.

**Calibration.** Four regression tests in
`tests/test_workers_p3.py::TestStorageService`, each verified to fail against
the unfixed worker and pass against the fixed one. Getting them to fail took
three attempts, and the two failed attempts are recorded in the test comments
because both are traps a later reader would fall into:

1. A literal `../../` in the URL is removed by httpx before the request is
   sent; `%2e%2e` is percent-decoded to `.` and then removed the same way.
   Only `..%2f` survives to the server. Two of the first three tests passed
   against known-vulnerable code for this reason.
2. `{bucket}` matches `[^/]+` against an already-decoded ASGI path, so no
   encoding puts a separator into `bucket`. The reachable value is the bare
   `..`, which is one segment and quite enough for a recursive delete, so
   `delete_bucket` is tested by direct call rather than through the router.

The fourth test asserts that a normal nested key (`a/b/c.txt`) still round-trips,
because `{key:path}` exists precisely so keys can nest: a containment check that
rejected every key with a separator would have passed all three attack tests and
broken the worker.

**Next review.** Closes when a CodeQL run reports zero `py/path-injection`
alerts in this file. The retained SARIF artifact makes that checkable from
outside the Security tab:

```
gh run download <run-id> -n codeql-sarif-python
python scripts/immune_scan.py --merge sarif-results/python.sarif
```

Three `critical` alerts (9.8 `py/command-line-injection` in
`workers/tateking/worker.py`, and two 9.1 `py/partial-ssrf` in
`workers/notifications/worker.py` and `workers/vault-service/worker.py`) and
thirteen further `high` alerts are present in the same SARIF, outside the files
this pull request touched. They are **not** fixed here and are not adjudicated;
they are named so that the next reader starts from a list rather than from a
count.


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
