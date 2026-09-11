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

### SEC-005 — mcp session-hijacking / host-validation advisories, unreachable behind semgrep's exact pin — **RETIRED 2026-09-11**

| Field | Value |
|---|---|
| **Disposition** | **RETIRED** (upstream fix landed; not an accepting disposition) |
| **ID** | PYSEC-2026-3481, PYSEC-2026-3482, PYSEC-2026-3483 (CVE-2026-52869, CVE-2026-52870, CVE-2026-59950) |
| **Scanner** | pip-audit |
| **Component** | `mcp==1.23.3` — transitive via `semgrep`, `requirements-security.txt` |
| **Recorded** | 2026-08-21 |
| **Retired** | 2026-09-11 |
| **Owner** | The Guardian (Marcus Magnolia) — Security pillar, SUITE-SEC |

**This entry is retired.** The three CVEs it accepted are fixed upstream and are no longer present in what is installed.

**Why this risk was accepted.** Every semgrep release through 1.172.0 exact-pinned `mcp==1.23.3`, not a range, so overriding it failed pip resolution rather than producing a patched install. The census classified these three as `blocked` rather than `fixable` — a fix existed, but was unreachable. All three are bugs in mcp's *server* transports — session hijacking and missing Host/Origin validation in the SSE, WebSocket and experimental-tasks paths. `semgrep` is invoked here purely as a CLI SAST scanner from pre-commit and CI; it never starts an mcp server, so none of those code paths execute.

**Why it is retired now.** Semgrep upgraded from 1.173.0 to 1.177.0, and semgrep 1.173.0 / 1.175.0 / 1.177.0 all declare `Requires-Dist: mcp==1.29.0`. The estate stopped installing the vulnerable version, and mcp 1.29.0 has zero advisories (re-measured 2026-09-11 against the OSV API). Nothing was suppressed to close this — the pin moved and the advisory count went to zero.

**The process failure.** This entry named its own re-check condition: *"Re-check on every semgrep bump."* The bump to semgrep 1.173.0 landed without that re-check, so the entry went on describing a dependency the estate had already stopped installing. A stale accepted risk reads exactly like a live one, which is why this is retired in place with its measurement rather than deleted. An accepted-risk entry that names its own re-check condition is only as good as someone performing it.

**Why the Disposition word is `RETIRED` and not `ACCEPT — RETIRED`.** The first attempt at this retirement wrote `**ACCEPT** — **RETIRED** (upstream fix landed)`, which reads correctly to a human and did nothing at all to the gate. `accepted_risk_register.registered_ids()` matches the **first word** of the Disposition row against `ACCEPTING_DISPOSITIONS = ("ACCEPT", "SUPPRESS")`, so all six ids stayed in the accepted set: the census would have classified them `accepted`, and `.trivyignore` governance would have gone on licensing their suppression. Had any of them resurfaced — mcp re-pinned, or another dependency pulling the vulnerable version — the production gate would have passed in silence.

That is the same defect as the stale entry itself, one level up: a retirement that reads retired and behaves accepted. Measured after the change, `registered_ids()` returns none of the six. A disposition here is a machine-read token, not prose; retiring an entry means changing that token to one outside `ACCEPTING_DISPOSITIONS`, and `tests/test_vulnerability_census.py::TestRetiredEntries` now holds that property so the next retirement cannot repeat this. Raised by cubic on PR #1207.

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
`safe_join` from the shared core (`Dimensionals/path_validation.py`) — the same
helper `src/admin_os/files_manager.py` already uses. No new copy of the
validator was vendored: the storage-service Dockerfile already mounts the
shared core at `/app/Dimensionals/` via the SFSC named build context, so the
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
this pull request touched. They were named here so that the next reader starts
from a list rather than from a count. All three are adjudicated below, as
**SEC-010**, **SEC-011** and **SEC-012** — but see **SEC-013**, which records
that adjudicating a finding and clearing its alert turned out to be two
different things, and that this register said the first while meaning the
second. The `high` alerts remain open.


---

### SEC-010 — the caller picked the vault's API path (`py/partial-ssrf`, 9.1)

| Field | Value |
|---|---|
| **Disposition** | **FIX** |
| **ID** | `py/partial-ssrf` (CodeQL, security-severity 9.1) |
| **Scanner** | CodeQL Advanced (`.github/workflows/codeql.yml`, language `python`) |
| **Location** | `workers/vault-service/worker.py:153` — `OpenBaoClient._request` |
| **Recorded** | 2026-09-11 |

The first of the three `critical` alerts SEC-009 could only name. Taken first
because it is **The Void**: the service that holds every secret on the platform.

**What it was.** One line built the URL:

```python
url = f"{self.addr}/v1/{path.lstrip('/')}"
```

`path` reaches it from `body.key` on `POST /secrets` — a public create endpoint
whose key field carried a length bound (`min_length=1, max_length=200`) and no
charset at all. `create_secret` mirrors to OpenBao as
`put_secret(f"tranc3/{body.key}", ...)`, which becomes
`secret/data/tranc3/{key}`, which becomes the URL above. So the caller chose
which OpenBao API path this worker called, and the call carries
`X-Vault-Token`.

**Measured, not assumed.** Against a local server recording the raw request
line, urllib normalises nothing:

| `key` | request line emitted |
|---|---|
| `normal-key` | `POST /v1/secret/data/tranc3/normal-key` |
| `../../../../sys/seal` | `POST /v1/secret/data/tranc3/../../../../sys/seal` |
| `../../../../auth/token/create` | `POST /v1/secret/data/tranc3/../../../../auth/token/create` |
| `x?list=true` | `POST /v1/secret/data/tranc3/x?list=true` |
| `x#frag` | `POST /v1/secret/data/tranc3/x` |
| `x y` | `InvalidURL` raised by `http.client` |

`..` walks out of `secret/data/` into `sys/` and `auth/`; `?` appends a query
the caller wrote; `#` truncates the path. A space is the only thing stdlib
already refused. Whether OpenBao resolves the dot-segments itself or redirects
to the cleaned path is not the question the fix turns on — either way the
request that leaves this worker is one the caller composed.

**Remediation.** A single `_vault_path()` checks every segment and refuses `.`,
`..`, empty segments, and anything outside `^[A-Za-z0-9][A-Za-z0-9._-]*$`,
then percent-encodes what remains. Encoding alone would not have been enough:
`.` is an unreserved character, so `%2e%2e` and `..` mean the same thing to a
server that resolves dot-segments, and quoting would have preserved the
traversal faithfully.

It is applied in **two** places, deliberately:

1. `_request` — so every path through the client is checked once, centrally.
   `put_secret` and `get_secret` are today's callers; the next one will not
   have to remember, which is the only version of this guard that stays true.
   A refusal returns `None` like every other failure mode there, so a rejected
   mirror degrades to the AES-GCM SQLite backend rather than 500ing.
