# Location-to-Location Flow Contract

> **What this is.** Thirty-nine statements of the form *"all X routes through Y"*, each paired
> with the probes that would evidence it, each measured against the working tree rather than
> asserted. It answers a question the estate could not previously answer at all.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **First measured:** 2026-08-21

- Contract: `config/estate/flow_contract.yaml`
- Checker: `scripts/flow_conformance.py`
- Baseline: `config/estate/flow_baseline.json`
- Tests: `tests/test_flow_conformance.py`

---

## 1. Why this exists

The platform's architecture is stated almost entirely as flow. Not "The Spark is an MCP server"
but "**all** MCP traffic routes through The Spark". Not "The Void is a vault" but "**all**
confidential material flows into The Void". Every one of those sentences is a claim about
routing, and until now not one of them was checkable.

`LOCATION-TRAFFIC-MATRIX.md` recorded the gap accurately in July: no file in this repository
instruments or declares inter-Location flow, and the one mechanism built for it —
`ServiceMesh.get_dependency_graph()` — returns an empty graph for every service because no
registration call site has ever passed `dependencies=`. That is still true. This document does
not fix it by instrumenting live traffic; it fixes the prior problem, which is that the claims
themselves were unfalsifiable. An unfalsifiable claim cannot be wrong, so it also cannot be
maintained.

## 2. The verdicts

A rule's verdict is **derived from its probes**, never declared. A rule cannot assert its own
health — the same discipline the vulnerability census learned when its `blocked` classifier was
inferring suppression from register membership and would have started passing at the exact moment
it should have started failing.

| Verdict | Meaning |
|---|---|
| `enforced` | every probe passes — the hub exists and something routes to it |
| `partial` | the hub exists and some, but not all, coupling probes pass |
| `unwired` | the hub exists and **nothing** routes to it |
| `absent` | no implementation found at all |
| `unknown` | a probe could not be evaluated — fail-closed, treated as failure |

`unwired` is the verdict worth having, and the reason this exercise was worth doing. It separates
*we have not built this* from the more expensive failure: code that exists, imports cleanly,
passes its own tests, is reached by nothing, and therefore reads as **done** in every review it
ever passes through. Fourteen flows sit there. That is the real finding.

## 3. The measurement

As at 2026-08-21T13:37:19+00:00, across 39 declared flows:

| Verdict | Count |
|---|---|
| `enforced` | 20 |
| `partial` | 4 |
| `unwired` | 14 |
| `absent` | 1 |
| `unknown` | 0 |

| ID | Hub | Claim | Verdict |
|---|---|---|---|
| `FLOW-002` | The Spark | All MCP tool traffic routes through The Spark | **enforced** |
| `FLOW-004` | The Nexus | All AI-to-AI communication routes through The Nexus | **enforced** |
| `FLOW-010` | Cryptex | All cyber-defence signal routes through Cryptex | **enforced** |
| `FLOW-020` | The Observatory | Every action and change is observed and logged by The Observatory | **enforced** |
| `FLOW-021` | The Basement | Observatory records age out into The Basement | **enforced** |
| `FLOW-024` | Think Tank | Section 7 research findings are handed to Think Tank for solution assessment | **enforced** |
| `FLOW-025` | Luminous | Luminous orchestrates and coordinates the platform on Cornelius's behalf | **enforced** |
| `FLOW-030` | Sashas Photo Studio | All photo and image generation routes through Sashas Photo Studio | **enforced** |
| `FLOW-032` | TateKing | All video creation and editing routes through TateKing | **enforced** |
| `FLOW-033` | TranceFlow | All game and 3D development routes through TranceFlow | **enforced** |
| `FLOW-034` | Imaginarium | The Imaginarium orchestrates the creative Locations rather than duplicating them | **enforced** |
| `FLOW-035` | Warp Radio | Warp Radio connects users to music on demand | **enforced** |
| `FLOW-040` | The Lab | All coding and development work routes through The Lab | **enforced** |
| `FLOW-050` | Infinity | Infinity Portal is the single login entrance | **enforced** |
| `FLOW-051` | Infinity | Infinity Gate routes a multi-role user to the right platform entrance | **enforced** |
| `FLOW-052` | Infinity | Infinity-One is the central user account and profile hub | **enforced** |
| `FLOW-062` | The Town Hall | The Town Hall carries ITIL/ITSM, the CI register and CMDB | **enforced** |
| `FLOW-063` | The Town Hall | The Town Hall carries the War Room and Governance Board Room | **enforced** |
| `FLOW-065` | DocUtari | All user documents and files are stored in DocUtari | **enforced** |
| `FLOW-066` | The Observatory | Diagnostic assessment is aggregated rather than per-service | **enforced** |
| `FLOW-001` | The Digital Grid | Workflow and pipeline execution routes through The Digital Grid | partial |
| `FLOW-022` | The Library | The Basement's confirmed patterns are promoted into The Library | partial |
| `FLOW-043` | The Workshop | The Workshop holds repositories and mirrors to GitHub, GitLab and Bitbucket | partial |
| `FLOW-060` | Royal Bank of Arcadia | All financial regulation routes through Royal Bank of Arcadia | partial |
| `FLOW-003` | API Marketplace | All external and internal APIs are catalogued by the API Marketplace | **unwired** |
| `FLOW-011` | The Void | All secrets and confidential material flow into The Void | **unwired** |
| `FLOW-013` | The Warp Tunnel | The Warp Tunnel isolates anomalous entities and transports them to The Ice Box | **unwired** |
| `FLOW-014` | The Ice Box | The Ice Box spins up containers, VMs and sandboxes on demand | **unwired** |
| `FLOW-015` | The HIVE | A Cryptex threat escalation raises a platform-wide alert state (Call to Arms) | **unwired** |
| `FLOW-023` | The Academy | Library KB articles are scanned by The Academy and developed into training material | **unwired** |
| `FLOW-031` | Fabulousa | All UX, UI and design-system work routes through Fabulousa | **unwired** |
| `FLOW-041` | The Lab | All debugging routes through Slime | **unwired** |
| `FLOW-042` | The Chaos Party | All testing routes through The Chaos Party | **unwired** |
| `FLOW-044` | The Artifactory | Produced artifacts are held and analysed by The Artifactory | **unwired** |
| `FLOW-053` | Infinity | Infinity Bridge is the transport layer users navigate through | **unwired** |
| `FLOW-054` | Arcadia | Arcadia is the post-login user entrance with forum, AI chat and email | **unwired** |
| `FLOW-061` | Arcadian Exchange | Transactions are executed by Arcadian Exchange and regulated by Royal Bank of Arcadia | **unwired** |
| `FLOW-064` | The Town Hall | User-requested work passes a PLM gate review before it is signed off | **unwired** |
| `FLOW-012` | The Lighthouse | The Lighthouse cryptographically tags and scans all inbound and outbound traffic | absent |

