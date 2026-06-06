# AI Governance — Trancendos Platform

**Status**: Baseline established · Formal certification pending  
**Last updated**: 2026-06-06  
**Owner**: Trancendos Engineering  
**Review cadence**: Quarterly (every 90 days)

---

## Framework Coverage

| Framework | Status | Notes |
|---|---|---|
| **EU AI Act (2024/1689)** | Partial | Art. 9, 13, 15, 50 addressed; Art. 16/17 pending |
| **ISO 42001:2023** | Partial | §6, 8, 9 in place; certification audit not yet scheduled |
| **NIST AI RMF 1.0** | Partial | GOVERN/MAP/MEASURE active; MANAGE partial |
| **UK AI Safety Framework** | Voluntary | Transparency & accountability principles applied |
| **GDPR (AI-related)** | Active | Art. 22 automated decision transparency via model cards |

---

## Registered AI Models

| Model ID | Name | EU AI Act Risk Tier | Audit Due |
|---|---|---|---|
| `luminous` | Luminous — Core AI Intelligence Engine | Limited | Quarterly |
| `turings_hub` | Turing's Hub — 3D AI Entity Builder | Limited | Quarterly |
| `mlflow_experiments` | MLflow Experiment Tracker | Minimal | Quarterly |

Full model cards available via: `GET /compliance/ai/model-cards`

---

## EU AI Act Compliance

### Art. 9 — Risk Management
- Risk classification function implemented (`classify_risk()`)
- Each model assigned a risk tier (minimal/limited/high/unacceptable)
- Use-case escalation rules applied at runtime (e.g. biometric → high-risk)
- **Gap**: No formal Annex III high-risk assessment completed

### Art. 13 — Transparency
- Model cards published for all registered AI components
- Known limitations documented per model
- Prohibited uses explicitly listed
- API endpoint: `GET /compliance/ai/model-cards`

### Art. 15 — Accuracy, Robustness, Cybersecurity
- Fairness metrics framework defined (demographic parity, equalised odds, calibration)
- All metrics currently **unmeasured** — requires live test dataset
- **Action required**: Run bias measurement suite against representative dataset
- Incident log tracks adverse AI behaviour: `POST /compliance/ai/incidents`

### Art. 50 — Transparency Obligations (Limited Risk)
- AI-generated content is identifiable in API responses
- Users interacting with AI entities (Turing's Hub) are informed of AI nature
- Personality profiles explicitly labelled as AI constructs

---

## ISO 42001:2023 Controls Mapping

| Clause | Control | Status |
|---|---|---|
| §4 Context | Interested parties, scope defined | ✅ Model registry + prohibited uses |
| §5 Leadership | AI policy | ⚠️ Policy documented here; not yet board-approved |
| §6 Planning | Risk assessment, objectives | ✅ Risk classification function + fairness metrics |
| §7 Support | Resources, awareness, documentation | ✅ Model cards + governance docs |
| §8 Operation | AI system lifecycle | ✅ Incident log + fairness report API |
| §9 Evaluation | Monitoring, audit | ⚠️ Endpoints operational; first formal audit pending |
| §10 Improvement | Nonconformity, continual improvement | ⚠️ Incident resolution workflow in place; improvement process informal |

---

## NIST AI RMF Coverage

### GOVERN
- AI governance module active (`src/compliance/ai_governance.py`)
- Model registry maintained with ownership and limitations
- Incident log operational

### MAP
- Model cards identify: intended use, prohibited uses, training data sources, limitations
- Risk tier assigned per model with escalation rules for use cases

### MEASURE
- Fairness metrics framework defined with thresholds
- Metrics currently unmeasured — requires live inference test data
- Incident count tracked per model per rolling 30-day window

### MANAGE (Partial)
- Incident logging and resolution workflow via API
- **Gap**: No automated remediation; no SLA on incident resolution
- **Gap**: No rollback/model versioning strategy documented

---

## Bias Testing Methodology

### Metrics Defined

| Metric | Target Threshold | Description |
|---|---|---|
| Demographic Parity Difference | < 0.1 | P(positive\|group A) - P(positive\|group B) |
| Equalised Odds Difference | < 0.1 | max(\|TPR diff\|, \|FPR diff\|) across groups |
| Individual Fairness Score | > 0.8 | Cosine similarity of outputs for similar inputs |
| Calibration Error | < 0.05 | Expected calibration error across confidence bins |

### Current Status
All metrics are **unmeasured**. To populate them:

1. Prepare a representative test dataset with demographic annotations
2. Run inference across all groups
3. Compute metrics and call `POST /compliance/ai/fairness-report/run`
4. Update `ModelCard.fairness_metrics` with measured values and `last_measured` timestamp

### Libraries (zero-cost, when needed)
- `fairlearn` (MIT) — demographic parity, equalised odds
- `aif360` (Apache 2.0) — comprehensive bias metrics
- Both can be added to `requirements-ai.txt` when measurement runs are implemented

---

## Incident Response Procedure

1. **Detection**: Adverse AI behaviour reported by user or automated monitor
2. **Log**: `POST /compliance/ai/incidents` with severity (low/medium/high/critical)
3. **Triage**: Engineering reviews within 24h (critical: 4h)
4. **Mitigation**: Implement fix or restrict model use case
5. **Resolve**: `PATCH /compliance/ai/incidents/{id}/resolve` with resolution notes
6. **Review**: Critical incidents trigger fairness re-assessment

**SLA targets** (aspirational — formalise in ITSM):
| Severity | Triage | Resolution |
|---|---|---|
| Critical | 4h | 24h |
| High | 24h | 72h |
| Medium | 72h | 2 weeks |
| Low | 1 week | Next sprint |

---

## Review Cadence

- **Quarterly**: Generate and review fairness report (`GET /compliance/ai/fairness-report`)
- **Annually**: Full model card review, update training data documentation
- **On deployment**: Risk classification review for any new model or major version
- **On incident**: Trigger fairness re-assessment for affected model

---

## Gaps & Roadmap

| Gap | Priority | Target |
|---|---|---|
| Bias measurement suite (live data) | P0 | Q3 2026 |
| ISO 42001 certification audit | P1 | Q4 2026 |
| Art. 16 registration (EU AI Act) | P1 | When required by regulation |
| MANAGE function — automated remediation | P2 | Q4 2026 |
| Expand model registry (new models) | P2 | Ongoing |
| Board-approved AI policy statement | P2 | Q3 2026 |
