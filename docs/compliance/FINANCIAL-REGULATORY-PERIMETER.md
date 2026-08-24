# Financial Regulatory Perimeter

**Version:** 1.0.0 | **Date:** 2026-08-22 | **Owner:** Trancendos Platform Engineering
**Companion to:** `docs/compliance/FCA-ALIGNMENT.md`, `docs/compliance/SECTOR-PROFILES.md`

> **This is not legal advice.** It is an engineering-side model of where the
> regulatory boundary sits, derived from what the codebase actually does. Before
> any activity in §4 is enabled, take advice from a regulatory solicitor or
> compliance consultant in each jurisdiction concerned. The value of this
> document is that it says precisely what the platform does today, so that advice
> can be sought about the right question.

---

## 1. The model: regulators regulate activities, not companies

The instinct behind "we have users in other countries, so we should comply with
all the global financial bodies" is a good one — but taken literally it is both
unachievable and unnecessary, and it is the single most expensive mistake a
small platform can make in this area.

No firm complies with the FCA *and* the SEC *and* FINRA *and* the CFPB as a
baseline posture. Financial regulation does not work like GDPR, where a single
regime attaches to you because of who your users are. It works like this:

1. Each jurisdiction defines a closed list of **regulated activities** —
   specific things you may not do for someone else without permission.
2. If you perform one of those activities, in or into that jurisdiction, you
   need that jurisdiction's authorisation.
3. If you do not, you need nothing. Not a lighter licence. Nothing.

So the question is never "which regulators apply to us?" It is **"which
regulated activities do we perform, and where?"** Answer that and the regulator
list falls out of it automatically. Answer it wrongly in the expansive direction
and you spend years and six figures preparing for permissions you never needed.

**The corollary that matters most:** the cheapest compliance posture is a
*narrow, deliberately defended perimeter*. Not "we comply with everything" —
"we provably do not do the things that would make us regulated, and we have
controls that stop us drifting into them by accident." That is what this
document, `FCA-ALIGNMENT.md` §2, and `_PROHIBITED_FINANCIAL_USES` in
`src/compliance/magna_carta.py` are collectively for.

---

## 2. Where Trancendos actually sits today

Measured against the code, not the naming. Everything in this table was checked
against source, not inferred from a service name.

| Thing | What the code actually does | Regulated? |
|---|---|---|
| **Royal Bank of Arcadia** | `primary_function` is *"Financial & Operations Management"* — infrastructure cost scaling and funding reallocation. Internal treasury metaphor. No customer accounts, no deposits, no client money. | No — not a bank, despite the name |
| **Arcadian Exchange** | `primary_function` is *"Procurement & Resource Trading"*. Its agents (`The Speculator-C`, `The Trader-C`) buy **compute** on server auctions. No ticker, ISIN, order book, matching engine or settlement vocabulary exists anywhere in `workers/orders-service/`. | No — an internal resource allocator, despite the name |
| **Billing / monetisation** | `src/monetisation/` — subscription tiers, free / £29 pro / £149 business, charged through Stripe. | No — see §3 |
| **payments-service (:8013)** | Routes to Stripe. No card data stored; PCI DSS scope sits with Stripe. | No — see §3 |
| **ledger-service (:8032)** | Internal double-entry record of the above. Records *our own* revenue. | No |
| **AI outputs on financial topics** | Whatever an LLM says when asked. **This is the only real exposure.** | Depends — see §4 |

The pattern is worth stating plainly, because it is easy to frighten yourself
reading the entity register: **Trancendos uses banking and exchange metaphors as
service names for internal infrastructure functions.** A regulator would not care
what a service is called. They would care what it does. Today, none of these do a
regulated thing.

---

## 3. Taking money is not a regulated activity

Charging customers a subscription is ordinary commerce. It becomes regulated when
you hold, transmit, or issue money **on someone else's behalf** — payment
services, e-money, safeguarding. Trancendos does none of those: Stripe is the
authorised payment institution, funds move from the customer to Stripe to
Trancendos' own account, and no client money is ever held.

The lines that would cross into regulation, none of which exist today:

