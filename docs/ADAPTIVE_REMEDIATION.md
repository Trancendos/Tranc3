# Adaptive Vulnerability Remediation System

**Status**: Active Implementation | **Last Updated**: 2026-09-05

## Overview

The Adaptive Vulnerability Remediation System is a **forward-looking, probabilistic approach** to security that moves beyond reactive patching. Instead of treating all vulnerabilities equally, it:

1. **Scores risk probabilistically** using exploitability, impact, and exposure
2. **Automates safe patches** (patch-level updates, non-breaking changes)  
3. **Predicts escalation** by monitoring attack chain development
4. **Documents decisions** with full traceability for compliance

## Philosophy: Proactive, Not Reactive

**Traditional (Reactive)**:
```
CVE published → Scanner finds it → Manual review → Patch → Deploy
```

**This Approach (Proactive)**:
```
Continuous monitoring → Risk scoring → Automated safe patches → Strategic decisions
```

**Goal**: Stay ahead of threats, not chase them.

## Risk Probability Model

### Core Formula
```
Risk Probability = P(Exploit) × P(Impact) × P(Exposure)
```

Each factor is **context-aware** for Tranc3 specifically.

### Exploitability P(Exploit) - 0 to 1
- **Attack vector**: local=0.3, adjacent=0.6, network=1.0
- **Attack complexity**: high=0.2, low=1.0  
- **Privileges required**: none=1.0, low=0.6, high=0.3
- **User interaction**: yes=0.3, no=1.0
- **Public exploit available**: +0.3
- **CISA KEV (actively exploited)**: +0.5

### Impact P(Impact) - 0 to 1
- **Base CIA triad**: Confidentiality/Integrity/Availability each 0-0.72
- **Tranc3-specific amplifiers**:
  - Uses AI model loading (torch.load): +0.3 (RCE vector)
  - Handles PII: +0.2
  - Internet-exposed endpoint: +0.15
  - In authentication path: +0.25

### Exposure P(Exposure) - 0 to 1
- **Package usage**: transitive=0.3, direct=0.7, critical=1.0
- **Vulnerable code path hit rate**: 0-1.0
- **Currently deployed**: ×1.2 amplifier
- **Attack chain length**: 1/(1+steps) penalty

## Decision Logic

```python
risk_score = cvss_score * p_exploit * p_impact * p_exposure

if CRITICAL and risk_score > 3.0:
    remediate_immediately()          # Same day
elif HIGH and risk_score > 2.0:
    if fixed_version_exists:
        remediate_within_7_days()    # Urgent
elif MEDIUM and risk_score > 1.5:
    if easy_patch:
        remediate_proactively()      # Auto-patch
    else:
        monitor_for_escalation()     # Watch for signals
else:
    accept_and_document()            # Audit trail
```

## Real-World Example: torch Vulnerabilities

**The Situation**: Trivy flags 10 PYSEC advisories in `torch==2.13.0`

**CVSS**: Critical/High (7.5-9.8)

**Context-Aware Assessment**:
- **Attack vector**: Local only (requires local code execution first)
- **Vulnerable code paths**: torch.jit.script, torch.lstm_cell, RNN unpacking  
- **Tranc3 usage pattern**:
  - ✅ Inference: tokenizer → model.forward() → output
  - ❌ JIT compilation: Never used
  - ❌ Model deserialization: weights_only=True enforced
  - ❌ Direct tensor manipulation: Sanitized through tokenizer
  
- **Attack chain**: 4+ steps required, all needing local code execution
- **Mitigations in place**: Input validation, weights_only flag, no JIT

**Probabilistic Scoring**:
```
P(Exploit) = 0.3 (local) × 1.0 (low complexity) × 0.7 (privileges) × 1.0 (no UI) = 0.21
P(Impact)  = 0.0 (mitigated, never hits vulnerable paths) = 0.0
P(Exposure) = 0.1 (rarely hit code paths)

Risk = 7.5 (CVSS) × 0.21 × 0.0 × 0.1 = 0.0 (mitigated!)
```

**Decision**: **ACCEPT RISK**
- Already documented in SECURITY-ASSESSMENT.md
- Mitigations prevent exploitation
- No upstream fix available
- Monitoring for: new exploit gadgets, upstream patches, JIT usage intro

---

## Escalation Monitoring

Automatically escalates to HIGH/CRITICAL if:

| Signal | Check Frequency | Action |
|--------|-----------------|--------|
| Public exploit released | Daily (exploit-db API) | Alert + re-score |
| Added to CISA KEV | Real-time | Escalate to CRITICAL |
| Related CVE pattern | Per-scan | Flag for analysis |
| Attack chain shortens | Manual review | Investigate |
| Patch released upstream | Daily (NVD feed) | Force review |

---

## Automation Tiers

### ✅ Auto-Patch (Trivial)
- Patch-level version bump: X.Y.Z → X.Y.(Z+1)
- No major/minor version change
- Merged automatically after tests pass

**Example**: cryptography 50.0.1 → 50.0.2 ✅

### 🔄 Manual Review (Moderate)
- Minor/major version bump
- Dependency cascade effect
- Needs human approval before merge