2. `SecretCreate.key` — a `field_validator` calling the same function, so the
   attempt fails loudly with a 422 instead of silently not mirroring. It adds
   exactly one rule the path builder does not have: the key must already equal
   its canonical form. `_vault_path` strips surrounding slashes, because a
   caller writing `/sys/health` means the same path; a secret *key* is
   different, and `/db-password` and `db-password` would otherwise be two
   SQLite rows mirroring onto one OpenBao path.

One function, two call sites, so the boundary and the URL cannot drift about
what "safe" means.

**Calibration.** Nine assertions in
`tests/test_workers_p4.py::TestVaultService` — eight parametrised key cases and
one direct client test. **All nine were run against the unfixed worker and all
nine failed**; all nine pass against the fixed one, alongside the file's other
100 tests. The direct test covers the structural half: `put_secret` returns
`False` and `get_secret` returns `None` for a traversal path without any
request leaving the process, and no OpenBao is needed to reach that refusal.

**Next review.** Closes when a CodeQL run reports zero `py/partial-ssrf`
alerts in this file. The second `py/partial-ssrf` is **SEC-011** below and the
9.8 `py/command-line-injection` is **SEC-012**.


---

### SEC-011 — the webhook guard checked the half that could not reach the path (`py/partial-ssrf`, 9.1)

| Field | Value |
|---|---|
| **Disposition** | **FIX** |
| **ID** | `py/partial-ssrf` (CodeQL, security-severity 9.1) |
| **Scanner** | CodeQL Advanced (`.github/workflows/codeql.yml`, language `python`) |
| **Location** | `workers/notifications/worker.py:443` — `NotificationDispatcher.dispatch_webhook` |
| **Recorded** | 2026-09-11 |

Second of the three `critical` alerts named in SEC-009.

**This one had already been worked on, which is what makes it interesting.**
The function carries real SSRF defence: `validate_webhook_url` blocks private
IPs, metadata endpoints and plaintext; a required allowlist supplies the
connection host from config rather than from the caller's URL, with a comment
explaining precisely why. The outbound **host** genuinely is not
attacker-chosen.

What was left is the request **target**, which the caller writes in full — and
the guard covering it had two defects, the second existing only because of the
first.

**Defect 1 — the `?` was missing.**

```python
_safe_path += _p.query or ""
```

Measured:

| webhook URL | target put on the wire |
|---|---|
| `https://allowed.example/hook?token=abc123` | `POST /hooktoken=abc123` |
| `https://allowed.example/hook?a=1&b=2` | `POST /hooka=1&b=2` |

A signed webhook — `?token=...`, the commonest shape there is — has never
reached its endpoint. Silently, because `dispatch_webhook` returns
`_resp.status < 400`: the 404 that came back read as *the remote rejected it*
rather than *we asked for the wrong thing*. A security review would not have
found this, and neither would a monitoring dashboard; only reading the line did.

**Defect 2 — the traversal check read the wrong half.** It decoded and
inspected `_p.path`. The query got a charset allowlist instead, and that
allowlist permits `.` and `%`. Because of defect 1 the query landed *in the
path*:

| webhook URL | target put on the wire |
|---|---|
| `https://allowed.example/hook?..%2f..%2fadmin` | `POST /hook..%2f..%2fadmin` |
| `https://allowed.example/hook/../admin` | rejected — the guard that worked |

So the control decoded the half of the URL that could not reach the path, and
did not decode the half that did. That is this engagement's defect class once
more: present, running, reporting, and pointed at the wrong thing.

**Remediation — one line, at the root.** The target is now assembled with
`urlunsplit`, so the `?` is structural rather than something a future edit has
to remember. Once the separator is there the query cannot reach the path at
all, which closes defect 2 by removing its mechanism instead of adding a second
runtime check for it.

**What was deliberately NOT done, and why it is recorded.** The obvious next
move is to also reject a query whose decoded form contains `/`. It was written,
measured, and removed: with the separator present a `/` in a query value is
harmless, and refusing `?x=%2Fetc` would break callers to defend against a
defect that no longer exists. A guard that cries wolf on working code costs a
gate its credibility as fast as a miss does. The belt-and-braces against
reintroducing defect 1 is a regression test, not a rejection of valid input.

**Calibration.** Four tests in
`tests/test_workers_p1.py::TestNotificationsWebhookTarget`, which replace
`HTTPSConnection` and assert on the target this worker *composed* rather than on
what any server made of it. **Three of the four fail against the unfixed
worker.** The fourth — path traversal still refused — passes against both, and
is labelled as such in the test itself: it is a non-regression test for the
guard the fix left alone, not a regression test for the fix. Saying which is
which is the difference between a calibrated suite and a hopeful one.

**Next review.** Closes when a CodeQL run reports zero `py/partial-ssrf`
alerts in this file. The last of the three criticals is **SEC-012** below.


---

### SEC-012 — the input file was the injection (`py/command-line-injection`, 9.8)

| Field | Value |
|---|---|
| **Disposition** | **FIX** |
| **ID** | `py/command-line-injection` (CodeQL, security-severity 9.8) |
| **Scanner** | CodeQL Advanced (`.github/workflows/codeql.yml`, language `python`) |
| **Location** | `workers/tateking/worker.py:433` — `run_ffmpeg_job` |
| **Recorded** | 2026-09-11 |

Last of the three, and the **highest-scored finding in the estate's SARIF**.

**Why `shell=False` was not the answer.** The call is
`subprocess.run(cmd, ..., shell=False)` with `cmd` built as a list, and the
params that look dangerous are already sanitised: `_safe_ts` pins timestamps to
`^[\d:.]+$`, `_safe_int` clamps CRF and dimensions. Someone had thought about
shell metacharacters and about the numeric params, and had got both right.

There is no shell to inject into. What is injected is an **argument**, and the
argument is the input file.

**The path.** `ClipIn.file_path` is a free-form `Optional[str]` on a JSON body:

```
POST /clips  {"title": "x", "file_path": "/etc/passwd"}   ->  201 Created
POST /jobs   {"clip_id": <that>, "operation": "extract_audio"}
POST /jobs/<id>/run                                       ->  ffmpeg -i /etc/passwd
```

That 201 is measured, not inferred — it is the first assertion in
`tests/test_tateking_media_containment.py::TestClipBoundary`, and it is what
the unfixed worker answers.

The value went to SQLite unexamined and came back out as `ffmpeg -i
<input_path>`. The only check between the two was:

```python
if not input_path or not Path(input_path).exists():
```

**`exists()` is a check that the attacker's chosen file is *there*.** It is the
opposite of a containment check, and it reads exactly like one. Any file on the
host ffmpeg can decode could be transcoded into the served media directory and
fetched; any it cannot gets up to 1000 bytes of ffmpeg's stderr returned in the
500 body.

**Remediation.** `_contained_media()` resolves the value under `MEDIA_DIR` via
`safe_join` from the shared core — the **same helper SEC-009 used for
storage-service**, deliberately, because a second copy of a path validator is a
second thing to keep right. `workers/tateking/Dockerfile` already mounts the
shared core at `/app/Dimensionals/` through the SFSC named build context, so
nothing new had to be vendored.

