# DVMS — Competitive Analysis and Enhancement Backlog

**Recorded:** 2026-09-04 · **Owner:** The Guardian (Marcus Magnolia) — Security pillar, SUITE-SEC
**Scope:** the Dependency & Vulnerability Management System as it exists in this repository,
assessed against the commercial and open-source platforms in the same category.

Every number below about *our* system was measured against the tree, not estimated. Every
claim about a *competitor* is attributed.

That promise was broken on the first draft and is worth recording rather than quietly
patching: this document described "no history, therefore no trends" as a weakness while
the very commit that carried it implemented census history. A governance record that
claims to be measured has to be re-measured when the tree moves under it, including by its
own author. Where a competitor's marketing figure is quoted it is labelled as theirs,
because a vendor's own noise-reduction percentage is a claim, not a measurement.
---

## 1. What the DVMS actually is

Not a product and not a single script — nine cooperating parts:

| Part | Code | Role |
|---|---|---|
| Census | `scripts/vulnerability_census.py` | Discovers 89 Python manifests + npm dirs, runs `pip-audit` and `npm audit --json`, classifies every finding, gates CI via `--check` |
| Register | `SECURITY_ALERT_REGISTER.md` | 7 entries, each a written disposition with an owner and a review date |
| Pin governance | `scripts/check_canonical_pin_governance.py` | Stops Dependabot and Renovate proposing the 5 centrally governed pins |
| Pin alignment | `scripts/align_framework_pins.py` | One version decision, applied across 63 requirements files in a reviewed pass |
| Proposal engines | `.github/dependabot.yml`, `renovate.json` | Governed; every enabled rule carries a 7-day `minimumReleaseAge` cooldown |
| Scanners in CI | Trivy, CodeQL, Semgrep, gitleaks, detect-secrets, OSV-Scanner, Checkov, syft + grype | Breadth beyond the census's two ecosystems |
| AI BOM | `scripts/ai_bom.py` | Model/dependency inventory |
| Obsolescence | `scripts/obsolescence_census.py` | End-of-life tracking, weekly |
| Schedule | `.github/workflows/supply-chain-watch.yml` | Census daily 05:00 UTC; obsolescence Mondays 05:30 UTC |

### The part that is genuinely unusual

`_classify()` in the census is the design's centre of gravity, and it is stricter than the
commercial norm:

```
fixable   A patched release exists and is reachable. Take it. Fails --check.
accepted  No patched release exists AND the id is dispositioned in the register.
blocked   A patched release exists but an explicit `Blocked-by` row says it is
          out of reach.
```

Two properties follow, and both are worth defending:

1. **An undocumented unfixable finding stays `fixable`.** It keeps failing the gate until
   somebody writes down why it is being accepted. Most platforms let a user click "ignore"
   with an optional comment; here the written disposition *is* the mechanism.
2. **`blocked` turns on an explicit marker, never on being documented.** A reachable fix
   stays `fixable` even for an id the register already knows about — which is what makes a
   newly published patch fail the gate the day it ships.

That is a governance-first design in a market of scanner-first products, and it is the thing
worth keeping through any future migration.

---

## 2. The comparable platforms

Identified from the 2026 SCA landscape. Each assessed on what it would actually change here.

### Endor Labs — reachability-first
Builds call graphs from application source and traces data flow into vulnerable methods,
function-level, across 40+ languages. Claims up to 97% noise reduction (92% average across
customers) — *their* figure.
**Relevance:** highest of any tool on this list. Reachability is what our register does by
hand. **Cost:** commercial, per-developer. Out of scope under Cloud Only.

### Snyk — developer-workflow-first
Reachability via Snyk DeepCode, but **limited to Java and JavaScript**; auto-fix PRs handle
most upgrades.
**Relevance:** the reachability limitation excludes our primary ecosystem (Python), so the
headline feature would not apply to 89 of our manifests. Auto-fix PRs are a category we
deliberately govern *down* — see the pin-governance rule that exists because bots produced
63 identical unmergeable PRs.

### Mend — automation-first, mid-market
Limited reachability; documented as still producing significant false-positive noise.
**Relevance:** low. It automates the part we already automate and does not solve the part we
do by hand.