**Example**: torch 2.13.0 → 2.14.0 ⚠️

### 📝 Accept & Document (Hard)
- No upstream fix available
- Mitigations prevent exploitation
- Documented with full context

**Example**: PYSEC-2026-1325 in ecdsa (no fix, HS256-only usage) ✅

---

## Remediation Tiers & SLA

| Tier | Severity | Score | Response | Action |
|------|----------|-------|----------|--------|
| **1** | CRITICAL | > 3.0 | Immediate (same day) | Auto-patch if trivial; PR + on-call review |
| **2** | HIGH | > 2.0 | Urgent (7 days) | PR created; scheduled review |
| **3** | MEDIUM | > 1.5 | Planned (30 days) | Auto-patch if trivial; else monitor |
| **4** | Accepted | N/A | N/A | Document + annual review |

---

## Implementation Files

### Core Engine
- **scripts/adaptive_vulnerability_remediation.py**
  - `VulnerabilityRiskProfile`: Per-CVE assessment
  - `ExploitabilityFactors`, `ImpactFactors`, `ExposureFactors`: Probability models
  - `RemediationPlan`: Groups findings by urgency
  - `DependencyUpgrader`: Safe version updates
  - `TrivyIgnoreManager`: Documents accepted risks

### Automation
- **.github/workflows/adaptive-security-remediation.yml**
  - Triggered by Trivy scan completion
  - Analyzes findings with risk scoring
  - Creates PRs for moderate/hard remediations
  - Auto-patches trivial fixes
  - Generates audit trail

### Documentation
- **docs/ADAPTIVE_REMEDIATION.md**: This file
- **.trivyignore**: Accepted risks with justification
- **REMEDIATION_LOG.md**: Generated per-PR with analysis
- **SECURITY.md**: High-level SLA + reporting

---

## Workflow Integration

```
┌─────────────────────────────────────────────┐
│   Trivy Security Scan (weekly + on-push)   │
└────────────────────┬────────────────────────┘
                     ↓
┌─────────────────────────────────────────────┐
│  Adaptive Remediation (auto-triggered)     │
│                                             │
│  1. Download Trivy SARIF artifacts         │
│  2. Parse vulnerability findings           │
│  3. Probabilistic risk scoring             │
│  4. Auto-patch safe updates (branch)       │
│  5. Escalation analysis (forecast)         │
│  6. Create PR for complex remediations     │
│  7. Comment on tracking issues             │
└────────┬───────────────┬───────────────────┘
         ↓               ↓
    [Auto-patches]  [PR Created]  [Escalation
     (trivial/easy)  (moderate)    Forecast]
         │               │             │
         └───────────────┼─────────────┘
                         ↓
         Approver reviews + merges
         (human in the loop)
```

---

## Metrics Tracked

Over time, we monitor:
- **Total findings per scan**: Trend over quarters
- **Remediable vs. accepted split**: How much is actionable
- **Time to patch**: Detection → deploy cycle time
- **Escalations caught**: MEDIUM → HIGH → CRITICAL jumps
- **False positive rate**: Trivy vs. manual verification
- **Auto-patch success rate**: No regressions from automated updates

---

## Compliance & Audit Trail

Every security decision is logged:

**Auto-Patches**:
- ✅ Commit message with CVE refs
- ✅ Test results in CI/CD
- ✅ Automated merge after approval

**Accepted Risks**:
- ✅ Entry in .trivyignore with justification
- ✅ Section in SECURITY.md 
- ✅ Documented in REMEDIATION_LOG.md per-PR
- ✅ Annual review trigger

**Escalations**:
- ✅ Workflow logs + email alerts
- ✅ GitHub issue auto-created
- ✅ On-call notification

---

## Key Principles

### 1. Probabilistic, Not Binary
Don't treat CVSS as gospel. Context matters.
- torch with local-only attack + no JIT = low risk, accept
- cryptography with network RCE + in auth path = high risk, patch immediately

### 2. Automate Safe Actions
Patch-level updates are almost always safe → auto-merge after tests.
Major bumps need human review → create PRs.

### 3. Forward-Looking
Monitor escalation signals (KEV, exploits, related CVEs).
Don't wait for the next scan.

### 4. Document Everything
Accepted risks need full context so you never silently regress.
Audit trail for compliance.

### 5. Stay Ahead
Weekly scans + daily escalation checks + predictive modeling.
Be proactive, not reactive.

---

## Further Reading

- [SECURITY.md](../SECURITY.md) — Vulnerability reporting SLA
- [SECURITY-ASSESSMENT.md](./SECURITY-ASSESSMENT.md) — Per-CVE deep dive (torch, sentencepiece, etc.)
- [SECURITY-POSTURE-MATRIX.md](./governance/SECURITY-POSTURE-MATRIX.md) — Holistic security posture
- [.trivyignore](../.trivyignore) — Current accepted risks

## Contact

- **Security Team**: security@trancendos.ai
- **Incident Response**: [See docs/INCIDENT_RESPONSE.md]
- **Escalations**: Create issue with label `security:urgent`
