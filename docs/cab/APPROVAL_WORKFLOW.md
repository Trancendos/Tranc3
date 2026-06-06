# Change Advisory Board — Approval Workflow

**Document ID:** CAB-003  
**DEF STAN ref:** REQ-CM-006  
**Owner:** The Town Hall  
**Version:** 1.0  
**Date:** 2026-06-06  

---

## 1. Change Request Template

When raising a **Significant** or **Emergency** PR, include the following block
in the PR description:

```markdown
## Change Advisory Board Request

**Change Type:** Significant | Emergency | Major
**CAB Reference:** CAB-YYYY-NNN  (assign sequentially per year)

### 1. Summary of Change
<!-- One paragraph describing what is changing and why -->

### 2. Impact Assessment
| Dimension | Assessment |
|---|---|
| Services affected | <!-- list service names and ports --> |
| Downtime expected | <!-- Yes / No / Rolling --> |
| Data migrations | <!-- Yes / No; describe if Yes --> |
| Security boundary change | <!-- Yes / No; describe if Yes --> |
| Compliance impact | <!-- Does this affect any REQ-* items? --> |

### 3. Blast Radius
<!-- Worst-case description of what breaks if the change fails -->

### 4. Rollback Plan
- [ ] Step 1:
- [ ] Step 2:
- [ ] Verification:

### 5. Test Evidence
- [ ] `make test-fast` passing
- [ ] `make compliance-ci` passing — score: ___%
- [ ] `make gate-check` — gates: ___/13

### 6. CAB Checklist (completed by reviewers)
- [ ] Impact assessment reviewed
- [ ] Rollback plan is credible
- [ ] Compliance gate is green
- [ ] No new PLANNED/PARTIAL requirements introduced without waiver
- [ ] Security sign-off (if security-boundary change)
```

---

## 2. Approval Process

### Significant Change

```
1. Requestor raises PR with CAB template completed.
2. Requestor applies label: cab-review-required
3. Requestor runs: make compliance-ci && make gate-check
4. CAB Chair assigns two reviewers within 1 business day.
5. Reviewers approve or request changes within 2 business days.
6. On 2 approvals: label → cab-approved; PR may be merged.
7. Chair records approval in the CAB log (§4).
```

### Emergency Change

```
1. Requestor raises PR with abbreviated template (impact + rollback required).
2. Requestor pages CAB Chair directly.
3. Chair reviews and approves within 4 hours.
4. Change deployed immediately after Chair approval.
5. Second CAB member completes post-review within 24 hours.
6. Full template completed retrospectively within 48 hours.
```

### Major Change

```
1. RFC document circulated ≥ 5 business days before planned PR.
2. Synchronous CAB meeting (or async with all members within 2 days).
3. Full board consensus required.
4. Post-implementation review mandatory within 5 business days.
```

---

## 3. Labels

| Label | Meaning |
|---|---|
| `cab-review-required` | Awaiting CAB review |
| `cab-approved` | Quorum reached; cleared for merge |
| `cab-post-review` | Emergency deployed; post-review pending |
| `cab-rejected` | Rejected; requestor must rework |

---

## 4. CAB Approval Log

| CAB Ref | PR | Date | Type | Approvers | Outcome |
|---|---|---|---|---|---|
| CAB-2026-001 | #99 | 2026-06-06 | Significant | @trancendos | APPROVED — Platform compliance uplift (TR3-001–TR3-011, WAV-001–WAV-003) |

---

## 5. CAB Reference Numbering

Format: `CAB-YYYY-NNN` — year + zero-padded sequential number, restarting each year.