## 4. What the numbers actually say

**The observation and memory chain is the strongest thing in the estate.** The Observatory is
imported by 84 modules outside its own tree — no other hub comes close — and its handoff to The
Basement is a real call at `src/observability/observatory.py:180`, not a documented intention.
Cryptex, The Spark, The Nexus and Luminous are all genuinely central to the code that surrounds
them.

**The creative chain works because one service does the routing.** Sashas Photo Studio, TateKing
and TranceFlow score `enforced` for exactly one reason: `workers/imaginarium/worker.py` names
their URLs and fans work out to them. Remove the Imaginarium and all three become islands. That
is a thin thread to hang a chain on, but it is a real one — and it is the only worker-to-worker
orchestration pattern in the estate that actually works, which makes it the template for the
rest rather than an exception.

**Fabulousa is the hole in that chain.** The Imaginarium's fan-out names five services and
design is not among them. UX, UI and design-system work is the one creative discipline the
orchestrator does not call, while the actual design system lives in a separate repository
(InfinityStyles) with no link back to the worker that is supposed to own it.

**The security chain terminates at stage one.** The Warp Tunnel scans and quarantines — to a
local directory. It does not hand the offender to The Ice Box, and The Ice Box could not receive
it if it did: that worker is a quarantine *register* (scan, list, release, stats over SQLite)
with no execution surface at all — no container runtime, no VM lifecycle, no detonation. The
three-stage design of isolate → detonate → assess is one stage built and two designed. The
Lighthouse, which is supposed to tag and monitor every item crossing the boundary, has no
implementation in this repository at all.

**Nothing raises an alarm.** The Call to Arms escalation — Cryptex detects, Renik and The
Guardian raise alert state, Cornelius requests HIVE support, the swarms mobilise — has no code,
no state machine, and no vocabulary anywhere in the repository. The nearest existing machinery
is the governance `EscalationFSM`, which escalates *decisions*, not defence. `hive-service` is
228 lines and exposes `/health` and nothing else.

**Two financial surfaces do not know about each other.** `src/monetisation` carries billing
tiers, the Arcadian Exchange fee calculation and revenue modelling in-process;
`workers/payments-service` carries accounts, transfers, deposits and a ledger — as a separate
worker. Neither imports or calls the other, and `orders-service` calls neither. So "transactions
execute in the Exchange and are regulated by the Bank" describes a relationship that exists in
documentation and in no code path. The 2.5% marketplace fee is a calculation with no transaction
to attach to.

**The learning loop was built and left with no entry point.** `src/basement/promotion.py`
implements the whole Basement → Library leg — clustering, regression detection, article rendering,
DRAFT authoring — and its own docstring describes closing "the fourth leg" of the learning
pipeline. Until this pass it was called by nothing: no import, no route, no job. Evidence
accumulated in the store and reached nobody. It now has an admin-gated entry point at
`POST /basement/promote`, which is why FLOW-022 reads `partial` rather than `unwired` — reachable,
but still not automatic. The next leg after that, Library KB → Academy curriculum, does not
exist: `workers/the-academy/worker.py` contains no reference to the Library, to KB articles, or
to any knowledge source.

