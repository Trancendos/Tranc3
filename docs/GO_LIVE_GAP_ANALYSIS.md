# Go-Live Gap Analysis — Trancendos Estate (4 repos)

**Date:** 2026-07-31
**Scope:** Tranc3, CranBania, Magna-Carta, InfinityStyles
**Question:** what remains before the platform is 100% production-ready and LIVE?

All findings below were verified by execution (test runs, builds, compose validation,
git object inspection) rather than read from status documents. Where an existing
document disagrees with observed behaviour, the observed behaviour is recorded.

---

## 1. Headline

The **code** is close to ready. The **deployment** has not happened, one defect stops a
fresh clone from producing a buildable tree at all, and a second would make a successful
deployment unsafe.

| Repo | Verified state |
|---|---|
| Tranc3 | Scorecard 94.4%; full suite 4 failures (2 real, 2 order-dependent); 26 lint errors |
| CranBania | 35/35 tests pass; 11 npm vulnerabilities (7 high); no `.env.example` |
| Magna-Carta | Layer B automation 100% (19/19); 14 owner gates + 8 certificate uploads open |
| InfinityStyles | Builds, but 15+ TypeScript errors masked; no tests; not wired to the platform |

The single most important correction: **the published readiness percentage is not a
measurement.** See §3.

---

## 2. Blockers to a safe go-live

Three distinct things are wrong, and they fail in different ways. §2.1 stops a clean
`git clone` from producing a buildable tree at all. §2.2 does not block deployment — it
makes a successful deployment unsafe. §2.3 is neither: it is the current state of the
estate, which is that nothing has been deployed yet.

### 2.1 The Magna-Carta submodule pin references a commit that does not exist

The superproject's gitlink for `compliance/magna-carta` records
`966c237cbcc9b1020091366f81e38254167a8766` — reported by `git submodule status`, and stored
as a tree entry in this repository, not in `.gitmodules` (which carries only the path and
URL). That object is not reachable in the Magna-Carta repository — verified with
`git cat-file -t` after `git fetch --all` (all 9 remote branches fetched):

```text
fatal: git cat-file: could not get object info
```

Reproduced end to end on a fresh clone of this branch. `git submodule update --init`
registers both submodules, clones both, then dies on the checkout:

```text
fatal: remote error: upload-pack: not our ref 966c237cbcc9b1020091366f81e38254167a8766
fatal: Fetched in submodule path 'compliance/magna-carta', but it did not contain
966c237cbcc9b1020091366f81e38254167a8766. Direct fetching of that commit failed.
```

**This one failure takes both submodules down with it.** After the aborted run, both
`compliance/magna-carta/` and `workers/cranbania/` contain only a `.git` entry and no
working tree. `docker-compose.production.yml:1277` builds The Town Hall with
`context: workers/cranbania`, so `docker compose build cranbania` then fails for want of a
Dockerfile — even though nothing is wrong with CranBania itself.

The collateral damage is confirmed by initialising CranBania on its own, which succeeds:

```text
Submodule path 'workers/cranbania': checked out 'da5d03460e317064b593e2c0d283fcfa19bc04d2'
```

`src/compliance/magna_carta.py:19` reads
`./compliance/magna-carta/config/magna_carta_config.json`, so the compliance middleware
also loses its configuration source.

**Action:** re-pin the submodule to a commit that exists on Magna-Carta `main`
(currently `cc7d70e151de7ef0f95be0fb094b133a20e7f9fc`), then commit the updated
gitlink. That single fix restores both submodules.

**Not a blocker, but fix it in the same pass — the CranBania pin is stale.**
`workers/cranbania` is pinned to `da5d034`, the parent of `a960ce1` ("Close auth gap…").
That commit is perfectly reachable and checks out cleanly, so this is a pin-freshness
issue rather than a deployment failure. It still matters, and for a runtime reason rather
than a coverage one: `a960ce1` changed `middleware.ts` itself, scoping the cron-secret
exemption to POST instead of the whole path, so a build from the older pin ships The Town
Hall with the broader exemption still in place. It also predates `middleware.test.ts`,
which is a coverage gap on top of that — but the deployable difference is the middleware,
not the test.

