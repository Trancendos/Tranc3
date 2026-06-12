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

The following are explicitly blocked by `src/compliance/ai_governance.py`:

```python
PROHIBITED_USES = [
    "financial_advice_regulated",           # COBS — regulated advice
    "autonomous_binding_financial_decisions", # MiFID II
    "investment_recommendation_personal",    # COBS 9A
    "credit_recommendation_regulated",       # CCA-regulated
]
```

AI outputs on financial topics carry the disclaimer: *"This is informational only and does not constitute regulated financial advice. Consult an FCA-authorised adviser."*

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

This positioning is enforced at:
1. `src/compliance/ai_governance.py` — runtime prohibited-use checks
2. API response headers — `X-AI-Assistive-Only: true` (planned Q3 2026)
3. UI disclaimers — in all AI-generated content surfaces

## 8. Compliance Mapping

| Requirement | Framework | Implementation | Status |
|---|---|---|---|
| No regulated activities without authorisation | FCA PRIN 1 | Prohibited-use checks | COMPLIANT |
| Consumer Duty outcomes | FCA PRIN 2A | Policy library + DSR | PARTIAL |
| Financial promotion approval | COBS 4 | Marketing review process | PROGRAMME_ARTEFACT |
| Payment via authorised PSP only | FCA PRIN | payments-service → Stripe | COMPLIANT |
| Supplier resilience | PS21/3 | DR programme | PARTIAL |
| AI not as regulated advice | FCA guidance | ai_governance.py + policies | COMPLIANT |

## 9. Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial FCA alignment programme |
