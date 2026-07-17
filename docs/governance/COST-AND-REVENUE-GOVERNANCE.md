# Cost and Revenue Governance

> **What this is.** The escalation policy for two related questions every service on this platform
> must periodically answer: (1) *is this still genuinely zero-cost*, and (2) *could this generate
> revenue, and is that worth doing*. Like `LOCATION-FUNCTIONS.md`, this document distinguishes a
> **fixed policy** (the escalation chain below) from **live, mutable state** (which services have
> actually been reviewed, and what was found) — the latter lives in
> `docs/architecture/ea-workbook/18_cost_and_revenue_review.csv`, not in this file.

**Code:** `src/master_worker/zero_cost_enforcer.py` (`ZeroCostEnforcer`, `BLOCKED_SERVICES`),
`config/zero_cost/providers.yaml` (`src/zero_cost/registry.py`), `scripts/zero_cost_audit.py`.
**Owner:** Royal Bank of Arcadia (Dorris Fontaine) · **Version:** 1.0.0 · **Created:** 2026-07-17

---

## 1. Scope and an explicit limit

This document defines a **process** — who reviews what, in what order, before this platform incurs
any real cost or pursues any real revenue activity. It is enforced two ways: automatically in code
(the zero-cost side — a request to a blocked provider is a Python exception, not a suggestion) and
procedurally by human sign-off (the revenue side, and any cost exception — nothing here can
authorize real spending or make a real tax determination by itself).

**What this document is not:** tax advice, a real revenue projection, or a claim that any named
persona autonomously approves spending. The named roles below (Dorris Fontaine, The Porter Family,
Cornelius MacIntyre) are this platform's documented ownership convention for *code and process*
(the same convention `CLAUDE.md` and `LOCATION-FUNCTIONS.md` use throughout) — they structure whose
review a change routes through in this repo's own tracking, not who has legal authority to commit
the operator to a real financial or tax obligation. Every real-world financial, tax, or legal
decision in this chain terminates in an actual human (§3, step 5) making an actual decision. Actual
tax obligations, bursaries, reimbursements, and fees are matters for a qualified accountant/tax
adviser — this platform can track and flag them (§4), it cannot determine them.

## 2. The zero-cost side (enforced in code today)

The platform's standing architecture is self-hosted and zero-cost (`CLAUDE.md` §"Zero-Cost
Self-Hosted Architecture"). Three real mechanisms already enforce this, found and partially closed
during this review:

| Mechanism | What it does | Gap found and fixed |
|---|---|---|
| `ZeroCostEnforcer.BLOCKED_SERVICES` | Regex blocklist of paid-service URL patterns; `assert_not_blocked()` raises `ValueError` before any external call that matches | Together.ai (`api.together.xyz`) was missing — added, alongside the pre-existing DeepSeek-direct block |
| `config/zero_cost/providers.yaml` + `src/zero_cost/registry.py` | Canonical per-capability approved-provider rotation chains; `assert_zero_cost()` rejects any provider not on the approved list | Already correctly excludes `together-ai`/`fireworks-ai` from the approved `ai_inference` chain (flagged `risk: credits_expire`) — this registry was right; the gap was that `workers/infinity-ai` never calls it |
| `ZeroCostEnforcer.assert_zero_cost()` daily assertion | Checks specific paid-provider env vars (`OPENAI_API_KEY`, etc.) and logs violations | `TOGETHER_API_KEY`/`DEEPSEEK_API_KEY` were missing from the checked list — added |

**Known remaining gap, not yet closed:** `workers/infinity-ai/service.py`'s `AIGatewayRouter` builds
its own provider list independently of `src/zero_cost/registry.py` — Together and DeepSeek are
currently excluded from the live rotation only because no API key is configured anywhere in
`docker-compose.production.yml`, not because the code checks `is_approved()`. That is an accident of
current configuration, not an enforced hard stop — the next person who sets `TOGETHER_API_KEY` as a
secret gets no warning from that worker itself (the platform-level checks above would still catch
it). Wiring `AIGatewayRouter.__init__` to filter its provider list through
`src/zero_cost/registry.is_approved()` is the natural next fix and is tracked as an open item, not
claimed as done here.

## 3. Escalation chain for any potential cost

Applies whenever a service change would introduce a cost that isn't already zero under §2 — a new
paid API tier, a cloud resource beyond a documented free tier, a subscription, etc.

