# POL-AI-001 — AI Ethics & Governance Policy
**Version:** 1.0.0 | **Owner:** Trancendos Platform Engineering | **Classification:** UNCLASSIFIED — PUBLIC  
**Effective:** 2026-06-12 | **Review Cycle:** Annual | **Approver:** Platform Owner

## 1. Purpose
Establish ethical principles and governance controls for AI systems operating within the Trancendos platform, in alignment with the EU AI Act (Regulation 2024/1689), ISO 42001, and Magna Carta Rules MC-RULE-004 (AI Governance) and MC-RULE-008 (AI Transparency).

## 2. AI Classification
All AI models in use are classified as **Limited Risk** (EU AI Act Title IV) or below:
- No high-risk AI applications (employment decisions, credit scoring, biometric identification)
- All AI outputs are advisory/assistive only — no autonomous decision-making on regulated matters
- FCA alignment: AI is explicitly prohibited from providing regulated financial advice

## 3. Prohibited AI Uses
The following uses are permanently prohibited and enforced by `src/compliance/magna_carta.py` (MC-RULE-004):
- Mass surveillance or biometric tracking
- Psychological manipulation
- Social scoring
- Deepfake generation without consent
- Autonomous weapons systems
- Circumvention of security controls
- Generation of regulated financial advice

## 4. AI Transparency Requirements
All AI-generated responses must:
- Include model identifier and provider in response headers (`X-AI-Model`, `X-AI-Provider`)
- Be clearly identifiable as AI-generated to end users
- Not impersonate a human without disclosure
- Provide reasoning/explanation on request

## 5. Human Oversight
- All AI recommendations are advisory; humans make final decisions on consequential matters
- Users can always escalate to a human operator
- AI model outputs are logged to The Observatory for audit and review
- Regular bias measurement per PROC-AI-002

## 6. Zero-Cost Sovereignty
AI inference follows the 5-tier fallback (MC-RULE-005): Ollama (local) → HuggingFace free → OpenRouter free → Fly.io → Offline stub. No paid API dependency by design.

## 7. Model Governance
- All model weights are validated before loading (`weights_only=True`, integrity checks)
- No untrusted model loading
- Model version changes require Normal change request (POL-OPS-002)

## 8. Bias and Fairness
Bias measurement programme (PROC-AI-002) runs quarterly. Results reviewed by Platform Owner. Significant bias findings trigger model replacement or fine-tuning.

## 9. Policy Review
This policy is reviewed annually or following significant changes to EU AI Act guidance, ISO 42001 updates, or platform AI capabilities.

---
*Magna Carta Rule Reference: MC-RULE-004 (AI Governance), MC-RULE-005 (Zero-Cost), MC-RULE-008 (Transparency)*  
*DEFSTAN Reference: REQ-AI-001, REQ-AI-002, REQ-AI-003*  
*FCA Reference: AI assistive-only positioning (not Part 4A regulated)*