### Socket — behavioural / malicious-package defence
Not reachability at all: analyses package *behaviour* to catch malware, typosquatting and
compromised maintainers.
**Relevance:** this is a real gap of ours, and a different gap from the one everyone else
addresses. Our only control in this category is `minimumReleaseAge: "7 days"`, which is a
good blunt instrument (it waits out most compromised-release windows) but detects nothing.

### OWASP Dependency-Track — the self-hostable platform
~20,000 organisations; ingests CycloneDX/SPDX SBOMs and continuously correlates against NVD,
GitHub Advisories, OSS Index, OSV. Supports CycloneDX VEX. **Critically: when a new CVE is
published it identifies every affected project without a rescan.**
**Relevance:** the closest thing to "the platform version of what we built". It is the
natural destination. **Cost:** an API-server container (2–8 GB RAM), a frontend container, a
managed PostgreSQL, and a backup target — i.e. it needs the local server that is currently
awaiting repair funding. **Honest verdict: not now.** It belongs on the Hybrid/Local path,
not the Cloud Only one.

---

## 3. SWOT — our DVMS

### Strengths
- **Fail-closed by construction.** A scan that errors counts as an unscanned surface, not a
  clean one. `--check` distinguishes "0 fixable" from "0 scanned".
- **Written dispositions with owners and review dates.** Seven entries, each carrying an
  owner and a `Next review`. An accepted risk that nobody owns does not exist here.
- **`blocked` as a first-class, separately-counted state.** Most tools conflate "we cannot
  fix it" with "we have accepted it". Conflating them is how a fixable finding goes quiet.
- **The proposal engines are governed, not merely enabled.** Ordering, datasource scope and
  override-detection are all enforced by a checker with its own calibrated test suite.
- **Zero marginal cost.** No per-developer licence, no vendor API budget.

### Weaknesses — all measured
- **No automated reachability.** The 2026 differentiator, absent. We perform it manually:
  SEC-005 and SEC-007 both contain hand-written reachability arguments. That is high-quality
  analysis that does not scale past a handful of entries.
- **The register is machine-unreadable.** It is, functionally, a VEX document that no tool
  can consume. Trivy, grype and OSV-Scanner run in our own workflows and re-report findings
  we have already dispositioned, because the disposition cannot reach them.
- **History exists but is thin, and CI does not contribute to it.** Closed on 2026-09-04:
  the census now appends one record per run to `vulnerability-census-history.jsonl`, keyed by
  surface + package + advisory so a turnover is visible rather than averaged away. What
  remains: the scheduled sweep holds no write token by design, so it uploads its record as an
  artifact instead of committing it, and the tracked file records only the runs a human
  landed. One line of history supports no trend yet — this becomes an answer over weeks, not
  on the day it was built.
- **Point-in-time, not continuous.** A CVE published against an unchanged manifest is found
  on the next daily run at best. Dependency-Track's "no rescan required" property is the
  thing we structurally lack.
- **Two ecosystems.** pip and npm only. The Rust/Go code under `aeonmind/` is covered by a
  Forgejo workflow that does not currently execute.
- **No malicious-package detection.** See Socket, above.
- ~~**DVMS ↔ CMDB overlap is zero.**~~ **Closed 2026-09-04.** This was recorded here as a
  weakness and it was half right. What was measured was the JOIN — the census keys findings
  by manifest path, the CMDB keys by ServiceID, and nothing mapped between them. What it
  was written to mean, that the entity linkage did not exist, was wrong: Cryptex and The Lab
  are Locations in `PLATFORM_ENTITIES.md`, and the design was unwired rather than absent.
  `src/dvms/surface_owner.py` supplies the join — 97 surfaces, 68 owned across 37 Locations,
  29 cross-cutting and stewarded, 0 unowned, enforced by
  `scripts/check_surface_ownership.py`. See `DVMS-ENTITY-FLOW.md`.

### Opportunities
- **OpenVEX is the missing wire, and it is free.** Trivy, grype and OSV-Scanner — all three
  already in our workflows — accept `--vex` with an OpenVEX document. The register becomes
  machine-readable once, and three scanners stop re-litigating settled findings.
- **`vulnerable_code_not_in_execute_path` is already our reasoning.** SEC-007's disposition
  is that exact justification, written in prose. The standard has a slot for it.
