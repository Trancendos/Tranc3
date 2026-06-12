# AI Governance Alignment

**Version:** 1.0.0 | **Date:** 2026-06-12 | **Owner:** Trancendos Platform Engineering
**Frameworks:** EU AI Act (2024/1689) · Magna Carta MC-RULE-004 · DEFSTAN REQ-AI-001

## 1. AI Risk Classification

Per EU AI Act Article 6 and Annex III, Tranc3 AI components are classified:

| Component | Classification | Rationale |
|---|---|---|
| infinity-ai inference gateway | **Limited Risk** | AI content generation — transparency required, not prohibited |
| Luminous AI brain | **Limited Risk** | Assistive AI, no autonomous binding decisions |
| tAImra digital twin | **Limited Risk** | User opt-in, transparent AI involvement |
| AI transparency headers | **Minimal Risk** | Labelling only |

**No Unacceptable Risk components are deployed.** The following are explicitly prohibited (see `src/compliance/ai_governance.py`):
- Biometric surveillance
- Social scoring
- Subliminal manipulation
- Prohibited profiling categories

## 2. Runtime Governance Controls

### MC-RULE-004 Enforcement

The `MagnaCarta` middleware evaluates MC-RULE-004 on every AI inference request:

```python
# src/compliance/ai_governance.py
PROHIBITED_USES = [
    "biometric_surveillance",
    "social_scoring",
    "subliminal_manipulation",
    "unauthorized_profiling",
    "autonomous_binding_financial_decisions",
    "unauthorized_health_diagnosis",
    "financial_advice_regulated",
]
```

Any request matching a prohibited use pattern returns HTTP 451 (Unavailable For Legal Reasons).

### Transparency Requirements

All AI-generated responses carry:
- `X-AI-Generated: true` header (planned — REQ-AI-003, Q3 2026)
- `X-AI-Model: <model_identifier>` header
- Assistive-only disclaimers in UI components

### Human Review Gate

High-risk automated decisions (score threshold >0.85) trigger:
1. Decision queued in `the-grid` workflow engine
2. Human reviewer notified via `notifications` service
3. 24-hour hold before execution
4. Audit trail written to The Observatory

## 3. Model Governance

### Approved Models

| Model | Provider | Use Case | Approval Date |
|---|---|---|---|
| phi-3-mini-4k-instruct | Microsoft/Ollama | General inference | 2026-06-12 |
| all-MiniLM-L6-v2 | HuggingFace | Embeddings | 2026-06-12 |
| OpenRouter :free models | OpenRouter | Fallback inference | 2026-06-12 |

### Model Change Process

New model onboarding requires:
1. CAB change request (via `cab_gate.register_change()`)
2. Bias measurement run (PROC-AI-002)
3. Security review (Cryptex team)
4. Town Hall approval (MC-RULE-007)

## 4. Bias Measurement Programme

Target metrics (Q3 2026 — first run):
- Demographic parity difference < 0.05
- Equalised odds difference < 0.05
- Calibration error < 0.02

Results published at `docs/evidence/BIAS-MEASUREMENT-RESULTS.md` (post-first-run).

## 5. Compliance Mapping

| Requirement | Framework | Implementation | Status |
|---|---|---|---|
| AI transparency labels | EU AI Act Art. 50 | X-AI-Generated header | PLANNED (Q3 2026) |
| Human oversight for high-risk | EU AI Act Art. 9 | Human review gate | COMPLIANT |
| Prohibited use blocking | EU AI Act Art. 5 | ai_governance.py | COMPLIANT |
| AI assistive positioning | FCA / Magna Carta | POL-AI-001 | COMPLIANT |
| Bias monitoring programme | EU AI Act Art. 9 | PROC-AI-002 | PLANNED |

## 6. Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial AI governance alignment document |
