# FCA Alignment Programme

**Version:** 1.0.0 | **Date:** 2026-06-12 | **Owner:** Trancendos Platform Engineering
**Standards:** FCA PRIN · FCA PRIN 2A (Consumer Duty) · COBS 4 · PS21/3

## 1. Scope and FCA Perimeter Assessment

Trancendos operates as a **platform provider** (SaaS/PaaS), not as an FCA-authorised firm. This programme governs the platform boundary to ensure:

1. The platform does **not** conduct regulated activities without authorisation
2. AI outputs are **never** presented as regulated financial advice
3. Payments route **exclusively** through an FCA-authorised PSP
4. Supplier resilience obligations under PS21/3 are understood

**FCA Part 4A Authorisation Status:** Not applicable unless regulated activities are added to platform scope. This is reviewed quarterly.

## 2. Prohibited Activities (Platform Boundary)

Four uses sit outside the platform boundary. Crossing any of them turns an
unregulated activity into a regulated one and changes Trancendos' authorisation
status — see `docs/compliance/FINANCIAL-REGULATORY-PERIMETER.md` for what each
maps to and why.

| Prohibited use | Regime |
|---|---|
| `financial_advice_regulated` | FCA COBS — regulated advice |
| `autonomous_binding_financial_decisions` | MiFID II / UK MiFIR |
| `investment_recommendation_personal` | FCA COBS 9A — personal recommendation |
| `credit_recommendation_regulated` | Consumer Credit Act |

**Where this is enforced.** `_PROHIBITED_FINANCIAL_USES` in
`src/compliance/magna_carta.py`, evaluated by MC-RULE-004's
`prohibited_use_blocked` check against the declared `use_case` of a request on an
AI route. The set is held in code rather than in `magna_carta_config.json` so
that widening the perimeter requires a code review, not a config edit; the EU AI
Act Article 5 set (`_PROHIBITED_AI_USES`) is held the same way, and both are
unioned with whatever the loaded rule config adds. `tests/test_financial_perimeter.py`
pins all four terms.

**Correction (2026-08-22).** Version 1.0.0 of this document stated that these
four were "explicitly blocked by `src/compliance/ai_governance.py`" and printed a
`PROHIBITED_USES` constant. No such constant existed — in that module or anywhere
else in the repository. The four strings appeared in this document and nowhere
else. The check that did exist carried only the EU AI Act terms and could not
fire at all: the middleware sets `use_case` to `None` when no route declares one,
the handler's `data.get("use_case", "")` default only applies to a *missing* key,
and `use_case.lower()` raised `AttributeError` on every request — which the rule
engine catches and, in advisory mode, converts to "passed". The check reported
success because it had crashed. Separately, the rule's route prefixes
(`/ai/`, `/infinity-ai/`, `/model-router/`) match no router `api.py` mounts, so it
skipped every in-process request regardless. All three are fixed.

**Residual gap — not closed.** Nothing currently sets `request.state.use_case`.
Until a route declares its use case the check evaluates an empty string and passes,
so the perimeter is enforced for any caller that supplies a `use_case` (including
direct `check_request` callers and the worker paths) but is not yet reached from an
unannotated HTTP route. The framework is also in `advisory` mode
(`enforcement.fail_closed_on_violation: false`), so a detected violation is logged,
not blocked. Both are tracked in `FINANCIAL-REGULATORY-PERIMETER.md` §7.

**Required disclaimer — not yet implemented.** AI outputs on financial topics are
to carry: *"This is informational only and does not constitute regulated financial
advice. Consult an FCA-authorised adviser."* That string appears nowhere in the
codebase; no response path emits it today. It is stated here as the requirement,
not as a description of current behaviour, and is tracked alongside the two gaps
above.

## 3. Consumer Duty (PRIN 2A)

Applicable when Tranc3 serves **retail customers** in the UK financial services supply chain.