Note that `scripts/setup_external_repos.sh` uses `git submodule update --remote`, which
tracks the upstream branch and bypasses the recorded pin entirely — so what you get
depends on which path you initialise with, and the two can disagree silently. Advance the
pin to `a960ce1df9fb478c373c0c0f20e2683aca154867` so both paths agree, and consider making
that script honour the recorded gitlink (or verify the checked-out SHA against it and fail
on mismatch) so deployment is deterministic rather than branch-tip dependent.

### 2.2 The Town Hall deploys unauthenticated by default

Three facts compound:

1. `middleware.ts:27-28` fails **open** — `if (!apiKey) return NextResponse.next()`.
2. `docker-compose.production.yml:1287` sets `CRANBANIA_API_KEY: ${CRANBANIA_API_KEY:-}`,
   defaulting to an **empty string**.
3. Traefik publishes it at `trancendos.com/townhall` with TLS and Let's Encrypt.

If the operator does not set the key in `.env.production`, every route — including
mutating ones — is reachable by anyone.

Separately, and independent of the key: **GET/read routes are never gated.** This is a
deliberate, documented decision (`middleware.ts:17-25`). PR #9 initially gated reads,
then reverted because every client component calls `fetch("/api/...")` with no
credential and the dashboard rendered empty. So board state, cards, **journal/audit
entries**, workspace export and ITSM incidents are world-readable whenever the service
is network-reachable.

The commit message states plainly that this "is a decision for the platform owner, not
something a header check can paper over." That decision is still outstanding and is a
go-live gate.

**Action (owner decision required):** either put a network boundary in front of
CranBania (Traefik forward-auth / IP allowlist / private network), or complete the
Infinity-One SSO integration already identified as the long-term direction. Also make
compose fail loudly on an empty `CRANBANIA_API_KEY` rather than defaulting it blank.

### 2.3 Nothing is deployed

`Ops executed on Citadel (live)` scores **12%**. `citadel_preflight.py` fails on exactly
one item — `.env.production missing` — which is expected, since secrets are generated on
the host. `citadel_compose_validate.py` passes cleanly (21 core services).

Per `CLAUDE.md`, The Citadel host is blocked on hardware funding, not on engineering.
This is the largest single gap to "LIVE" and it is **not a code problem**. Everything
needed is already scripted (`scripts/citadel_deploy_all.sh`, `deploy/LIVE_DEPLOY.md`).

---

## 3. The readiness scorecard overstates confidence

`scripts/production_readiness_score.py` presents ten weighted dimensions. Only four are
actually measured from repository state:

| Dimension | Weight | Source |
|---|---|---|
| CI & automated tests | 20% | binary flip: `92.0 if tests_ok else 40.0` |
| P0 core platform | 20% | binary flip: `95.0 if live_scripts else 82.0` |
| Worker fleet | 15% | measured — but see below |
| Production infrastructure | 15% | measured (compose validation) |
| Security & dependencies | 10% | measured |
| Observability | 8% | binary flip on `tests_ok` |
| UX / Infinity Admin OS | 7% | **hardcoded 78.0** |
| Zero-cost policy | 5% | **hardcoded 90.0** |
| Legacy decommission | 5% | binary flip: `55.0 if live_scripts else 35.0` |
| Ops executed live | 5% | measured |

**65% of the total weight is a constant or a two-value flip.** Two of those flips key off
the same `tests_ok` boolean, so a single pytest invocation moves three dimensions at once.

This was visible in practice during this analysis: the score read **80.8%** purely because
`pytest` was not installed in the environment, and rose to **94.4%** after
`pip install -r requirements-test.txt` — with no change to any source file. A metric that
moves 13.6 points on a dependency install is not measuring product readiness.