**The Chaos Party never sees the platform's own tests.** The worker is real — suites, runs, batch
runs, chaos experiments — and CI runs `pytest` directly and posts nothing to it. The platform's
test intelligence is blind to the platform's testing.

## 5. What was fixed in this pass

| Change | Effect |
|---|---|
| `POST /basement/promote`, admin-gated | FLOW-022 `unwired` → `partial`; the learning pipeline's fourth leg is reachable |
| Flow contract + checker + baseline | 39 previously unfalsifiable claims are now measured and re-runnable |
| `tests/test_flow_conformance.py` | The classifier, the prose-stripping and the baseline comparison are pinned against regression |
| Promotion keyed on pattern signature | `POST /basement/promote` is idempotent — a retry or a second admin cannot raise a duplicate draft from the same evidence |

Everything else in the `unwired` and `absent` columns is recorded, not repaired. Repairing them
is real product work — a sandbox runtime, an alert state machine, a payments↔ledger contract —
and inventing thin versions of them to turn the table green would defeat the purpose of having
built the table.

## 6. Two defects this checker had, and why they are worth recording

The first run reported **24 enforced**. Four of those were false, and the way they were false is
the point.

**The checker cited its own prose as evidence.** FLOW-022 scored `enforced` because
`symbol_called` grepped `scripts/` for `promote(` and found a match — in the docstring of
`flow_conformance.py` itself, the paragraph explaining that `promote()` is called by nothing. A
tool that accepts its own description of an absence as proof of a presence is worse than no tool.
Fixed by stripping comments and docstrings before any probe reads a file, excluding `__pycache__`
(a `.pyc` contains every string literal in its module, so matching inside one counts the same
source twice and calls it corroboration), and excluding the checker from its own search path.

**A mention passed as a route.** "All debugging routes through Slime" scored `enforced` because
the string `Slime` appears in `workers/the-lab/worker.py` — inside a `"lead_ais"` metadata
literal. "Arcadia has a forum" scored `enforced` on `primary_function="... Forum & Email Hub"` in
the entity table. Naming a thing is not routing to it. Fixed by requiring patterns to match a
route, a call or an environment variable, and by a contract test asserting every rule carries at
least one coupling probe — which immediately caught a third defect: FLOW-060 (Royal Bank) had
only existence probes and was scoring healthy purely because the directories exist.

Both are the same defect class this estate keeps rediscovering — `payload_scanner.py` unwired
from `/mcp/rpc`, a security score that could not move when a CVE landed, sixteen dormant Forgejo
jobs, `dependency_audit.py` discarding its own result, the census inferring `blocked` from
register membership. **A control that exists, runs, and reports, but cannot fail.** It is worth
noticing that building the instrument to detect that class produced two fresh instances of it
inside a single afternoon.

## 7. Running it

```bash
python scripts/flow_conformance.py                  # the table above
python scripts/flow_conformance.py --json           # full probe detail
python scripts/flow_conformance.py --check          # fail on regression against the baseline
python scripts/flow_conformance.py --write-baseline # record current verdicts (reviewable act)
```

`--check` compares the contract against the baseline **exactly**, in both directions. It
deliberately does not fail on the standing backlog of 14 unwired flows: a gate that is red on day
one for reasons nobody can fix that day trains people to wave it through, which is the failure mode
the gate exists to prevent. What it fails on is any disagreement with the recorded state —
a regression, an unrecorded improvement, a rule missing from the baseline, or a baseline entry
whose rule has been deleted from the contract.

> **Correction, 2026-08-21.** This section first said the gate failed *only* on regression, and the
> code matched that description. Both were wrong, and wrong in a way that broke the ratchet they
> were meant to be. If a flow improved from `partial` to `enforced` and nobody refreshed the
> baseline, the run passed — leaving the baseline still reading `partial`, so a later slide back
> from `enforced` to `partial` also passed, because it now *matched*. The gate would have stayed
> green across the entire round trip, having recorded an improvement it then silently gave back.
> Raised in review by CodeRabbit on PR #839 and fixed in the same pass: an unrecorded improvement
> now fails with a message naming the fix, and `TestBaselineComparison` pins both directions plus
> the baseline-only case.

## 8. Cross-references

- `docs/governance/LOCATION-TRAFFIC-MATRIX.md` — the document that recorded this gap; §4's
  "path forward" option 1 (populate `ServiceDescriptor.dependencies`) remains unbuilt
- `docs/governance/MATRIX-INDEX.md` — index of the governance matrix family
- `config/estate/registry.yaml` — component-level truth for names, ports and ownership
- `PLATFORM_ENTITIES.md` — the 43 canonical entities these flows connect
