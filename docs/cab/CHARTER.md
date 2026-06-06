# Change Advisory Board — Charter

**Document ID:** CAB-001  
**DEF STAN ref:** REQ-CM-006 (DEF STAN 00-044 Configuration Management)  
**Owner:** The Town Hall  
**Version:** 1.0  
**Date:** 2026-06-06  
**Review cycle:** Annually or after any Major change classification event

---

## 1. Purpose

The Change Advisory Board (CAB) is the governance body responsible for reviewing,
approving, and overseeing Significant and Emergency changes to the Trancendos platform.
It exists to protect platform stability, security, and DEFSTAN compliance while enabling
the engineering velocity required to meet platform objectives.

The CAB operates as a **lightweight, async-first board** aligned with ITIL Change
Management principles, adapted for a small engineering team running a self-hosted
zero-cost architecture.

---

## 2. Scope

The CAB has authority over all changes classified as:

| Classification | Trigger | CAB Required |
|---|---|---|
| **Standard** | Pre-approved template, low-risk, repeatable | No — auto-approved |
| **Normal** | Typical feature/bugfix PR | No — 1 peer reviewer |
| **Significant** | Architectural change, new service, security-boundary change, new external dependency | **Yes — 2 CAB members** |
| **Emergency** | Production hotfix, active incident response | **Yes — 1 CAB chair, post-review within 24h** |

See `../change-request-process.md` §2 for classification criteria.

---

## 3. Mission

1. **Protect compliance** — Ensure all Significant changes pass the DEFSTAN compliance gate before merge.
2. **Reduce risk** — Assess blast radius, rollback plan, and security implications of proposed changes.
3. **Maintain traceability** — Every Significant/Emergency change must have a documented approval trail.
4. **Enable speed** — Decisions must be made within the SLAs defined in §6. The CAB exists to unblock, not delay.

---

## 4. Decision Authority

| Change Type | Minimum Approval | Quorum |
|---|---|---|
| Significant | 2 CAB members (must include ≥1 from Security or Architecture) | 2 |
| Emergency | 1 CAB Chair (post-review within 24h by a second member) | 1 |
| Major (platform-wide, multi-service) | Full board + post-implementation review | 3 |

All approvals are recorded as Forgejo PR reviews with the label `cab-approved`.

---

## 5. Responsibilities

### Board Chair (rotating, quarterly)
- Owns the CAB agenda and SLA enforcement
- Escalation point for tie-breaks and emergency approvals
- Files post-implementation reviews for Emergency changes

### Members
- Review change submissions within SLA (see §6)
- Assess: impact, rollback plan, compliance gate status, test coverage
- Approve (`:+1:` review) or Request Changes with written rationale
- Flag if `make compliance-ci` or `make gate-check` has not been run

### Engineering (requestor)
- Classifies the change correctly before raising the PR
- Completes the change request template (see `APPROVAL_WORKFLOW.md`)
- Runs `make compliance-ci` and attaches the report to the PR
- Ensures rollback plan is documented

---

## 6. SLAs

| Change Type | Review SLA | Escalation |
|---|---|---|
| Significant | 2 business days | Chair may approve if quorum not met after SLA |
| Emergency | 4 hours | Chair approves immediately; post-review within 24h |
| Major | 5 business days | Full board meeting required |

---

## 7. Meeting Cadence

The CAB operates **asynchronously** through Forgejo PR reviews as the primary mechanism.
A synchronous review session is convened only for Major changes or when async consensus
cannot be reached within SLA.

---

## 8. Governance Links

- Change Request Process: `../change-request-process.md`
- Approval Workflow & Templates: `APPROVAL_WORKFLOW.md`
- CAB Membership Register: `MEMBERSHIP.md`
- Compliance Gate: `.forgejo/workflows/compliance-gate.yml`
- DEFSTAN Register: `../../compliance/register.yaml`