The `Worker fleet` dimension is measured, but by grepping `worker.py` for the literal
strings `"Stub worker"` / `"full implementation TODO"`. That returns **0 stubs across 81
workers**, which is accurate here — the thin files (`infinity-admin-service/worker.py` is
4 lines) are legitimate re-export shims for a modular refactor, verified by reading them —
but the check would not detect a genuinely empty worker that omitted those exact phrases.

The scorecard also links two documents that do not exist:
`docs/PRODUCTION_FORENSIC_ASSESSMENT.md` and `docs/PRODUCTION_READINESS_STATUS.md`.

**Action:** either replace the constants with real measurements (E2E pass rate for UX,
count of live CF routes for legacy decommission, dependency-audit output for zero-cost),
or relabel those rows as self-assessed so the headline number is not read as evidence.

---

## 4. Real code defects

### 4.1 `timesteps` is accepted and silently discarded

`tests/test_luminous_routes.py::test_neuromorphic_process_runs` fails with `assert 20 == 5`.

The caller passes `{"input": [...], "timesteps": 5}`. `src/bio_neural/neuromorphic.py:217`
constructs the network with `timesteps=20` hardcoded inside `_build_snn`, ignoring the
request. The API accepts a caller-supplied parameter, discards it, and reports the
hardcoded value back. **The test is correct; the code is wrong.**

### 4.2 A stale test contradicts an intentional security fix

`tests/test_gateway_service.py::TestGatewayOverview::test_overview_optional_auth_without_key`
expects `/api/overview` to return 200 without credentials. It returns 401.

`workers/gateway-service/main.py:180-191` documents why: these paths were deliberately
added to `enforced_paths` because the RBAC engine's anonymous-user default already grants
`READ_PLATFORM`, so without middleware enforcement an unauthenticated caller passed
straight through `check_rbac()`. The hardening is correct; the test predates it.

**Action:** update the test to assert 401 and rename it — the current name asserts a
security property the platform has deliberately abandoned.

### 4.3 Two order-dependent test failures

`tests/test_capacity_guard.py::TestThresholdEscalation` — both tests
(`test_emits_observatory_event_at_each_band`, `test_does_not_re_emit_within_same_band`)
fail in a full-suite run but **pass in isolation**. This is shared-state leakage between
tests, not a product defect, but it makes the suite non-deterministic and will produce
confusing red builds.

### 4.4 Lint

`ruff check .` reports **26 errors**, all import-organisation, all auto-fixable with
`--fix`.

---

## 5. Per-repo gaps

### CranBania

- **11 npm vulnerabilities (2 low, 2 moderate, 7 high)**, including Next.js
  *Unauthenticated disclosure of internal Server Function endpoints*, PostCSS path
  traversal / arbitrary file read, and sharp/libvips CVEs. `npm audit fix` is available,
  but run it deliberately: it rewrites `package-lock.json` and can move the dependency
  graph, so record the lockfile revision beforehand, review the resulting diff, then
  re-run the build, the test suite and the audit before calling it done. This matters
  more than usual given §2.2 — the service is intended to be publicly routed.
- **No `.env.example`**, despite 13 required environment variables including three
  secrets (`CRANBANIA_API_KEY`, `CRANBANIA_CRON_SECRET`, `FORGEJO_TOKEN`). This is not
  what causes §2.2's blank key — the `${CRANBANIA_API_KEY:-}` fallback in
  `docker-compose.production.yml` does that on its own. The missing example file is a
  compounding documentation gap: it leaves an operator no way to discover the variable
  exists before the silent default has already taken effect.
- CI is Forgejo-only (`.forgejo/workflows/`, 4 workflows) — correct per platform policy.
- Dockerfile is sound: multi-stage, non-root, healthcheck, and `next.config.ts` correctly
  sets `output: "standalone"` as the build requires.

### Magna-Carta

- **No CI whatsoever** — no `.github/workflows`, no `.forgejo/workflows`. For the repo
  that defines the compliance framework, nothing verifies its own registers on change.
  `scripts/compliance_health_check.py` and `scripts/readiness_automation_score.py` exist
  and pass; they simply never run automatically.