Applied in two places, the pattern SEC-010 also used:

1. `POST /clips` — a 400 the caller can read, so they learn why now rather than
   when a job they queued fails later.
2. `run_ffmpeg_job` — re-derived from the row rather than trusted. **The
   database is not a trust boundary**: rows predate the boundary check, and a
   future writer to `clips` would not inherit it.

Two accepted shapes, and both are deliberate. An absolute path *already under*
the media root is accepted and rewritten as relative before the join, because
that is a shape existing rows legitimately have — refusing it would have made
the guard a breaking change dressed as a security fix. And `file_path` stays
optional, because a clip may be URL-only.

One property comes free: a resolved path is always absolute, so no value
reaching argv can begin with `-` and be read by ffmpeg as an option.

**Calibration.** 16 tests in `tests/test_tateking_media_containment.py`, and
the two halves calibrate differently, which the file says out loud:

- The 12 unit tests fail against the unfixed worker because `_contained_media`
  does not exist there. True, and a **weak** proof — recorded as weak.
- The 4 boundary tests go through the HTTP API. Two fail non-trivially: the
  unfixed worker answers **201** to `/etc/passwd` and to
  `../../../../etc/passwd`. Two pass against both worker versions on purpose —
  a clip inside the root, and a clip with no `file_path` — because containment
  is not a ban on clips, and a guard that broke either would have passed every
  attack test while breaking the service.

The symlink case is covered by `safe_join` resolving before comparing, and is
tested anyway: *"we use safe_join"* is a claim, and the test is the measurement
behind it.

**Next review.** Closes when a CodeQL run reports zero
`py/command-line-injection` alerts in this file. With this entry all three
`critical` alerts from SEC-009's SARIF are adjudicated; the thirteen `high`
are not.


---

### SEC-013 — a fixed vulnerability and a cleared alert are not the same fact

| Field | Value |
|---|---|
| **Disposition** | **FP (scanner limitation)**, plus one real correction |
| **ID** | `py/partial-ssrf` 9.1 and `py/command-line-injection` 9.8, both persisting after their fixes |
| **Scanner** | CodeQL Advanced |
| **Recorded** | 2026-09-11 |

**The correction first.** After SEC-010, SEC-011 and SEC-012 landed, this
register and a pull-request comment both said the three critical alerts were
adjudicated. Measured against the retained SARIF for `9990dd07` — the run taken
*after* all three fixes — CodeQL still reported **2 critical**:

| Alert | Location at `9990dd07` |
|---|---|
| `py/command-line-injection` 9.8 | `workers/tateking/worker.py:519` |
| `py/partial-ssrf` 9.1 | `workers/vault-service/worker.py:221` |

One of the three had genuinely cleared: SEC-011's webhook alert is gone, which
is what took the count from 3 to 2. The other two had not, and nothing in this
repository had checked. The claim was made from the fixes and the tests, not
from the scanner — which is the estate's own defect class, committed by the
work that exists to name it. **A fix is evidence about the code. Only a scan is
evidence about the alert.**

**The two remaining alerts are different from each other, and the flows say so.**
Reading `codeFlows` out of the SARIF rather than trusting the line number:

*tateking* — the reported flow is **not** the one SEC-012 fixed:

```
worker.py:396  job_id          <- the source
worker.py:438  output_path     <- MEDIA_DIR / f"job_{job_id}_output"
worker.py:462  cmd
worker.py:519  subprocess.run(cmd)
```

`input_path` does not appear. SEC-012's flow cleared; this is the **output**
path, and its source is `job_id`, declared `job_id: int` on the route. FastAPI
answers 422 to anything that is not an integer, so no separator and no leading
`-` can reach it. CodeQL does not model that coercion. Fixed by making the
invariant explicit and local — `f"job_{int(job_id)}_output"` — which costs one
call, states the constraint where it matters instead of five frames up in a
decorator, and is a conversion the scanner can see. A guard only the framework
knows about is one the next reader has to take on trust.

*vault-service* — the reported flow runs straight **through** the fix:

```
worker.py:574  body            <- POST /secrets
worker.py:582  f"tranc3/{body.key}"
worker.py:206  path
worker.py:154  path            <- _vault_path()
worker.py:195  "/".join(quote(seg) for seg in segments)
worker.py:215  safe_path
worker.py:219  url
```

CodeQL traced every segment check and the percent-encoding and kept the taint,
because a helper that *raises* on bad input is not something it models as a
sanitiser. There is no defect here to fix: nine calibrated assertions cover it
and the boundary answers 422. **The vulnerability is fixed; the alert is not
cleared.** A post-condition (`_SAFE_BUILT_PATH.fullmatch`) now asserts the whole
constructed path rather than only its parts — worth having on its own terms,
since "each part is safe" and "the parts were combined" is not the same claim as
"the result is safe" — but whether it clears the alert is **unverified until CI
runs**, and is written here as unverified rather than asserted.

**What was deliberately not done.** A CodeQL model pack declaring `_vault_path`
and `safe_join` as sanitisers is the durable answer, and it is not in this
change. CodeQL cannot be run on this machine, so the pack could not be
calibrated — and shipping an uncalibrated control that tells a scanner to stop
looking at something is the exact move this branch has refused everywhere else.
It is named here as the next step rather than attempted blind.

**VERIFIED, 2026-09-11.** Read from the retained SARIF for `bc074c33`
(run 34584659158), not from a summary line:

```
CRITICAL: 0        (3 at the start of this work, 2 at 9990dd07)
HIGH:    13        (14 at 9990dd07)
```

Both fixes cleared their alerts, **including the one recorded above as
unverified**: `_SAFE_BUILT_PATH.fullmatch` did clear vault-service's
`py/partial-ssrf`. That is worth stating plainly because the entry hedged it,
and the hedge was the right call at the time — the outcome does not
retrospectively justify claiming it early. The `high` that this work itself
introduced (`tateking:79`) is also gone.

The CodeQL model pack for `_vault_path` and `safe_join` is no longer needed for
these two. It remains the durable answer for SEC-014's pair, which persist.

**Next review.** Reopens if any `critical` returns.


---

### SEC-014 — the SQL allowlist held, and still enforced less than it said (`py/sql-injection`, 8.8)

| Field | Value |
|---|---|
| **Disposition** | **FP** for the alert; **FIX** for the defect it led to |
| **ID** | `py/sql-injection` (CodeQL, security-severity 8.8) ×2 |
| **Scanner** | CodeQL Advanced |
| **Location** | `src/vector/adapter.py:436`, `:446` — `_PgvectorBackend._bootstrap` |
| **Recorded** | 2026-09-11 |

First of the `high` band, and the highest of them.

**The alert is a false positive, and the flow says why.** Read from the SARIF
rather than the line number, the taint runs from a request body to a *table
name*:

```
src/routers/search_api.py:259   req            <- POST /ingest
src/routers/search_api.py:267   req.collection
src/search/hybrid.py:79         vector_collection
src/vector/adapter.py:413       collection
src/vector/adapter.py:416       raw_table      <- f"vec_{collection...}"
src/vector/adapter.py:430       self._table
src/vector/adapter.py:436       f-string in CREATE TABLE
```

A table name cannot be a bound parameter, so this has to be an identifier
allowlist — and there already is one, with `# noqa: S608 — identifier
validated` beside it. Measured against every injection shape:

| `collection` | derived table | accepted? |
|---|---|---|
| `x'; DROP TABLE t; --` | `vec_x'; drop table t; __` | no |
| `x"y` / `x;y` / `x(y)` / `a b` | — | no |
| `abc\nDROP TABLE t` | — | no |
| `docs`, `my-docs`, `Notes` | `vec_docs`, `vec_my_docs`, `vec_notes` | yes |

The allowlist holds. CodeQL does not model a raising validator as a sanitiser —
the same limitation SEC-013 records for `_vault_path`.

**But the validator was wrong anyway, and that is the finding.**

```python
_SAFE_IDENT = __import__("re").compile(r"^[a-z][a-z0-9_]{0,62}$")
...
if not self._SAFE_IDENT.match(raw_table):
```

`$` matches at the end of the string **or immediately before a trailing
newline**, so:

```
re.compile(r"^[a-z][a-z0-9_]{0,62}$").match("vec_abc\n")      ->  MATCHES
re.compile(r"^[a-z][a-z0-9_]{0,62}$").fullmatch("vec_abc\n")  ->  None
```

A validator whose whole job is "only these characters" admitted one its
character class forbids.

**Seven of them, and none exploitable.** A sweep found the same combination in
`src/vector/adapter.py`, `src/database/encrypted_sqlite.py` (also a SQL table
name), `workers/vault-service/worker.py` (added by SEC-010 the day before),
`workers/tateking/main.py`, `workers/tateking/worker.py` (ffmpeg argv),
`src/dvms/native_ecosystems.py` and `scripts/check_trivyignore_governance.py`.
Checked individually: a newline is SQL whitespace, is percent-encoded before it
reaches a URL, and is an ordinary character inside a list argv with no shell. So
this is **not seven vulnerabilities** — it is seven controls whose stated
contract is not the one they enforce, each one character from correct, with
nothing anywhere that would notice if one of them became exploitable. All seven
now use `fullmatch`.

**The guard, and the calibration that failed first.**
`scripts/check_anchored_validators.py` fails CI on an anchored `^...$` pattern
used with `.match(`, exempting `re.MULTILINE` compiles and anything carrying an
explicit `# anchored-ok: <reason>`. It found sixteen more call sites: seven
genuine line parsers, now exempted with a written reason, and nine further
validators, now `fullmatch`.

Its first version **could not see the validator it was written for.** It matched
the literal `re.compile(`, and `adapter.py` writes `__import__("re").compile(`.
Planting `.match()` back left the guard green — caught only because planting the
defect is mandatory here, not optional. Now calibrated against three of the
seven: each plant fails the guard and names the file, and the restored tree is
clean. That failure is kept as a test.

**Calibration.** 13 tests in `tests/test_anchored_validators.py`: the language
behaviour itself (so the guard becomes obsolete loudly if Python ever changes),
the allowlist holding against six injection shapes, the newline it used to
admit, legitimate collection names still working — because a guard that broke
those would pass every attack test while breaking the feature — and the
guard's blindness case.

**Next review.** The two `py/sql-injection` alerts were predicted to persist,
and **measured at `bc074c33` and again at `6fae9678`, they did** — still reported at `adapter.py:436`
and `:446`. The prediction holding is the useful part: it confirms the shape is
an unmodelled sanitiser rather than an unfixed defect, which is what
distinguishes this entry from a vulnerability. A CodeQL model pack declaring
`safe_join` and the identifier allowlists as sanitisers is the durable answer,
and needs a machine that can run CodeQL to calibrate it.


---

### SEC-015 — the validator was the sink (`py/path-injection`, 7.5)

| Field | Value |
|---|---|
| **Disposition** | **FIX** |
| **ID** | `py/path-injection` (CodeQL, security-severity 7.5) ×2 |
| **Scanner** | CodeQL Advanced |
| **Location** | `src/personality/spawner.py:54`, `:68` — `_resolve_output_base` |
| **Recorded** | 2026-09-11 |

**This entry started as a claim to check, not a defect to fix.**
`.github/workflows/codeql.yml`'s header said:

> Previous CodeQL alerts (#30-#41) were fixed in PR #29 by replacing
> `_assert_under_base()` with `validate_path()` in spawner.py.

`validate_path()` appears nowhere in `src/personality/spawner.py`. The file uses
`safe_join()` and its own `_resolve_output_base()`. The only two surviving
mentions of `_assert_under_base` in the tree are that header and a list of
recognised guard names in `Dimensionals/security_automation/scanner.py`. So the
header described a fix in terms of a function the named file does not contain,
while the scanner still reported the rule it claimed was resolved — SEC-013's
shape, one layer further out.

**The flagged sinks are the validator's own filesystem probes.** Read from the
`codeFlows` rather than the line numbers, taint runs from
`POST /turingshub/spawn` to:

```
src/personality/turingshub/routes.py:75   body            <- POST /turingshub/spawn
src/personality/turingshub/routes.py:85   body["output_dir"]
src/personality/spawner.py:104            output_dir      (spawn)
src/personality/spawner.py:115            output_dir
src/personality/spawner.py:38             output_dir      (_resolve_output_base)
src/personality/spawner.py:54             Path(...).resolve()   <- sink
src/personality/spawner.py:68             parent.exists()       <- sink
```

Not the scaffold write — `safe_join` already guarded that, and the model pack at
`.github/codeql/tranc3-python-models/models/path-validation.yml` already declares
it a barrier. What was unguarded was the *act of validating*: `.resolve()` and
`.exists()` ran on the raw caller string before anything decided whether that
string was one this code was willing to touch. A validator that stats what it is
about to refuse is an existence oracle, and returns the answer through timing and
through the two distinct error paths.

**The second branch was dead, and its only live effect was that probe.** It
returned `candidate` when `candidate.parent` sat under an allowed root — but
`candidate` is resolved, so it has no `..` left and lies strictly below its
parent: any parent under a root puts the candidate under the same root, and the
first loop would already have returned. The sole path where
`candidate == candidate.parent` is `/`, whose parent is `/` and is under no root.
Measured across `./spawned`, `/tmp/x/y`, `/etc/cron.d/evil`, `/`, `/etc`, `..`,
`/tmp`, `/root/.ssh`, `/usr/lib/python3/x`: the second loop returned for nothing
the first had rejected.

**The fix is an ordering, not a new check.** Lexical containment first —
`os.path.normpath` on the joined path, pure string work, no syscall — and only a
path that survives it is resolved and checked again. The second check still
matters: it is what catches a symlink *inside* an allowed root pointing out of
it, which the lexical check cannot see. One deliberate narrowing: a symlink into
a root from outside (`/opt/link -> /tmp/x`) was accepted before and is refused
now, because step 1 judges the name the caller supplied.

**Calibration.** 13 tests in `tests/test_spawner_output_containment.py`. Run
against the restored pre-fix implementation, `test_no_filesystem_touch_for_rejected_path`
fails and prints the oracle verbatim:

```
['resolve:/etc/shadow-probe-target', 'stat:/etc/shadow-probe-target',
 'exists:/etc', 'stat:/etc']
```

Four syscalls on a path that was always going to be refused, including
`exists:/etc` — the dead branch, caught in the act. The other twelve pass against
both implementations, which is the honest result: they pin behaviour the old code
also had, and only this one distinguishes them. Its counterpart
`test_accepted_path_does_resolve` asserts an accepted path *is* resolved, so the
absence being measured is specific to rejections rather than to the guard having
been disabled.

**What this entry does not settle.** `/turingshub/spawn` declares no auth
dependency of its own, and `RBACMiddleware` does not gate it — its own docstring
says it "silently skips unauthenticated requests", and its `dispatch` populates
`request.state.user` and then always calls `call_next`. Another control that runs
on every request and enforces nothing by itself; enforcement depends on each route
calling `require_permission()`, and this one does not. `ZeroTrustASGIMiddleware`
*can* deny and is enabled by default, so whether an anonymous caller reaches the
spawner at all comes down to that middleware's default policy. **That has not been
measured**, and it is a separate question from this alert.

**Second pass, after cubic's P1 — the docstring said more than the code did.**
The first fix resolved the lexically-checked path in a single `Path.resolve()`
and claimed *"nothing outside a root is ever handed to the filesystem"*. Too
strong, and cubic said so. A symlink planted **inside** an allowed root
redirects the resolution outward, and `resolve()` follows it before any check
can object:

```
/tmp/sym-xxxx/into-etc -> /etc/shadow
lexically contained : True
.resolve() returns  : /etc/shadow
```

The containment verdict was still correct — the second check rejects it — but
the probe had already happened, which is the whole thing this function exists to
prevent. A claim that enforces less than it states is SEC-014's title, committed
here by the entry that documents it.

`os.readlink` reads a link's target *without* following it, so this was fixable
rather than only documentable. `_resolve_without_leaving` now walks the
components one at a time, `lstat`-ing each (which does not follow a final
symlink), expanding any link lexically against its own parent, and refusing the
first that leaves the roots — so nothing outside a root is stat-ed, and the
docstring is now true. A symlink chain is bounded so a cycle raises instead of
hanging. Contained links still resolve normally, which is tested, because a
guard that refused every symlink under the root would break legitimate layouts.

Calibration: 18 tests, 2 of which fail against the one-shot `resolve()` —
`test_the_target_is_never_stat_ed`, which spies on `os.stat` and asserts no call
outside the roots, and the symlink-cycle case.

**Third pass — the walk had to restart, and cubic found that too.** The second
pass expanded a link, checked the expanded *string* for containment, and carried
on with the next component. It never walked the target's own components, so an
intermediate symlink inside the target escaped unexamined. Reproduced before
being accepted:

```
<root>/mid -> /etc
<root>/hop -> <root>/mid/passwd

_resolve_output_base("<root>/hop")  ->  ACCEPTED
that path really is                ->  /etc/passwd
```

`<root>/mid/passwd` is lexically under the root, so the check passed on a string
whose second component was a door out. Expanding a link now re-seeds the pending
component list with the target's parts ahead of whatever remains, so every
component of every target is walked in its own right: `mid` is examined,
`readlink` returns `/etc`, and the walk refuses. A contained intermediate link
still resolves, which is tested — a restart that refused every multi-hop path
would pass the attack test while breaking ordinary layouts.

**A known limit, stated rather than implied.** This resolves by name, so a local
attacker who can already write inside an allowed root could swap a component
between the walk and the later `safe_join`/`mkdir` — a TOCTOU race cubic also
raised. Closing it means holding directory descriptors with `O_NOFOLLOW` through
every scaffold write, which is a redesign of how this module *writes* rather than
how it *validates*. The precondition is write access inside `Path.cwd()`, `/tmp`
or `$HOME`; an attacker with that already has better options against this process
than racing a scaffold generator. Not fixed, and not silently left out.

**Next review — measured, and the prediction did NOT hold.** This entry
predicted both alerts would persist, reasoning that `_resolve_output_base` still
returns a validated `Path` to a caller and that CodeQL does not model a raising
validator as a sanitiser.

**Both cleared.** Read from the retained SARIF for `6fae9678`
(run 34588789164): zero `py/path-injection` alerts on `src/personality/spawner.py`.

The reasoning was wrong in a specific and useful way. The flagged sinks were
never the *return value* — they were the `Path(...).resolve()` and
`parent.exists()` probes themselves, which is what this entry's own analysis
established and then failed to carry into its prediction. Replacing them with
`os.lstat` and `os.readlink` removed the sinks, so there was nothing left for the
taint to reach. The unmodelled-sanitiser limitation is real (SEC-014 and SEC-018
still demonstrate it) but it was never what governed this alert.

Recorded plainly because a prediction that missed is worth more than one that
held: it says the model of *why* an alert persists was wrong, and that model was
about to be reused.


---

### SEC-016 — the handler was unguarded; the app was not exploitable (`py/path-injection`, 7.5)

| Field | Value |
|---|---|
| **Disposition** | **FIX** — defence in depth. **Severity corrected downward 2026-09-11**, see below |
| **ID** | `py/path-injection` (CodeQL, security-severity 7.5) ×3 |
| **Scanner** | CodeQL Advanced |
| **Location** | `workers/gateway-service/router.py:743` ×2, `:744` — `serve_dashboard` |
| **Recorded** | 2026-09-11 |

> **CORRECTION, same day.** This entry first read *"unauthenticated arbitrary
> file read"*, and that was published in a pull-request comment. It was wrong.
> The proof of concept below ran against a **standalone FastAPI app replicating
> only this handler**, not against the gateway service as assembled. Measured
> against the real app with the route reverted to its pre-fix form, every
> traversal spelling is refused before it reaches the handler and **nothing
> leaks** — the OWASP hardening middleware stands in front of this route. The
> handler was genuinely unguarded; the deployed app was not exploitable through
> it. The fix stays, as defence in depth. Measuring one thing and reporting
> another is the mistake SEC-013 exists to record, and this is the same mistake
> in the other direction — overstating rather than understating.

**An unguarded handler.** Three alerts on one line:

```python
@router.get("/dashboard/{path:path}")
async def serve_dashboard(path: str = "index.html"):
    file_path = DASHBOARD_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
```

FastAPI's `{path:path}` converter exists precisely to let separators through, so
the handler received the remainder of the URL verbatim. `Path.__truediv__` does
not normalise `..`, and `exists() and is_file()` checks that the attacker's
chosen file is *there* — the opposite of containment. The route declares no auth
dependency.

Unlike SEC-014 and SEC-015, **the alert was simply correct**, and the flow is
three lines with no interprocedural hop: source at `:740`, join at `:742`, sink
at `:743`/`:744`. That shortness is worth noting — the two entries above it
needed the `codeFlows` read carefully to establish they were false positives;
this one needed the line read carefully to establish it was not.

**What the handler does, in isolation.** Against a bare FastAPI app carrying
only this route:

| request | result |
|---|---|
| `GET /dashboard/../../../../etc/passwd` | 404 |
| `GET /dashboard/..%2f..%2f..%2f..%2fetc%2fpasswd` | **200**, `root:x:0:0:root:/root:/bin/bash…` |
| `GET /dashboard/%2e%2e/%2e%2e/etc/passwd` | **200** |
| `GET /dashboard/..%2f.git%2fconfig` | **200**, `[core]… [remote "origin"]…` |

**The first row is why this survived review.** Every normal HTTP client —
browsers, `httpx`, `requests` — collapses `..` before the request leaves, so the
obvious probe comes back 404 and the route reads as safe. Percent-encoded
separators survive that normalisation and Starlette decodes them *after*
routing, so the traversal arrives intact.

**What the assembled app does, which is the part that was not measured before
publishing.** Same reverted route, but reached through `mod.app` with its
middleware stack:

| request | result | leaked |
|---|---|---|
| `..%2f..%2f..%2f..%2fetc%2fpasswd` | 400 `{"detail":"Invalid input"}` | no |
| `%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd` | 400 | no |
| `..%2f.git%2fconfig` | 400 | no |
| `../../../../etc/passwd` | 404 | no |

Ten further evasions aimed at the middleware rather than the handler — overlong
UTF-8 `%c0%af`, `%u2216`, `....//`, backslash separators, fully-encoded,
double-encoded, `..;/`, and a NUL byte — were all refused (400, 401 or 404),
none leaking. The middleware held against every spelling tried.

So the honest verdict is: **the route had no containment check of its own, and
the app in front of it refused every probe.** The fix is still right — a route
must not depend on a middleware it does not declare, and middleware order,
configuration and spelling coverage all change without this route's author
noticing — but it closes a gap in depth, not an open hole.

**The fix is containment via `safe_join`** — the same helper SEC-009 and SEC-012
use, deliberately, because a second copy of a path validator is a second thing
to keep right. Components are validated by name before the join, then the join is
resolved and re-checked, so `..` and absolute components are refused and a
symlink planted inside the dashboard directory pointing out of it is refused
after resolution. Splitting with `PurePosixPath` keeps parsing on URL semantics.
Traversals and genuine misses both return 404, so the response does not
distinguish "you tried to traverse" from "not there".

**The fix had a hole, and the test found it — not the reading.** The first
version filtered `"/"` out of the parsed parts. POSIX gives `//` its own meaning,
so `PurePosixPath("//etc/passwd").parts[0]` is `"//"`, not `"/"`, and
`//etc/passwd` passed through with a root component still attached and escaped
the join. `test_absolute_path_is_contained_not_honoured` failed on exactly that
case. Now the leading separators are stripped from the string before it is
parsed, which no enumeration of separator spellings can get wrong.

That test had *already* corrected me once: it first asserted that `/etc/passwd`
raises, and it does not — the leading separator is dropped and it resolves to
`DASHBOARD_DIR/etc/passwd`, contained and harmless, which is what every static
file server does. Refusal and containment are both acceptable; containment is
what the requirement names, so that is what it now asserts.

**Calibration.** 25 tests in `tests/test_gateway_service.py`, classes
`TestDashboard*`. Against the restored vulnerable route, **15 fail**. The 10 that
pass in both are the plain filename, nested filename and containment cases —
they pin behaviour the vulnerable code also had, which is what they are for —
plus the route-level probes, which the middleware refuses either way.

These counts were wrong in this entry until cubic caught it: the paragraph still
said "21 tests in `tests/test_gateway_dashboard_containment.py`", a file this
same entry records having deleted two paragraphs further down. One half of the
entry was corrected and the other left standing, so it cited a file that does not
exist. Re-measured against the suite the tests actually live in.

**Where the test lives — and the second correction.** These tests now sit
inside `tests/test_gateway_service.py`. They first went into a file of their
own, which put the worker directory on `sys.path` and imported `router` at
module scope, and **that broke six tests in the existing suite** with
`sqlite3.OperationalError: no such table: events`.

The mechanism is worth recording because the existing loader's docstring
anticipates the shape and stops one module short of it. `_load_gateway_worker()`
evicts `config`, `database` and `service` from `sys.modules` before
`exec_module`, so gateway-service's own copies are re-executed — but it does not
evict `router`. pytest imports every test module during collection, before any
test runs, so a second module importing `router` there left
`sys.modules["router"]` holding a router bound to the *pre-eviction* `database`.
`worker.py`'s `from router import router` then picked up that stale router:
`init_db()` created its tables in the fresh `database`'s file while
`insert_event` wrote to the old one.

Two loaders for one worker, which is the same mistake as a second copy of a path
validator — the thing this very fix avoided by reusing `safe_join`. One loader
now, and the containment tests live with it.

**This was reported as "no regressions" before it was true.** The full-suite run
that claim rested on never reached `tests/test_gateway_service.py` — the string
does not appear in its output — and a partial result was read as a clean one.
The same error as the severity overclaim above, and the same as SEC-013's.

The finding that sent the test to `tests/` in the first place still stands:
`workers/gateway-service/tests/` exists, with a `conftest.py`, a `TestClient` and
two modules, and **no workflow runs it**. `ci.yml`'s Pytest job runs
`pytest tests/ -q`, `pyproject.toml` sets `testpaths = ["tests"]`, and nothing
under `.github/workflows/` names a worker suite.

That is the estate's recurring shape once more — a control that exists, runs when
invoked, and is never invoked. It is not fixed here: how many of the ~70 worker
suites currently pass is unmeasured, and turning them all on in one commit would
convert an unknown number of pre-existing failures into a blocked queue. Tracked
separately.

**Also not settled.** `serve_dashboard` has no auth dependency, and
`RBACMiddleware` does not supply one — see SEC-015. Whether this route was
reachable anonymously in a deployment depends on `ZeroTrustASGIMiddleware`'s
default policy, unmeasured. `gateway-service` is **not currently wired into**
`docker-compose.production.yml` — its own Dockerfile comment says "if/when this
service is wired in" — so the exposure is latent rather than live. That lowers
today's urgency and not the severity of the defect: the fix belongs in the code
before the service is wired in, not after.

**Next review — measured, and the prediction held.** All three cleared. Read
from the retained SARIF for `6fae9678` (run 34588789164): zero
`py/path-injection` alerts on `workers/gateway-service/router.py`.

This also answers the contingency the entry named: the model pack **is** being
applied to `workers/`, so `safe_join`'s barrier declaration works there. That was
worth knowing independently of this fix.


---

### SEC-017 — the alert found the smaller half (`py/path-injection`, 7.5)

| Field | Value |
|---|---|
| **Disposition** | **FIX** ×2 — one reported, one found by reading around it |
| **ID** | `py/path-injection` (CodeQL, security-severity 7.5) ×1 |
| **Scanner** | CodeQL Advanced (the reported half only) |
| **Location** | `src/backup/engine.py:383` — `list_backups`; and **unreported**, `restore()` |
| **Recorded** | 2026-09-11 |

**The reported half — a read.** `GET /backup/list?worker=` reached:

```python
search_root = self.backup_root / worker if worker else self.backup_root
for meta_file in sorted(search_root.rglob("*.meta.json"), reverse=True):
    results.append(json.loads(meta_file.read_text()))
```

`Path.__truediv__` neither normalises `..` nor refuses an absolute right
operand — it *replaces* the left one. Measured:

| `?worker=` | `search_root` | effect |
|---|---|---|
| `gateway` | `<root>/gateway` | intended |
| `../../etc` | `<root>/../../etc` | escapes the root |
| `/` | `/` | **`rglob` walks the entire filesystem** |

The `/` row is the sharper one, and the calibration run put a number on it: the
same test takes **15,222 ms** against the pre-fix engine and under a millisecond
against every other input in the same parametrisation. One query parameter, a
full-disk walk, and the contents of every `*.meta.json` found anywhere returned
in the response body.

**The unreported half — a write, and it is worse.** Reading around the alert
rather than only at it:

```python
class RestoreRequest(BaseModel):
    worker: str
    backup_path: Optional[str] = None
    target_path: Optional[str] = None
    dry_run: bool = True
```

`restore()` honoured both paths verbatim. `backup_path` was read from anywhere;
`target_path`, after the SQLite integrity check, reached:

```python
live.parent.mkdir(parents=True, exist_ok=True)
if live.exists():
    live.rename(live.with_suffix(".pre-restore.db"))
shutil.move(tmp_path, str(live))
```

That is an arbitrary file write of caller-supplied content, creating parent
directories on the way, bounded only by "must gunzip to something that passes a
SQLite integrity check". Writing a valid SQLite database over another service's
valid SQLite database needs no exotic parsing — it is the obvious use of the
primitive, and `infinity-auth`'s user table is the obvious destination. The
existing file is renamed aside first, so the same call is also a destructive
one.

**CodeQL reported only the read.** That is the entry's point: the alert list is
a place to start reading, not a list of what is wrong. Three entries in a row
now — SEC-014's real defect was adjacent to a false positive, SEC-015's was the
validator rather than the write, and here the reported sink was the less serious
of two in the same file.

**Both are post-authentication, and that was checked rather than assumed.**
`workers/backup-service/worker.py` gates every route but `/health` behind
`x-internal-secret` and fails closed — its own comment records that it once read
`if _INTERNAL_SECRET and ...`, which a blank secret made falsy so the refusal
never ran, and that it now answers 503 instead. A control that was found
non-acting and fixed. So this is not an anonymous primitive, unlike SEC-016.

It is still worth denying at the destination: `INTERNAL_SECRET` is **one shared
value** across the estate's workers, so any single compromised worker inherits
arbitrary file write on the service that holds every other worker's database
backups. That is the lateral move the shared secret makes cheap, and the backup
service is the worst place in the estate to land it.

Unlike SEC-016, `backup-service` **is** wired into
`docker-compose.production.yml` — port 8078 published, Traefik router on
`backup-service.trancendos.com` with TLS.

**The fix.**

* `_worker_backup_dir` — a worker name indexes a directory; it is not a path. It
  is matched against `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` with `fullmatch` (per
  SEC-014's rule about `$`) and then joined with `safe_join`. It **raises** on a
  bad name rather than returning `[]`, because an empty list is what a real
  worker with no backups yet looks like; the route turns the refusal into a 400.
* `_contained_backup_file` — a backup is a file this service wrote, so there is
  no legitimate `backup_path` outside the backup root.
* `_permitted_restore_target` — destinations are the live database paths the
  registry itself declares, plus anything under `BACKUP_RESTORE_ROOT` when an
  operator sets it. Unset by default. The check runs **before** anything is
  read, so a refused target never causes a file to be opened, and
  `test_refusal_happens_before_any_write` asserts the destination directory is
  not created on the way to being refused.

`BACKUP_RESTORE_ROOT` is read at call time, not bound to a module constant: a
constant captured at import cannot be configured by the process that imports it,
which would make the one escape hatch this policy offers unusable in exactly the
case it exists for, and untestable without reaching into module internals.

**Four existing tests broke, and they were right to.** `test_restore_dry_run`,
`test_restore_overwrites_live_db`, `test_restore_creates_pre_restore_backup` and
`test_restore_no_backups` all restore a fixture-built `WorkerDB` — deliberately
not in the global registry — to a `tmp_path` destination. That is a legitimate
thing to do, and the new policy is that it has to say where. They now take a
`restore_root_allowed` fixture that sets `BACKUP_RESTORE_ROOT` to the temp
directory. Changing a test to accommodate a security fix is usually the wrong
move; it is right here only because the contract genuinely changed and the
change is written into the fixture's docstring rather than silently applied.

**Calibration.** 32 tests in `tests/test_backup_path_containment.py`; against
the restored pre-fix engine, **9 fail**, including the 15-second one. The 23 that
pass in both are the acceptance half — every name in
`WORKER_DATABASE_REGISTRY` still resolves, a registry-declared restore target
still needs no env var, and a backup inside the root still restores. An
over-tight name check would be a self-inflicted outage dressed as a security fix,
so that half is tested as deliberately as the refusals.

**Three more from cubic, two of which held.**

* **An existing directory was a permitted restore target, and that was
  destructive.** Measured against the pre-fix engine: a directory containing a
  file was renamed to `<name>.pre-restore.db`, a database file was moved into its
  place, and `restore` returned **success**. Containment was never the failing
  half — the directory was inside the permitted root. Being *allowed* to write
  somewhere is not the same as that place being a sensible destination, and the
  policy only encoded the first. Now refused.
* **A relative `BACKUP_ROOT` broke every named-backup restore.** `backup()`
  returns a path that already contains the root, so treating a relative
  `backup_path` as root-relative built `<root>/<root>/<worker>/…`. The
  containment verdict was never wrong; the path was. Relative paths now resolve
  against the working directory before the comparison.
* **`.` as a target did not hold.** It was already refused, by a mechanism the
  reviewer did not have: `Path(".").parts` is `()`, so the empty-parts guard
  rejects it first. Kept as a test, because "already correct, for a different
  reason" is a result worth recording rather than quietly folding into the fix.

**Next review — measured, and the prediction held.** The reported alert
cleared: zero `py/path-injection` alerts on `src/backup/engine.py` in the
retained SARIF for `6fae9678` (run 34588789164).

The unreported write still has no alert to clear, which is the durable point: its
only evidence is the test suite. A scanner that never named the more serious of
two defects in one file is not the thing to measure that fix against.


---

### SEC-018 — four false positives and one real leak beside them (`py/clear-text-logging-sensitive-data`, 7.5)

| Field | Value |
|---|---|
| **Disposition** | **FP** ×4; **FIX** for what reading around them found |
| **ID** | `py/clear-text-logging-sensitive-data` (CodeQL, security-severity 7.5) ×4 |
| **Scanner** | CodeQL Advanced |
| **Location** | `src/security/vault_client.py:65`, `:68`, `:108`; `src/security/jwt_rotator.py:106` |
| **Recorded** | 2026-09-11 |

**The four alerts are false positives.** Every logging site in both files was
enumerated, not sampled:

| site | logs |
|---|---|
| `vault_client.py:65` | `secret_name` |
| `vault_client.py:68` | `secret_name` |
| `vault_client.py:108` | `secret_name`, and the caught exception |
| `jwt_rotator.py:106` | `secret_id[:8]` — a UUID4 prefix — and `expires_at` |

A name and an identifier. The values never appear: `vault_client`'s `value` is
returned and cached but never logged, and `jwt_rotator`'s `new_secret` is
`secrets.token_hex(64)` that reaches storage only as a truncated SHA-256. The
rule fires on the *variable names* `secret_name` and `secret_id`.

**`:108` was the one worth checking properly**, because it logs a caught
exception, and the exception can come from `set_secret` — the one call that
*receives* a secret value. Measured across the five shapes
`except Exception` actually catches there:

| inner exception | secret in the final log line |
|---|---|
| `httpx.HTTPStatusError` | no |
| `httpx.ConnectError` | no |
| `httpx.ReadTimeout` | no |
| `json.JSONDecodeError` | no |
| `TypeError` (serialisation) | no |
| *control:* exception carrying the request body | **yes** |

The control matters. Without it the table would pass equally well against a
module that never built a message at all, and "the secret did not appear" is
exactly the kind of claim that passes for the wrong reason. It is kept as a
test.

**What reading around them found, and it is real.** `httpx` does not redact
userinfo when it builds an error message:

```
Client error '403 Forbidden' for url
'https://vaultuser:tOpS3cretToken@vault.internal:8038/secrets'
```

Every `VaultError` in the module interpolates that exception, and both
`get_secret_sync` and `jwt_rotator`'s rotation loop log the result. So an
operator who put credentials in `VAULT_SERVICE_URL` would have them written to
the log **by the vault client itself** — in a module whose entire purpose is
keeping secrets out of places like that. No alert named this.

Fixed at the source rather than at each log site: `VaultClient.__init__` now
discards userinfo, so every downstream message is safe regardless of which one
logs it. Nothing is lost — this client authenticates with `VAULT_TOKEN` in an
`Authorization` header, so userinfo in the URL is redundant as well as
dangerous. The warning names the variable and never the value, and it does not
fire when there is nothing to strip, because a guard that warned on every
start-up would be trained away.

**Calibration.** 18 tests in `tests/test_vault_client_log_hygiene.py`; 3 fail
against the pre-fix constructor. Five URL shapes are covered including an IPv6
literal, where `urlsplit().hostname` strips the brackets and a bare `fe80::1` is
not a host.

cubic caught one more: `if parts.port:` is falsy for port `0`, so an explicitly
written port was silently dropped and the client redirected to the scheme
default. `urlsplit("https://u:p@host:0/").port` is `0`, and `bool(0)` is False.
Now `is not None`, with a test for the absent-port case too, so the fix cannot
have become "always append".

**Next review — measured, and the prediction held.** All four persist in the
retained SARIF for `6fae9678` (run 34588789164), at `vault_client.py:104`,
`:107`, `:147` and `jwt_rotator.py:106`. The first three moved by exactly the 39
lines `_without_userinfo` added — the same three alerts, not new ones.

They will keep persisting: the code still logs variables named `secret_name` and
`secret_id`, which is what the rule matches on. Renaming them to satisfy a
scanner would make the code worse. This entry is the standing answer.


### SEC-019 — the fix that would have moved real users (`py/weak-sensitive-data-hashing`, 7.5)

| Field | Value |
|---|---|
| **Disposition** | **FP** — and deliberately not "fixed" |
| **ID** | `py/weak-sensitive-data-hashing` (CodeQL, security-severity 7.5) ×1 |
| **Scanner** | CodeQL Advanced |
| **Location** | `src/nanoservices/feature_flags/feature_flags.py:296` — `_hash_bucket` |
| **Recorded** | 2026-09-11 |

```python
def _hash_bucket(self, key: str) -> float:
    h = hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF
```

called as `_hash_bucket(f"{flag_key}:{user_id}")`. The rule fires because
`user_id` is classified as sensitive; the code already passes
`usedforsecurity=False`, which this rule does not consider.

**False positive.** The digest is not a credential, not a stored identifier, and
not compared against anything an attacker supplies. It is consumed on the next
line as `bucket < rule.percentage / 100.0` and discarded — never persisted,
never returned in a `FlagEvaluation`, and `_hash_bucket` has no caller outside
the module (checked across the tree, not assumed).

**The reason this entry exists is that the obvious fix is not free.** Swapping
MD5 for SHA-256 or BLAKE2 changes every user's bucket, which silently moves an
arbitrary fraction of users into and out of every live percentage rollout —
features appearing and disappearing for real people, with nothing in the diff
saying so. It is a one-line change that would read as tidying. This is the
clearest case so far of a scanner finding whose reflexive remediation is more
harmful than the finding.

So the assignments are pinned instead, in
`tests/test_feature_flag_bucketing.py` — 210 tests, the pinned table generated
from the implementation rather than transcribed. Anyone changing the hash now
gets a failure naming the affected keys, which turns a silent behaviour change
into a decision. `test_changing_the_hash_would_move_users` quantifies it by
computing how many of the sample cross a 50% threshold under SHA-256, and fails
if *none* do — because a sample on which the two digests agree would be useless
as evidence.

The suite also pins what the hash is actually for, which is the contract any
replacement must satisfy: buckets in `[0, 1)`, roughly uniform (a 10% rollout
reaching 8–12% of a 5,000-user sample), sticky per user, and independent across
flags — otherwise every 10% rollout would target the same 10% of users.

**Next review — measured, and the prediction held.** Persists at
`feature_flags.py:296` in the retained SARIF for `6fae9678` (run 34588789164),
for the same reason as SEC-018: the rule matches the construct, not the risk. Revisit if the platform adopts a
FIPS-mode interpreter that omits MD5 entirely — `usedforsecurity=False` already
covers FIPS builds that merely restrict it — in which case the re-bucketing
becomes unavoidable and should be planned and announced, not slipped in.


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