| Consumer Duty Outcome | Implementation | Evidence |
|---|---|---|
| Products and services | Clear feature descriptions, no hidden obligations | docs/policies/ |
| Price and value | Zero-cost tiers documented | docs/01-MAGNACARTA-FOUNDATION.md |
| Consumer understanding | Plain language policy summaries | POL-PRI-001 |
| Consumer support | DSR process <30 days, support channels | PROC-DSR-001 |

## 4. Financial Promotions (COBS 4)

Financial communications from Trancendos must be:
- **Fair, clear and not misleading** — marketing review checklist enforced pre-publish
- **Approved** — all financial promotions reviewed by compliance before distribution
- **AI-generated content** — labelled with AI disclosure, reviewed by human before distribution

## 5. Payments Architecture (PS21/3 Resilience)

```
payments-service (:8013) → Stripe (FCA-authorised PSP)
                          ↓
                    No card data stored in Tranc3
                    PCI DSS scope = Stripe only
                    BAU recovery: <4 hours (alternate PSP configured)
```

**Alternate PSP:** Documented at `config/payments_failover.yaml` (to be created on PSP activation).

### Operational Resilience (PS21/3)

| Important Business Service | Maximum Tolerable Disruption | Recovery Mechanism |
|---|---|---|
| User authentication | 4 hours | P0 worker, manual failover |
| Payment processing | 24 hours | Alternate PSP switchover |
| AI inference | 4 hours | 5-tier fallback (Offline always available) |

## 6. Supplier Resilience (PS21/3)

Critical third-party suppliers for platform operation:

| Supplier | Service | Criticality | Fallback |
|---|---|---|---|
| Docker Hub | Container registry | High | Self-hosted Gitea (Zot) |
| Fly.io | Legacy backend | Medium | Self-hosted Citadel |
| Cloudflare | Legacy CF Workers | Low (migrating) | Traefik self-hosted |
| Stripe | Payments | High | Alternate PSP |

Supplier risk reviewed quarterly. Exit strategies documented per supplier.

## 7. AI Assistive-Only Positioning

Per `docs/policies/POL-AI-001-AI-Ethics-Governance.md`:

> All AI outputs are **assistive only**. Tranc3 AI components are classified EU AI Act Limited Risk. No output constitutes regulated advice in financial services, legal services, or medical practice.

This positioning is carried at:
1. `src/compliance/magna_carta.py` — MC-RULE-004 prohibited-use checks against a
   declared `use_case` (§2). `src/compliance/ai_governance.py` holds the model
   registry and risk classifier MC-RULE-004 calls into; its own `prohibited_uses`
   field is a descriptive attribute on a registry entry, not a gate.
2. API response headers — `X-AI-Assistive-Only: true` — **not implemented**; no
   response path sets this header.
3. UI disclaimers — **not implemented**; the disclaimer string in §2 appears
   nowhere in the codebase.

## 8. Compliance Mapping

| Requirement | Framework | Implementation | Status |
|---|---|---|---|
| No regulated activities without authorisation | FCA PRIN 1 | MC-RULE-004 prohibited-use checks | PARTIAL — enforced for callers that declare a `use_case`; no route declares one yet |
| Consumer Duty outcomes | FCA PRIN 2A | Policy library + DSR | PARTIAL |
| Financial promotion approval | COBS 4 | Marketing review process | PROGRAMME_ARTEFACT |
| Payment via authorised PSP only | FCA PRIN | payments-service → Stripe | COMPLIANT |
| Supplier resilience | PS21/3 | DR programme | PARTIAL |
| AI not as regulated advice | FCA guidance | magna_carta.py MC-RULE-004 + policies | PARTIAL — see §7; disclaimer and header unimplemented |

## 9. Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial FCA alignment programme |
| 2026-08-22 | Trancendos | §2 corrected — the claimed `PROHIBITED_USES` constant did not exist; perimeter implemented in `magna_carta.py` and pinned by tests. §7/§8 downgraded from COMPLIANT where the control was documented but absent. |