- `compliance_health_check.py`: 0 errors, 1 warning — **ACT-006 overdue** (due 2026-07-15,
  still "In progress").
- **14 owner go-live gates open** and **8 certifications pending upload**. These are
  real-world deliverables, not code:

  | Ref | Item | Due |
  |---|---|---|
  | ACT-003 / CERT-001 | Pay ICO data protection fee, record registration number | **2026-07-31** |
  | ACT-006 | Tranc3 HIPAA Tier A product copy remediation | 2026-07-15 (**overdue**) |
  | ACT-001 / CERT-002 | Signed DPA with authorised PSP (SUP-003) | 2026-08-31 |
  | ACT-007 | Policy attestation cycle for privileged roles | 2026-08-31 |
  | ACT-002 / CERT-003 | Countersign health connector BAA/DPA (SUP-005) | 2026-09-30 |
  | ACT-009 | Validate `magna_carta.py` request-boundary enforcement in staging | 2026-09-30 |
  | ACT-016 | Appoint named individuals to the 13 defined roles in HRIS | 2026-09-30 |
  | ACT-019 / CERT-009 | Name H&S officer, execute RIDDOR reporting drill | 2026-09-30 |
  | ACT-008 / CERT-005 | SOC 2 Type II observation period evidence | 2026-10-01 |
  | ACT-010 | Resolve US AI fallback DPA (SUP-004) or keep disabled | 2026-10-31 |
  | ACT-017 / CERT-007 | Premises fire risk assessment | 2026-10-31 |
  | ACT-005 / CERT-004 | Commission external penetration test (annual programme) | 2026-12-31 |
  | ACT-018 / CERT-008 | Payroll provider + live HMRC RTI reporting | 2026-12-31 |
  | ACT-012 | Expand BCP restore tests to all P0 databases | 2027-06-07 |

  All eight pending certificates appear above. The register holds nine slots in total —
  the ninth, CERT-006 (ISO 27001), is `not_applicable`, a reserved placeholder for a
  future certification with no owner action attached, so it is not counted as pending.

  Several of these gate lawful operation rather than technical function — ICO
  registration and the PSP DPA in particular. They cannot be closed by engineering and
  have long external lead times, so they should start now regardless of The Citadel's
  hardware funding.

### InfinityStyles

- `next.config.mjs` sets **`typescript: { ignoreBuildErrors: true }`**, masking **15+ real
  type errors** in `components/ui/` (`chart.tsx`, `resizable.tsx`, `calendar.tsx`).
  `pnpm build` succeeds and prints "Skipping validation of types"; `npx tsc --noEmit`
  shows the failures — verified by running `npx tsc --noEmit` inside the InfinityStyles
  working tree, not this one, so they are not reproducible from a Tranc3 checkout.
  The installed `react-resizable-panels` (v4.12.2 per its pnpm lockfile) no longer
  exports `PanelGroup` /
  `PanelResizeHandle`, so `resizable.tsx` references APIs that do not exist at runtime.
- Still named **`my-v0-project`** in `package.json` — an un-renamed v0.dev scaffold.
- **No test script and no tests.** CI runs `codeql.yml` and `node.js.yml` only.
- `@nuxt/kit` is a dependency of a Next.js application — almost certainly spurious.
- `@emotion/is-prop-valid` and `@nuxt/kit` are pinned to `"latest"`, making builds
  non-reproducible.