- **The history file is now the substrate for the analysis nobody has written yet.** MTTR,
  recurrence-per-package and "is exposure growing" are all reads over a file that exists;
  none of them are implemented.
- ~~**The manifest→ServiceID join**~~ — **done 2026-09-04.** It opened a larger one: with an
  owner on every finding, `src/dvms/dispatch.py` can raise the Change or Incident against the
  Location that answers for it, which is the Cryptex → The Lab handoff the platform's entity
  architecture always described and never had a first step for.

### Threats
- **A naive VEX export would be a fail-open control.** This is the single most important
  finding in this document. Marking every dispositioned entry `not_affected` would suppress
  real vulnerabilities in three scanners at once. Of our seven entries, **only SEC-007** is
  genuinely `not_affected` (the vulnerable function is never called). SEC-006 is the
  opposite: no patch exists and reachability was never established — it is `affected` with
  an action statement. Exporting it as `not_affected` would hide a live issue behind a
  standards-compliant file.
- **Dependency on a dormant runner.** Fourteen scheduled Forgejo supply-chain jobs need the
  self-hosted act-runner. They are built, wired, and do not fire.
- **Register drift.** Seven entries are maintainable by hand; seventy are not. Field naming
  is already inconsistent (`Component` vs `Components` vs `Location`).

---

## 4. Enhancement backlog, in value order

| # | Change | Value | Risk | Cost |
|---|---|---|---|---|
| ~~1~~ | ~~**Census history**~~ — **done 2026-09-04**, same commit as this document | Substrate for trends, MTTR, recurrence | None: adds data, suppresses nothing | Done |
| 1a | **Trend readers over that history** — MTTR, recurrence-per-package, exposure direction | Turns the record into an answer | None | Small |
| 2 | **VEX status as an explicit register field** — `VEX-Status` + `VEX-Justification` rows, from the OpenVEX enums | Makes #3 safe | None on its own | Small |
| 3 | **OpenVEX exporter** wired into Trivy/grype/OSV | Dispositions propagate to three scanners | **High if done naively** — see Threats | Medium |
| ~~4~~ | ~~**manifest → ServiceID join**~~ — **done 2026-09-04**, plus the dispatcher it unblocked | A finding names its Location and becomes a Change or Incident there | None: refuses to guess, `unmapped` is a gate failure | Done |
| 5 | **Ecosystem coverage** — Rust/Go into the census | Closes a real blind spot | None | Medium |
| 6 | **Malicious-package signal** | New detection category | Low | Medium |
| 7 | **Dependency-Track** | Continuous correlation, no rescan | Migration risk | **Blocked on server funding** |

### The rule that must govern #3

> The exporter refuses to guess. An entry without an explicit, human-written `VEX-Status`
> is **not exported**, and its findings keep failing the scanners. Silence is never
> interpreted as `not_affected`.

This is the same principle as `_classify()`'s treatment of undocumented findings, applied to
a new surface — and for the same reason.

---

## Sources

- [Top 5 SCA Tools for 2026: Snyk vs Mend vs Black Duck vs Endor Labs vs Socket](https://guptadeepak.com/tools/top-5-sca-tools-2026/)
- [Best SCA Solutions for 2026: Reachability-Driven Analysis — Endor Labs](https://www.endorlabs.com/learn/best-sca-solutions)
- [Best SCA Tools for 2026: 9 Tools Compared — Pixee](https://www.pixee.ai/blog/best-sca-tools-2026)
- [Signal in the Noise: An Industry-Wide Perspective on the State of VEX — OpenSSF](https://openssf.org/blog/2026/01/08/signal-in-the-noise-an-industry-wide-perspective-on-the-state-of-vex/)
- [OpenVEX and Open Source Vulnerability Scanners — OpenSSF](https://openssf.org/blog/2023/12/20/openvex-and-open-source-vulnerability-scanners-how-the-dynamic-duo-improves-vulnerability-management/)
- [Trivy — Vulnerability Exploitability Exchange (VEX)](https://trivy.dev/docs/latest/guide/supply-chain/vex/)
- [OWASP Dependency-Track](https://dependencytrack.org/)
- [Dependency-Track Review 2026: SBOM-First SCA — AppSec Santa](https://appsecsanta.com/dependency-track)