- Holding a customer balance they can withdraw or spend elsewhere → **e-money**
- Moving money between two other parties → **payment services** (PSD2 / UK PSRs)
- Extending credit, or arranging it → **Consumer Credit Act** (UK)
- Offering "buy now pay later" style deferred payment → same

None of this is triggered by taking a card payment for your own product.

---

## 4. The four gates that would change everything

These are the four things Trancendos must not do without deliberate,
advised, funded preparation. They are the same four in `FCA-ALIGNMENT.md` §2 and
in `_PROHIBITED_FINANCIAL_USES`.

### Gate 1 — `financial_advice_regulated`
Telling a specific person what to do with their money, in a way tailored to
them. Under the FCA's COBS this is *advising on investments*; the equivalent US
concept sits under the Investment Advisers Act. Generic education ("index funds
have historically had lower fees than active funds") is not advice. "Given your
situation, you should move your pension into X" is.

This is the gate an AI platform crosses accidentally. Not by building a
robo-adviser — by having a general chat assistant answer a user's question about
their own money helpfully.

### Gate 2 — `investment_recommendation_personal`
COBS 9A: a *personal recommendation* is a narrower, sharper thing than advice
generally, and it carries suitability obligations. Any output that names a
specific instrument and presents it as suitable for this user is one.

### Gate 3 — `autonomous_binding_financial_decisions`
An AI that executes rather than suggests. This is where MiFID II, best
execution, and (in the US) the SEC's rules on automated advice come in. The
distance between "The Trader-C bids on compute" and "an agent executes a trade
for a user" is a product decision, not a technical one — which is exactly why
the perimeter has to be enforced in code rather than remembered.

### Gate 4 — `credit_recommendation_regulated`
Consumer Credit Act territory. Recommending or arranging borrowing.

**Each of these is enforced by MC-RULE-004's `prohibited_use_blocked` check** —
see §7 for the honest limits of that enforcement today.

---

## 5. Corrections to the regulator list

The list of bodies to consider was: FCA, SEC, CFPB, FINRA, IRS, IRA. Three of
those need correcting before they can be planned around.

| Named | What it actually is | Relevance to Trancendos |
|---|---|---|
| **FCA** | UK conduct regulator. Correctly identified, and correctly the primary one. | **Primary.** Only if a §4 gate is crossed. |
| **SEC** | US federal securities regulator. Regulates *securities* activity — issuing, broking, advising on, trading. | Only on Gate 1/2/3, and only for US persons. |
| **FINRA** | **Not a government regulator** — a self-regulatory organisation. You cannot "comply with FINRA" as an outside firm; its rules bind *its member broker-dealers*. You become subject to it by registering as a broker-dealer, which is downstream of an SEC decision, not a parallel one. | Not applicable, and cannot be made applicable without first becoming a broker-dealer. |
| **CFPB** | US consumer *financial products* regulator — lending, deposit accounts, debt collection, credit reporting. | Only on Gate 4, and only in the US. Not triggered by SaaS subscriptions. |
| **IRS** | The US **tax** authority, not a conduct regulator. Tax obligations follow from where the company is established and where it sells, not from what activities it performs. | Real but separate: a tax/VAT question (like HMRC in the UK), not a financial-services-conduct one. Handle it with an accountant, not a compliance programme. |
| **IRA** | An **Individual Retirement Account** — a US savings *product*, not a body of any kind. | Not a regulator; nothing to comply with. Would only matter if Trancendos ever custodied retirement assets, which is several gates beyond anything contemplated. |

Two bodies the list omitted that matter more than several it included:

- **ICO** (UK) and the EU **data protection authorities** — already in scope via
  GDPR, and far more likely to be the first regulator Trancendos ever hears from.
- **EU AI Act** authorities — already in scope, already partly enforced
  (`_PROHIBITED_AI_USES`), and applicable *regardless of* financial activity.

---

## 6. The jurisdiction ladder — how to scale without boiling the ocean

The right posture for a platform at this stage is a ladder, climbed only as far
as the product actually goes. Each rung costs real money; do not pay for a rung
you are not standing on.

**Rung 0 — where Trancendos is now. Cost: near zero.**
No regulated activity anywhere. Obligations are: ordinary consumer law, data
protection, tax, and the AI Act. Financial regulators are not in scope at all.
The work is *defending* this position: the §4 gates enforced in code, and
`FCA-ALIGNMENT.md`'s perimeter assessment reviewed when the product changes.

**Rung 1 — global users, still no regulated activity. Cost: low.**
This is the rung the question was really about. Having users abroad does **not**
pull in their regulators, because no regulated activity is performed. What it
does pull in:
- consumer-protection and unfair-terms law in each market (contract and pricing
  transparency — not financial regulation);
- data protection (GDPR, UK GDPR, and US state privacy laws);
- sanctions and export control screening — genuinely universal, genuinely
  applies at rung 0, and the one thing on this list worth doing now;
- tax registration thresholds (VAT/GST/sales tax) per market.

None of these need a financial licence. All are handled by terms, screening, and
an accountant.

**Rung 2 — one regulated activity, one jurisdiction. Cost: high.**
Pick the home market (UK/FCA), get advised, apply for the narrow permission that
covers exactly the one activity. Do not apply for a broad permission "to be
safe" — broader permissions carry proportionally heavier ongoing obligations,
capital requirements, and reporting.

**Rung 3 — the same activity, further jurisdictions. Cost: multiplied.**
Each jurisdiction is a separate authorisation with its own capital, reporting,
and local-presence requirements. There is no global passport. Even the EU's
MiFID passport only works from an EU-established entity, which post-Brexit a UK
firm is not.

**The practical rule:** each new jurisdiction at rung 2+ costs roughly what the
first one did. Plan to serve one, well.

---

## 7. Enforcement status — what is real and what is not

Stated plainly, because the previous version of the FCA document stated
enforcement that did not exist.

| Control | Status | Evidence |
|---|---|---|
| Four financial prohibited uses defined in code | **Real** | `_PROHIBITED_FINANCIAL_USES`, `src/compliance/magna_carta.py` |
| MC-RULE-004 flags them when a `use_case` is declared | **Real** | `tests/test_financial_perimeter.py` |
| Perimeter survives a config edit | **Real** | held in code, unioned with config; pinned by test |
| Rule covers the AI routes `api.py` mounts | **Real (newly)** | prefix tuple previously matched no mounted router |
| A crashing rule is visible to the caller | **Real (newly)** | `handler_errors` in the `check_request` outcome |
| **Any HTTP route declares its `use_case`** | **NOT DONE** | nothing sets `request.state.use_case`; unannotated routes evaluate an empty use case and pass |
| **A detected violation blocks the request** | **NOT DONE** | `enforcement.mode: advisory`, `fail_closed_on_violation: false` — violations are logged, not blocked |
| **The financial disclaimer is emitted** | **NOT DONE** | the string in `FCA-ALIGNMENT.md` §2 exists nowhere in the codebase |
| **`X-AI-Assistive-Only` response header** | **NOT DONE** | no response path sets it |

The first four are the difference between a documented perimeter and an enforced
one. The last four are what remains. They are listed here rather than quietly
omitted because a compliance control that is believed to exist and does not is
strictly worse than one known to be missing — it stops anyone looking for it.

### 7.1 Recommended order

1. **Declare `use_case` on the AI routes.** Small change, unlocks everything
   above it. A route that serves inference sets `request.state.use_case` from
   the request; the middleware already forwards it.
2. **Emit the disclaimer** on financial-topic responses. Cheap, and it is the
   control a regulator would look for first.
3. **Move MC-RULE-004 to fail-closed** once (1) is done and false positives are
   understood. Advisory mode is defensible while the input is unannotated;
   it stops being defensible once the check can actually see the use case.
4. **Sanctions/export screening at signup** — rung 1, genuinely universal, and
   nothing to do with financial licensing.

---

## 8. Perimeter drift — the real risk, and it is already in the register

The largest risk here is not that Trancendos decides to become a broker. It is
that a metaphor gets implemented literally by someone who reads the register and
takes it as a specification.

Three verbatim entries make this concrete:

- `src/entities/platform.py:570` — Arcadian Exchange ability:
  *"Micro-Transaction Trading: HFT trades of digital assets."*
- `src/entities/platform.py:571` — *"Passive Income Routing: Invests idle system
  resources."*
- `docs/governance/TRANCENDOS-MODELS-MATRIX.md:60` — George Porter's variant
  `Tranc3-Crypto` described as *"digital-asset micro-transaction trading
  (Bitcoin, Ethereum, Litecoin, Shiba Inu, and similar tokens)"*.

Today these describe an agent bidding on compute auctions. Read literally, they
describe **high-frequency trading of named cryptocurrencies and the investment
of idle funds** — which in the UK is cryptoasset activity under the Money
Laundering Regulations (FCA cryptoasset registration) and, in the EU, MiCA. Both
are regimes with zero current coverage in Magna Carta (§9).

This is a documentation risk with regulatory consequences, and it has two
cheap fixes:

1. **Say what it does.** "HFT trades of digital assets" → "high-frequency
   bidding on compute-resource auctions". "Invests idle system resources" →
   "reallocates idle compute capacity". The named cryptocurrencies in the Models
   Matrix should either be justified by real code or removed.
2. **Keep the metaphor, add the disclaimer.** If the flavour is wanted, the
   register entry should carry an explicit "internal resource allocation; not a
   financial market activity" note so no engineer and no auditor reads it as a
   spec.

Recommendation: (1) for the Models Matrix line, which names real tradeable
assets and has no code behind it; (2) for the two ability strings, which carry
platform character worth keeping.

*This is flagged, not fixed — the register text is the owner's, and rewriting an
entity's canonical ability description is a naming decision rather than a defect
fix.*

---

## 9. Coverage measured against Magna Carta

Documents in `compliance/magna-carta/docs/`, `compliance/magna-carta/compliance/`
and `docs/compliance/` mentioning each regime:

| Regime | Docs | Assessment |
|---|---|---|
| FCA | 46 | Well covered — the right primary focus |
| SEC | 68 | Over-covered relative to exposure (no US regulated activity) |
| HMRC | 7 | Reasonable — tax, correctly separated from conduct |
| IRS | 6 | Reasonable |
| PSD2 | 3 | Adequate — no payment services performed |
| PRA | 2 | Correctly minimal — PRA regulates deposit-takers and insurers |
| **FINRA** | 0 | **Correct.** Not applicable; do not add coverage |
| **CFPB** | 0 | Acceptable at rung 0; needed only if Gate 4 is ever crossed |
| **ESMA** | 0 | Acceptable at rung 0 |
| **MiCA** | 0 | **Gap if §8 is ever taken literally** |
| **MLR / AMLD** | 0 | **Gap if §8 is ever taken literally** — and the one that bites first, because cryptoasset registration is an AML regime, not a conduct one |

The two genuine gaps (MiCA, MLR/AMLD) are both downstream of the same thing: the
crypto-trading language in §8. Fix the language and the gaps close without
writing a single compliance document. Implement the language and both become
urgent, expensive, and blocking.

---

## 10. Summary

- The goal is **not** "comply with all global financial bodies". It is
  "perform no regulated activity, provably, and know exactly which line would
  change that".
- Trancendos performs **no regulated financial activity today**, in any
  jurisdiction. The banking and exchange names are metaphors for internal
  infrastructure functions.
- FCA is the right primary reference if a line is ever crossed. FINRA is not a
  regulator you can comply with; the IRS is tax; "IRA" is a savings product.
- Having users abroad adds consumer law, data protection, sanctions screening
  and tax registration — **not** financial regulators.
- The four gates are now enforced in code for callers that declare a use case,
  and honestly documented as unenforced for those that do not.
- The largest live risk is a metaphor in the entity register being read as a
  specification. That is §8, and it is a one-line-per-entry fix.

## 11. Review history

| Date | Reviewer | Action |
|---|---|---|
| 2026-08-22 | Trancendos | Initial perimeter model; enforcement gap in `FCA-ALIGNMENT.md` §2 found and closed; regulator list corrected; drift risk in the entity register recorded |