1. **Dorris Fontaine (Royal Bank of Arcadia)** reviews the request first. Real review means: is
   there a genuinely zero-cost alternative already in `config/zero_cost/providers.yaml`? Has
   self-building the capability (in-house, matching this platform's own self-hosted pattern) been
   considered? This step must be able to point to what was checked, not just assert "no alternative."
2. If no zero-cost or self-built alternative exists, the request goes to a **governance board** for
   oversight and consultation — in this platform's existing structure, that's The Town Hall
   (Tristuran, `workers/cranbania/`), which already runs PRINCE2/ITIL change governance for
   everything else. A cost-incurring change is a change like any other; it goes through the same
   board, not a separate invented process.
3. If the board and Dorris agree the cost is unavoidable, **adaptive rotation and hard stops** are
   the interim mitigation, not the final answer: keep the zero-cost provider first in rotation
   (already the default across every capability in `providers.yaml`), and cap exposure with an
   explicit spend/request ceiling before the paid tier is ever reached (`quota_hard_stop: true`,
   `daily_request_limit_per_provider` in `providers.yaml` policy block — extend this pattern to any
   new paid tier being considered, don't invent a new mechanism per-service).
4. **Dorris presents the finding to Cornelius MacIntyre (Luminous)** — the case must show the
   alternatives actually investigated (§3.1), the board's position (§3.2), and the bounded worst-case
   cost with the hard stop in place (§3.3). Cornelius does not have independent authority to approve
   spend; this step exists so the request reaching the human is complete and not a bare "we need
   money" ask.
5. **The human operator decides.** Approve (cost incurred, with the agreed hard stop still active as
   a ceiling — approval is not a blank cheque) or reject (service suspended/rolled back to its
   zero-cost state, or not built). This is the only step in the chain with real authority over real
   money — nothing upstream of it can commit actual spend.

Record the outcome of any run through this chain in
`docs/architecture/ea-workbook/18_cost_and_revenue_review.csv` (§5) so it's auditable, not just a
conversation that happened once.

## 4. Tax, bursaries, reimbursements, and fees

Where a cost-governance case (§3) surfaces something with tax implications (VAT/sales tax on a
purchased service, an available grant/bursary, an eligible reimbursement, a platform transaction
fee), that fact gets **recorded and flagged** in the same review record (§5) so it isn't lost — but
the platform does not calculate, file, or claim any of these on your behalf. Route it to an actual
accountant or tax adviser before it affects a real decision. "Proactive and automated" here means
*surfacing* the flag reliably (e.g. Royal Bank of Arcadia's billing worker, `src/monetisation/`,
noting a new fee schedule the moment it changes), not the platform independently deciding what's
owed.

## 5. The revenue side — Arcadian Exchange service review

Standing practice: services get periodically reviewed by **Arcadian Exchange (The Porter Family)**
for realistic monetization angles — passive income, revenue-generating features, monetization
techniques appropriate to what that specific service does. Two rules keep this honest:

- Every entry is logged as a **candidate idea for human evaluation**, not a decided business
  outcome. No revenue figures are asserted; this platform has no live financial data to assert them
  from, and inventing figures here would be exactly the kind of fabrication this whole review effort
  has been working to eliminate from the CMDB.
- Any monetization idea that would touch payments in any way must specifically be checked against
  the existing rule in `BLOCKED_SERVICES`: *"Stripe payments — only allowed via Royal Bank of
  Arcadia worker"*. Nothing charges a real user except through that one, already-built path
  (`workers/payments-service`, `src/monetisation/billing.py`).

Reviewed services and their candidate ideas are tracked in
`docs/architecture/ea-workbook/18_cost_and_revenue_review.csv`, seeded honestly rather than
exhaustively: only services actually reviewed appear there, following this workbook's existing
verify-before-document convention (`docs/architecture/ea-workbook/README.md`).

## 6. Open items

- Wire `workers/infinity-ai/service.py`'s `AIGatewayRouter` to `src/zero_cost/registry.is_approved()`
  so Together/DeepSeek exclusion is enforced, not accidental (§2).
- `src/cloud/cost_optimizer.py` (`MultiCloudCostOptimizer`) was found during this review: dead code,
  never imported anywhere, defaulting `AWS_ENABLED`/`AZURE_ENABLED`/`GCP_ENABLED` to `"true"` and
  estimating ~£2,600/month of paid multi-cloud spend — directly contradicting this platform's
  zero-cost architecture. It predates the self-hosted pivot (referenced only in `wiki-content/
  Historical-*` docs). Recommend removal; not deleted in this pass pending confirmation it isn't
  wanted for some future multi-cloud evaluation path.
- `workers/vrar3d`'s optional `SKETCHFAB_API_KEY` integration is not listed in
  `config/zero_cost/providers.yaml` or `ZeroCostEnforcer.BLOCKED_SERVICES` — same class of gap as
  the infinity-ai item above, found later in the same audit pass (`18_cost_and_revenue_review.csv`
  REV-VRAR3D-001). Inert by default (feature only activates if the key is configured), but needs the
  same Dorris review before it's ever turned on.
- The Void has three separate worker implementations discovered across this audit
  (`docs/architecture/ea-workbook/02_service_inventory.csv` SRV-VOID-001/SRV-INFVOID-001):
  `workers/vault-service/` (deprecated, still deployed, broken port), `workers/the-void/`
  (code-only, never deployed), and `workers/infinity-void/` (fully working, self-contained,
  correctly deployed at port 8002 — appears to be the actual functioning self-hosted replacement).
  Consolidating onto one is a naming/architecture decision for Prometheus/Cornelius, not something
  this cost/revenue review resolves on its own.
- The full ~90-service Arcadian Exchange review (§5): as of this update, the EA/CMDB workbook
  (`docs/architecture/ea-workbook/18_cost_and_revenue_review.csv`) has verify-before-document
  reviews for 78 real services, including the previously-deferred billing-path services
  (orders-service, payments-service, files-service, identity-service, artifactory-service). Notably,
  payments-service (the standalone worker) was found to have no Stripe integration at all — the real
  Stripe billing path is `src/monetisation/billing.py`, a separate subsystem mounted on
  tranc3-backend, not the worker this row's process originally assumed. A handful of infrastructure
  sidecars in `docker-compose.production.yml` (Traefik, Prometheus, Grafana, MISP, Wazuh, and
  similar third-party self-hosted stacks) remain outside this workbook's scope and would need their
  own review pass if this process is extended to them.