- **Not referenced anywhere in Tranc3** — no compose service, no platform entity, no
  documentation link. It is an orphan relative to the platform; its intended role
  (presumably Fabulousa's design system) is undeclared.

---

## 6. Smaller Tranc3 items

- **`SECURITY_ALERT_REGISTER.md` does not exist** at the repo root. `scripts/security_score.py:22`
  expects it and awards 12 of 100 security points for its presence with `FIX`/`FP`/`ACCEPT`/`SUPPRESS`
  dispositions and a `hostIPC` entry. This single missing file is the entire reason the
  security dimension sits at 88.6% against a 90% target. Every other security check passes.
- `.env.production` must be generated on The Citadel host
  (`scripts/generate_production_env.sh`) — expected, not a defect.
- `AUDIT_SIGNING_KEY` is not yet set for production.
- P0 `/health` endpoints are not yet scraped by Prometheus.
- **Two GitHub checks are red on every commit for reasons unrelated to the code**, which
  is worth fixing because it destroys the value of the signal. The commit status for this
  branch reads `failure`, and the cause is `CircleCI Pipeline`: *"No configuration was
  found in your project."* There is no `.circleci/` directory anywhere in the repository —
  the app is installed but the repo uses Forgejo and GitHub Actions, so it errors
  unconditionally. `Kilo Code Review` likewise returns `action_required` with *"your
  account is out of credits."* Neither is caused by the change under review, and neither
  can go green through anything a contributor writes. While they stay installed, "CI is
  red" carries no information on this repository and a genuine regression is easy to miss
  in the noise. Either uninstall both apps or satisfy them (add a `.circleci/config.yml`,
  add Kilo credits or switch it to a free model).

---

## 7. What to do, in order

**Can be done now, no funding, no external party:**

1. Re-pin `compliance/magna-carta` to an existing commit — this alone unblocks building.
   In the same pass, advance `workers/cranbania` to
   `a960ce1df9fb478c373c0c0f20e2683aca154867` and initialise both
   submodules. *(§2.1)*
2. Fix the `timesteps` bug in `src/bio_neural/neuromorphic.py`. *(§4.1)*
3. Update the stale gateway auth test to assert 401 and rename it. *(§4.2)*
4. Isolate the `test_capacity_guard` shared state. *(§4.3)*
5. `ruff check --fix .` *(§4.4)*
6. `npm audit fix` in CranBania; add `.env.example` covering all 13 variables. *(§5)*
7. Make compose reject an empty `CRANBANIA_API_KEY` instead of defaulting it blank. *(§2.2)*
8. Create `SECURITY_ALERT_REGISTER.md` with genuine dispositions — this needs real
   security judgement, not a placeholder file to satisfy the grep. *(§6)*
9. Add CI to Magna-Carta running its two existing check scripts. *(§5)*
10. Remove `ignoreBuildErrors` from InfinityStyles and fix the type errors, or state
    explicitly that the repo is not production-bound. Rename `my-v0-project`, drop
    `@nuxt/kit`, pin the `latest` dependencies. *(§5)*
11. Replace the scorecard's hardcoded dimensions with measurements, or relabel them.
    Create or delete the two missing linked documents. *(§3)*

**Requires an owner decision:**

12. How The Town Hall's read routes get protected — network boundary now, or
    Infinity-One SSO. This blocks go-live independently of everything else. *(§2.2)*

**Requires money or an external party — start immediately, long lead times:**

13. ICO fee (**due 2026-07-31**), PSP DPA, health-connector BAA, pentest, SOC 2 observation
    period, fire risk assessment, payroll/RTI. *(§5)*
14. The Citadel host hardware, then `./scripts/citadel_deploy_all.sh` and DNS cutover. *(§2.3)*

---

## 8. Honest summary

Treating "100% LIVE" as the target, the estate is roughly:

- **Code readiness: high.** ~5,000 tests with 4 failures, of which 2 are genuine and both
  are small. Compose validates. 81 workers are really implemented.
- **Deployability from a clean clone: currently broken.** A single invalid submodule
  gitlink stops the build before it starts, and takes the healthy CranBania submodule
  down with it. It is a quick fix.
- **Security posture: one unresolved design decision** (Town Hall read routes) plus a
  fail-open default that turns a missing environment variable into an open service.
- **Compliance: the automatable half is complete; the human half has barely started,**
  and its longest-lead items (SOC 2, pentest, DPAs) are measured in months.
- **Actually live: 12%,** gated on hardware funding rather than engineering.

The engineering work remaining is days. The compliance and hardware work is months, and
it is on the critical path to "LIVE" in a way the code is not.
