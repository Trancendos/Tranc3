# Documentation Audit (DOC_AUDIT)

> **Purpose:** Catalog every documentation file in the repo (root-level `.md`/`.rst`/`.txt` and the entire `docs/` tree), record its metadata, summarize its purpose, assess its current state, and flag docs that reference code paths or other docs that no longer exist.

> **Generated:** 2026-08-21  |  **Scope:** repo root + `docs/` (subdirectories included)  |  **Total doc files audited:** 215

## 1. Summary

| Metric | Value |
|---|---|
| Total documentation files | 215 |
| Repo-root files | 12 |
| `docs/` files | 203 |
| Categories | 17 |
| Orphaned docs (no inbound link from any other doc) | 151 |
| Files flagged outdated/missing-ref | see Findings |

### Files by category

| Category | Count |
|---|---|
| Service Doc | 44 |
| Solution Pack | 44 |
| Governance | 39 |
| Docs Root | 19 |
| Architecture | 17 |
| Repo Root | 12 |
| Compliance | 10 |
| DefStan Standards | 9 |
| Runbook | 4 |
| CAB (Change Advisory) | 3 |
| Policy | 3 |
| Procedure | 3 |
| Evidence | 2 |
| Framework/Templates | 2 |
| Privacy | 2 |
| Engineering | 1 |
| Template | 1 |

## 2. Master Catalog

Columns: **Path** · **KB** (size) · **W** (word count) · **§** (section/heading count) · **Modified** · **Cat** (category) · **Purpose** (first heading) · **State** · **Orphan** (✓ if no inbound doc link).

| Path | KB | W | § | Modified | Cat | Purpose | State | Orphan |
|---|---|---|---|---|---|---|---|---|
| `ARCHITECTURE_THREAT_MODEL.md` | 25.6 | 3730 | 35 | 2026-08-21 | Repo Root | Tranc3 Architecture Threat Model | complete |  |
| `CLAUDE.md` | 46.1 | 6569 | 35 | 2026-08-21 | Repo Root | CLAUDE.md | complete (verified code paths exist) | ✓ |
| `CODE_OF_CONDUCT.md` | 6.8 | 992 | 0 | 2026-08-21 | Repo Root | CODE_OF_CONDUCT.md | complete | ✓ |
| `PLATFORM_ENTITIES.md` | 23.4 | 3575 | 8 | 2026-08-21 | Repo Root | Trancendos Platform Entity Hierarchy | complete | ✓ |
| `README.md` | 9.9 | 1198 | 40 | 2026-08-21 | Repo Root | TRANC3 — Core AI Platform | complete | ✓ |
| `SECURITY.md` | 9.4 | 1337 | 23 | 2026-08-21 | Repo Root | Tranc3 Security Policy | complete |  |
| `SECURITY_ALERT_REGISTER.md` | 6.2 | 944 | 9 | 2026-08-21 | Repo Root | Security Alert Register | complete (generated) | ✓ |
| `docs/01-MAGNACARTA-FOUNDATION.md` | 3.1 | 459 | 9 | 2026-08-21 | Docs Root | Magna Carta Foundation — Zero-Cost Sovereignty Principle | complete | ✓ |
| `docs/API_REFERENCE.md` | 9.8 | 1388 | 70 | 2026-08-21 | Docs Root | Tranc3 API Reference | outdated (refs missing api_enhanced.py; v0.1.0) | ✓ |
| `docs/DEPLOYMENT_GUIDE.md` | 8.0 | 1096 | 55 | 2026-08-21 | Docs Root | Tranc3 Deployment Guide — Zero-Cost Infrastructure | needs-verification |  |
| `docs/DEPLOYMENT_INDEX.md` | 3.2 | 394 | 7 | 2026-08-21 | Docs Root | Deployment Documentation Index | complete (index) | ✓ |
| `docs/DEPLOYMENT_RUNBOOK.md` | 22.8 | 3169 | 149 | 2026-08-21 | Docs Root | Tranc3 Production Deployment Runbook | needs-verification |  |
| `docs/DESIGN_SYSTEM.md` | 15.5 | 1873 | 52 | 2026-08-21 | Docs Root | Trancendos Platform — Design System | needs-verification | ✓ |
| `docs/GO_LIVE_GAP_ANALYSIS.md` | 27.9 | 4167 | 19 | 2026-08-21 | Docs Root | Go-Live Gap Analysis — Trancendos Estate (4 repos) | needs-verification | ✓ |
| `docs/HOSTIPC_RISK_ACCEPTANCE.md` | 2.0 | 258 | 7 | 2026-08-21 | Docs Root | hostIPC Risk Acceptance — Nanoservice Shared Memory | needs-verification |  |
| `docs/PRODUCTION_ROADMAP.md` | 3.2 | 504 | 9 | 2026-08-21 | Docs Root | Production Readiness Roadmap | needs-verification | ✓ |
| `docs/RESEARCH_FINDINGS.md` | 22.8 | 3120 | 38 | 2026-08-21 | Docs Root | Tranc3 Research Findings — Cross-Repo Intelligence & Frontier Technologies | needs-verification | ✓ |
| `docs/SECURITY-ASSESSMENT.md` | 6.8 | 873 | 20 | 2026-08-21 | Docs Root | Tranc3 Security Vulnerability Assessment | needs-verification | ✓ |
| `docs/SECURITY_RESEARCH_FINDINGS.md` | 20.0 | 2999 | 70 | 2026-08-21 | Docs Root | Tranc3 Research Findings — Phase 3 Comprehensive Discovery | needs-verification | ✓ |
| `docs/THE_TOWN_HALL.md` | 2.7 | 321 | 7 | 2026-08-21 | Docs Root | The Town Hall | needs-verification | ✓ |
| `docs/WIKI_INDEX.md` | 5.7 | 788 | 9 | 2026-08-21 | Docs Root | Trancendos Documentation Index | complete (index) | ✓ |
| `docs/WINDOWS_DEPLOY.md` | 3.9 | 523 | 6 | 2026-08-21 | Docs Root | Windows deploy (CLOUD_ONLY / Fly.io) | needs-verification |  |
| `docs/ZERO_COST_VENDOR_MATRIX.md` | 8.4 | 1260 | 10 | 2026-08-21 | Docs Root | Zero-Cost Vendor Matrix | needs-verification | ✓ |
| `docs/architecture/AS-BUILT-ARCHITECTURE.md` | 5.2 | 677 | 14 | 2026-08-21 | Architecture | Tranc3 — As-Built Architecture | needs-verification | ✓ |
| `docs/architecture/BLUEPRINT.md` | 5.7 | 537 | 10 | 2026-08-21 | Architecture | Tranc3 Architecture Blueprint | needs-verification | ✓ |
| `docs/architecture/BRANCH-SALVAGE-ANALYSIS.md` | 4.7 | 715 | 6 | 2026-08-21 | Architecture | Branch salvage analysis — what is actually left in 78 stale branches | needs-verification | ✓ |
| `docs/architecture/CONTROL-TO-COMPONENT-MAP.md` | 4.1 | 584 | 13 | 2026-08-21 | Architecture | Control-to-Component Mapping | needs-verification | ✓ |
| `docs/architecture/PROACTIVE_SYSTEMS.md` | 10.2 | 1080 | 13 | 2026-08-21 | Architecture | Proactive Systems Architecture | needs-verification | ✓ |
| `docs/architecture/PYTHON-3.14-UPGRADE-ASSESSMENT.md` | 19.1 | 2877 | 10 | 2026-08-21 | Architecture | Python 3.11 → 3.14 Upgrade Assessment | needs-verification | ✓ |
| `docs/architecture/SERVICE-REVIEW.md` | 16.7 | 1896 | 78 | 2026-08-21 | Architecture | Platform Service Review | needs-verification | ✓ |
| `docs/architecture/SHARED-FUNCTIONAL-SERVICES-CORE.md` | 10.9 | 1594 | 11 | 2026-08-21 | Architecture | Shared Functional Services Core (SFSC) — the `Dimensional` package | needs-verification | ✓ |
| `docs/architecture/TEST-INTELLIGENCE.md` | 10.1 | 1591 | 11 | 2026-08-21 | Architecture | Test intelligence — the CircleCI question, answered in-platform | needs-verification | ✓ |
| `docs/architecture/THREE-LANE-TRANSPORT.md` | 8.4 | 1296 | 6 | 2026-08-21 | Architecture | Three-Lane Transport and the Terminal Hub | needs-verification | ✓ |
| `docs/architecture/decisions/TASD-001-circuit-breaker-consolidation.md` | 17.4 | 2190 | 19 | 2026-08-21 | Architecture | TASD-001 — Circuit Breaker Consolidation | needs-verification | ✓ |
| `docs/architecture/ea-workbook/README.md` | 12.1 | 1687 | 8 | 2026-08-21 | Architecture | EA / CMDB Workbook | complete | ✓ |
| `docs/architecture/ea-workbook/api-spec-template.md` | 8.6 | 915 | 4 | 2026-08-21 | Architecture | API Specification Template (OpenAPI 3.1) | needs-verification | ✓ |
| `docs/architecture/ea-workbook/compliance-and-pipeline.md` | 7.6 | 1048 | 10 | 2026-08-21 | Architecture | Compliance Mapping & Deployment Pipeline | needs-verification | ✓ |
| `docs/architecture/ea-workbook/runbooks.md` | 11.0 | 1488 | 32 | 2026-08-21 | Architecture | Operational Runbooks — Anchor Services | needs-verification | ✓ |
| `docs/architecture/infrastructure-modes.md` | 9.2 | 899 | 6 | 2026-08-21 | Architecture | Trancendos Infrastructure Architecture — Mermaid Diagrams | needs-verification | ✓ |
| `docs/architecture/master-schema.md` | 11.9 | 1926 | 16 | 2026-08-21 | Architecture | Trancendos Master Schema Documentation | needs-verification | ✓ |
| `docs/cab/APPROVAL_WORKFLOW.md` | 3.2 | 523 | 16 | 2026-08-21 | CAB (Change Advisory) | Change Advisory Board — Approval Workflow | needs-verification | ✓ |
| `docs/cab/CHARTER.md` | 3.8 | 570 | 12 | 2026-08-21 | CAB (Change Advisory) | Change Advisory Board — Charter | needs-verification | ✓ |
| `docs/cab/MEMBERSHIP.md` | 1.7 | 265 | 5 | 2026-08-21 | CAB (Change Advisory) | Change Advisory Board — Membership Register | needs-verification | ✓ |
| `docs/change-request-process.md` | 3.9 | 560 | 13 | 2026-08-21 | Docs Root | Change Request Process | needs-verification | ✓ |
| `docs/compliance/AI_GOVERNANCE.md` | 6.2 | 955 | 21 | 2026-08-21 | Compliance | AI Governance — Trancendos Platform | needs-verification | ✓ |
| `docs/compliance/COMPLIANCE-ACTION-TRACKER.md` | 2.4 | 435 | 5 | 2026-08-21 | Compliance | Compliance Action Tracker | needs-verification | ✓ |
| `docs/compliance/COMPLIANCE-BLUEPRINT.md` | 4.1 | 622 | 17 | 2026-08-21 | Compliance | Compliance Operating Model — Tranc3 Platform | needs-verification | ✓ |
| `docs/compliance/FCA-ALIGNMENT.md` | 4.6 | 662 | 11 | 2026-08-21 | Compliance | FCA Alignment Programme | needs-verification | ✓ |
| `docs/compliance/HIPAA-ALIGNMENT.md` | 4.7 | 696 | 18 | 2026-08-21 | Compliance | HIPAA Alignment Programme | needs-verification | ✓ |
| `docs/compliance/ISO27001_SOA.md` | 13.8 | 2254 | 9 | 2026-08-21 | Compliance | ISO 27001:2022 — Statement of Applicability (SOA) | needs-verification | ✓ |
| `docs/compliance/RISK_REGISTER.md` | 11.9 | 1923 | 16 | 2026-08-21 | Compliance | ISO 27001:2022 — Information Security Risk Register | needs-verification | ✓ |
| `docs/compliance/SOC2-EVIDENCE-SCHEDULE.md` | 4.5 | 701 | 14 | 2026-08-21 | Compliance | SOC 2 Type II Evidence Schedule | needs-verification | ✓ |
| `docs/compliance/SOC2_TYPE_II.md` | 12.4 | 1941 | 19 | 2026-08-21 | Compliance | SOC 2 Type II — Trust Services Criteria Mapping | needs-verification | ✓ |
| `docs/compliance/TRANC3-REGISTER-BRIDGE.md` | 3.5 | 476 | 18 | 2026-08-21 | Compliance | Tranc3 Register Bridge — Magna Carta ↔ DEFSTAN Mapping | needs-verification | ✓ |
| `docs/credential-rotation-advisory.md` | 5.4 | 767 | 11 | 2026-08-21 | Docs Root | Credential Rotation Advisory | needs-verification | ✓ |
| `docs/defstan/COMPLIANCE_REGISTER.md` | 7.2 | 1104 | 10 | 2026-08-21 | DefStan Standards | Compliance Register — Tranc3 / Trancendos Platform | needs-verification | ✓ |
| `docs/defstan/README.md` | 4.1 | 575 | 15 | 2026-08-21 | DefStan Standards | DEFSTAN Compliance Framework — Tranc3 / Trancendos Platform | complete | ✓ |
| `docs/defstan/standards/00-044-configuration-management.md` | 1.8 | 210 | 9 | 2026-08-21 | DefStan Standards | DEF STAN 00-044 — Configuration Management | needs-verification | ✓ |
| `docs/defstan/standards/00-055-safety-software.md` | 3.6 | 433 | 10 | 2026-08-21 | DefStan Standards | DEF STAN 00-055 — Safety-Related Software | needs-verification | ✓ |
| `docs/defstan/standards/00-056-safety-management.md` | 2.3 | 257 | 10 | 2026-08-21 | DefStan Standards | DEF STAN 00-056 — Software Development | needs-verification | ✓ |
| `docs/defstan/standards/00-600-supportability.md` | 2.4 | 256 | 10 | 2026-08-21 | DefStan Standards | DEF STAN 00-600 — Supportability (ILS) | needs-verification | ✓ |
| `docs/defstan/standards/00-700-information-assurance.md` | 6.7 | 795 | 15 | 2026-08-21 | DefStan Standards | DEF STAN 00-700 — Information Assurance | needs-verification | ✓ |
| `docs/defstan/standards/05-057-ietm.md` | 2.3 | 257 | 10 | 2026-08-21 | DefStan Standards | DEF STAN 05-057 — Technical Documentation (IETM-inspired) | needs-verification | ✓ |
| `docs/defstan/standards/05-086-quality-assurance.md` | 2.1 | 231 | 10 | 2026-08-21 | DefStan Standards | DEF STAN 05-086 — Quality Assurance | needs-verification | ✓ |
| `docs/engineering/TRANC3-INTEGRATION-GUIDE.md` | 5.2 | 640 | 34 | 2026-08-21 | Engineering | Tranc3 — Magna Carta Integration Guide | needs-verification | ✓ |
| `docs/evidence/PEN-TEST-PROGRAMME.md` | 2.9 | 471 | 16 | 2026-08-21 | Evidence | Penetration Test Programme | needs-verification | ✓ |
| `docs/evidence/POLICY-ATTESTATION-REGISTER.md` | 1.8 | 274 | 8 | 2026-08-21 | Evidence | Policy Attestation Register | needs-verification | ✓ |
| `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` | 14.3 | 2113 | 9 | 2026-08-21 | Framework/Templates | Design Governance Framework — Trancendos Platform | needs-verification | ✓ |
| `docs/framework/SERVICE-DOC-PACK-TEMPLATE.md` | 10.5 | 1531 | 15 | 2026-08-21 | Framework/Templates | Service Doc-Pack Template — `<Service Name>` | needs-verification | ✓ |
| `docs/governance/ACCEPTABLE-USE-POLICY.md` | 8.8 | 1241 | 7 | 2026-08-21 | Governance | Trancendos Platform — Acceptable Use Policy & Location Subscription Terms | needs-verification | ✓ |
| `docs/governance/ACCESS-CONTROL-GOVERNANCE.md` | 9.2 | 1223 | 6 | 2026-08-21 | Governance | Access Control Governance | needs-verification | ✓ |
| `docs/governance/ACCESSIBILITY-STANDARDS.md` | 5.5 | 774 | 6 | 2026-08-21 | Governance | Accessibility Standards | needs-verification | ✓ |
| `docs/governance/AI-AGENT-BOT-TIER-MATRIX.md` | 6.1 | 780 | 8 | 2026-08-21 | Governance | AI ↔ Agent ↔ Bot Tier Matrix | needs-verification |  |
| `docs/governance/AI-BOM.md` | 7.2 | 1084 | 9 | 2026-08-21 | Governance | AI-BOM — the models this platform consumes | needs-verification |  |
| `docs/governance/AI-GOVERNANCE-CONSTITUTION.md` | 21.8 | 2974 | 16 | 2026-08-21 | Governance | AI Governance Constitution | needs-verification | ✓ |
| `docs/governance/AI-RELATIONSHIP-MATRIX.md` | 12.6 | 1843 | 10 | 2026-08-21 | Governance | AI-to-AI Relationship Matrix, Activity Feed & Location Brochure | needs-verification | ✓ |
| `docs/governance/BOM-MATRIX.md` | 11.2 | 1590 | 6 | 2026-08-21 | Governance | BOM Matrix — Bills of Materials Across the Platform | needs-verification |  |
| `docs/governance/CODE-COMPLIANCE-MATRIX.md` | 6.0 | 686 | 7 | 2026-08-21 | Governance | Code Compliance Matrix | needs-verification | ✓ |
| `docs/governance/CONTINUOUS-IMPROVEMENT-PROGRAMME.md` | 3.8 | 625 | 12 | 2026-08-21 | Governance | Continuous Improvement Programme | needs-verification | ✓ |
| `docs/governance/COST-AND-REVENUE-GOVERNANCE.md` | 17.3 | 2315 | 9 | 2026-08-21 | Governance | Cost and Revenue Governance | needs-verification | ✓ |
| `docs/governance/DATA-TRANSFER-MATRIX.md` | 5.3 | 695 | 6 | 2026-08-21 | Governance | Data Transfer Matrix | needs-verification | ✓ |
| `docs/governance/DEBUGGING-MATRIX.md` | 5.5 | 770 | 8 | 2026-08-21 | Governance | Debugging Matrix | needs-verification | ✓ |
| `docs/governance/DUPLICATE-WORKER-FINDINGS.md` | 8.2 | 1100 | 6 | 2026-08-21 | Governance | Duplicate Worker Findings — 2026-08-07 systematic sweep | needs-verification | ✓ |
| `docs/governance/ENVIRONMENTAL-MATRIX.md` | 5.7 | 810 | 8 | 2026-08-21 | Governance | Environmental Matrix | needs-verification | ✓ |
| `docs/governance/ERROR-REMEDIATION-MATRIX.md` | 6.6 | 861 | 8 | 2026-08-21 | Governance | Error, Vulnerability, Remediation & Self-Healing Matrix | needs-verification |  |
| `docs/governance/ESTATE-PROTECTION-MATRICES.md` | 3.7 | 412 | 3 | 2026-08-21 | Governance | Estate Protection Matrices — Tranc3 Cross-Link | needs-verification | ✓ |
| `docs/governance/GPU-MATRIX.md` | 5.8 | 812 | 6 | 2026-08-21 | Governance | GPU Matrix | needs-verification | ✓ |
| `docs/governance/HARD-STOP-MATRIX.md` | 8.4 | 1180 | 9 | 2026-08-21 | Governance | Hard Stop Matrix | needs-verification | ✓ |
| `docs/governance/INTERNAL-AUDIT-PROGRAMME.md` | 3.0 | 475 | 12 | 2026-08-21 | Governance | Internal Audit Programme | needs-verification | ✓ |
| `docs/governance/LOCATION-FUNCTIONS.md` | 18.8 | 2919 | 8 | 2026-08-21 | Governance | Location Functions & Job Descriptions Registry | needs-verification |  |
| `docs/governance/LOCATION-TRAFFIC-MATRIX.md` | 5.0 | 694 | 6 | 2026-08-21 | Governance | Location-to-Location Traffic Matrix | needs-verification | ✓ |
| `docs/governance/MANAGEMENT-REVIEW-TEMPLATE.md` | 2.4 | 373 | 15 | 2026-08-21 | Governance | Management Review Template | needs-verification | ✓ |
| `docs/governance/MATRIX-INDEX.md` | 13.7 | 1685 | 6 | 2026-08-21 | Governance | Matrix Index | needs-verification |  |
| `docs/governance/MONOLITH-EXTRACTION-FINDINGS.md` | 39.2 | 5056 | 14 | 2026-08-21 | Governance | Monolith Extraction Findings — 2026-08-08 systematic sweep | needs-verification | ✓ |
| `docs/governance/NOTEBOOKS-JOURNALS-SCOPE.md` | 7.4 | 1093 | 10 | 2026-08-21 | Governance | Notebooks / Journals for AIs and Agents — Scoping Doc | needs-verification | ✓ |
| `docs/governance/OBSERVABILITY-AND-AUTOMATION-GOVERNANCE.md` | 14.2 | 1907 | 7 | 2026-08-21 | Governance | Observability and Automation Governance | needs-verification | ✓ |
| `docs/governance/OBSOLESCENCE-ACCEPTED.md` | 6.3 | 1050 | 8 | 2026-08-21 | Governance | Obsolescence — Accepted Components | needs-verification | ✓ |
| `docs/governance/PERMISSIONS-ACCESS-MATRIX.md` | 6.1 | 834 | 6 | 2026-08-21 | Governance | Permissions & Access Matrix | needs-verification |  |
| `docs/governance/PERSONALITY-ARCHETYPES.md` | 13.4 | 1693 | 7 | 2026-08-21 | Governance | Personality Archetypes — Research Basis for Job-Description Trait Vectors | needs-verification |  |
| `docs/governance/PRIVACY-MATRIX.md` | 4.4 | 625 | 6 | 2026-08-21 | Governance | Privacy Matrix | needs-verification |  |
| `docs/governance/PYTHON-3.14-UPGRADE-ASSESSMENT.md` | 29.8 | 3790 | 14 | 2026-08-21 | Governance | Python 3.11 → 3.14 Upgrade Feasibility Assessment | needs-verification | ✓ |
| `docs/governance/SECURITY-POSTURE-MATRIX.md` | 18.8 | 2582 | 8 | 2026-08-21 | Governance | Security Posture Matrix | needs-verification |  |
| `docs/governance/SWARM-COORDINATION-MATRIX.md` | 11.0 | 1448 | 7 | 2026-08-21 | Governance | Swarm Coordination Matrix | needs-verification |  |
| `docs/governance/THE-FOUNDATION.md` | 4.7 | 706 | 6 | 2026-08-21 | Governance | The Foundation — the parent entity above Trancendos | needs-verification | ✓ |
| `docs/governance/THRESHOLD-MATRIX.md` | 9.6 | 1240 | 11 | 2026-08-21 | Governance | Threshold Matrix | needs-verification | ✓ |
| `docs/governance/TOKEN-EFFICIENCY-MATRIX.md` | 3.7 | 475 | 6 | 2026-08-21 | Governance | Token Efficiency Matrix | needs-verification | ✓ |
| `docs/governance/TRANCENDOS-MODELS-MATRIX.md` | 23.4 | 3184 | 13 | 2026-08-21 | Governance | Trancendos Models Matrix | needs-verification | ✓ |
| `docs/governance/UX-UI-DESIGN-MATRIX.md` | 4.8 | 576 | 6 | 2026-08-21 | Governance | UX/UI Design Matrix | needs-verification | ✓ |
| `docs/policies/POL-AI-001-AI-Ethics-Governance.md` | 2.8 | 395 | 10 | 2026-08-21 | Policy | POL-AI-001 — AI Ethics & Governance Policy | needs-verification | ✓ |
| `docs/policies/POL-OPS-002-Change-Management.md` | 2.2 | 331 | 9 | 2026-08-21 | Policy | POL-OPS-002 — Change Management Policy | needs-verification | ✓ |
| `docs/policies/POL-PRI-001-Data-Protection-Privacy.md` | 3.8 | 584 | 11 | 2026-08-21 | Policy | POL-PRI-001 — Data Protection & Privacy Policy | needs-verification | ✓ |
| `docs/privacy/PRIVACY_IMPACT_ASSESSMENT.md` | 5.1 | 821 | 10 | 2026-08-21 | Privacy | Privacy Impact Assessment (PIA) | needs-verification | ✓ |
| `docs/privacy/ROPA.md` | 3.8 | 606 | 7 | 2026-08-21 | Privacy | Record of Processing Activities (ROPA) | needs-verification | ✓ |
| `docs/procedures/PROC-CHG-001-Change-Request.md` | 1.5 | 201 | 7 | 2026-08-21 | Procedure | PROC-CHG-001 — Change Request Procedure | needs-verification | ✓ |
| `docs/procedures/PROC-DSR-001-Data-Subject-Requests.md` | 2.4 | 396 | 9 | 2026-08-21 | Procedure | PROC-DSR-001 — Data Subject Request Handling Procedure | needs-verification | ✓ |
| `docs/procedures/PROC-TRN-001-Security-Awareness-Attestation.md` | 3.7 | 563 | 17 | 2026-08-21 | Procedure | PROC-TRN-001 — Security Awareness and Policy Attestation | needs-verification | ✓ |
| `docs/runbooks/README.md` | 1.6 | 232 | 3 | 2026-08-21 | Runbook | Operational Runbooks — Trancendos Platform | complete | ✓ |
| `docs/runbooks/api-backend.md` | 3.6 | 502 | 26 | 2026-08-21 | Runbook | Runbook: tranc3-backend (FastAPI API) | needs-verification |  |
| `docs/runbooks/disaster-recovery.md` | 9.3 | 1245 | 50 | 2026-08-21 | Runbook | Disaster Recovery Runbook — Trancendos Platform | needs-verification |  |
| `docs/runbooks/zero-downtime-deploy.md` | 3.3 | 473 | 21 | 2026-08-21 | Runbook | Runbook: Zero-Downtime Deployment Procedure | needs-verification |  |
| `docs/services/INDEX.md` | 56.2 | 7717 | 2 | 2026-08-21 | Service Doc | Service Doc-Pack Coverage Index | needs-verification | ✓ |
| `docs/services/api-marketplace/README.md` | 14.9 | 2143 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — API Marketplace | complete | ✓ |
| `docs/services/arcadia/README.md` | 9.0 | 1320 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — Arcadia (Post-Login Front-End Hub) | complete | ✓ |
| `docs/services/arcadian-exchange/README.md` | 6.6 | 968 | 9 | 2026-08-21 | Service Doc | Service Doc-Pack — Arcadian Exchange | complete | ✓ |
| `docs/services/chronosphere-arcstream/README.md` | 18.3 | 2614 | 15 | 2026-08-21 | Service Doc | Service Doc-Pack — ChronosSphere / ArcStream | complete | ✓ |
| `docs/services/cryptex/README.md` | 17.8 | 2455 | 19 | 2026-08-21 | Service Doc | Service Doc-Pack — Cryptex | complete | ✓ |
| `docs/services/devocity/README.md` | 19.4 | 2639 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — DevOcity | complete | ✓ |
| `docs/services/docutari/README.md` | 21.6 | 2968 | 17 | 2026-08-21 | Service Doc | Service Doc-Pack — DocUtari | complete | ✓ |
| `docs/services/fabulousa/README.md` | 16.1 | 2320 | 15 | 2026-08-21 | Service Doc | Service Doc-Pack — Fabulousa | complete | ✓ |
| `docs/services/i-mind/README.md` | 17.5 | 2385 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — I-Mind | complete | ✓ |
| `docs/services/imaginarium/README.md` | 17.3 | 2474 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — Imaginarium | complete | ✓ |
| `docs/services/infinity/README.md` | 15.1 | 2131 | 15 | 2026-08-21 | Service Doc | Service Doc-Pack — Infinity (OAuth2/OIDC + SSO + MFA Auth) | complete | ✓ |
| `docs/services/luminous/README.md` | 12.7 | 1735 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — Luminous (Core Platform Brain) | complete | ✓ |
| `docs/services/resonate/README.md` | 17.9 | 2554 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — Resonate | complete | ✓ |
| `docs/services/royal-bank-of-arcadia/README.md` | 7.7 | 1158 | 9 | 2026-08-21 | Service Doc | Service Doc-Pack — Royal Bank of Arcadia | complete | ✓ |
| `docs/services/sashas-photo-studio/README.md` | 16.8 | 2392 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — Sashas Photo Studio | complete | ✓ |
| `docs/services/taimra/README.md` | 16.8 | 2337 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — tAimra | complete | ✓ |
| `docs/services/tateking/README.md` | 16.4 | 2342 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — TateKing | complete | ✓ |
| `docs/services/the-academy/README.md` | 18.2 | 2599 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — The Academy | complete | ✓ |
| `docs/services/the-artifactory/README.md` | 26.5 | 3523 | 19 | 2026-08-21 | Service Doc | Service Doc-Pack — The Artifactory | complete | ✓ |
| `docs/services/the-basement/README.md` | 16.6 | 2298 | 20 | 2026-08-21 | Service Doc | Service Doc-Pack — The Basement | complete | ✓ |
| `docs/services/the-chaos-party/README.md` | 12.7 | 1854 | 15 | 2026-08-21 | Service Doc | Service Doc-Pack — The Chaos Party (Central Testing Platform) | complete | ✓ |
| `docs/services/the-citadel/README.md` | 15.3 | 2051 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — The Citadel (Strategic Ops & DevOps Fortress) | complete | ✓ |
| `docs/services/the-digital-grid/README.md` | 13.9 | 1923 | 15 | 2026-08-21 | Service Doc | Service Doc-Pack — The Digital Grid (Workflow DAG Engine) | complete | ✓ |
| `docs/services/the-dutchy/README.md` | 17.4 | 2383 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — The Dutchy | complete | ✓ |
| `docs/services/the-hive/README.md` | 6.7 | 981 | 9 | 2026-08-21 | Service Doc | Service Doc-Pack — The HIVE | complete | ✓ |
| `docs/services/the-ice-box/README.md` | 19.5 | 2680 | 15 | 2026-08-21 | Service Doc | Service Doc-Pack — The Ice Box | complete | ✓ |
| `docs/services/the-lab/README.md` | 17.6 | 2417 | 19 | 2026-08-21 | Service Doc | Service Doc-Pack — The Lab | complete | ✓ |
| `docs/services/the-library/README.md` | 19.5 | 2647 | 20 | 2026-08-21 | Service Doc | Service Doc-Pack — The Library | complete | ✓ |
| `docs/services/the-lighthouse/README.md` | 6.6 | 960 | 9 | 2026-08-21 | Service Doc | Service Doc-Pack — The Lighthouse | complete | ✓ |
| `docs/services/the-nexus/README.md` | 10.7 | 1491 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — The Nexus (WebSocket Communication Hub) | complete | ✓ |
| `docs/services/the-observatory/README.md` | 15.4 | 2115 | 15 | 2026-08-21 | Service Doc | Service Doc-Pack — The Observatory (Audit, Tracing, Health) | complete | ✓ |
| `docs/services/the-spark/README.md` | 17.6 | 2483 | 15 | 2026-08-21 | Service Doc | Service Doc-Pack — The Spark (MCP Server) | complete | ✓ |
| `docs/services/the-studio/README.md` | 15.4 | 2198 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — The Studio | complete | ✓ |
| `docs/services/the-town-hall/README.md` | 10.4 | 1448 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — The Town Hall (Governance Hub) | complete | ✓ |
| `docs/services/the-void/README.md` | 11.7 | 1676 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — The Void (Secrets & Password Vault) | complete | ✓ |
| `docs/services/the-warp-tunnel/README.md` | 20.0 | 2801 | 19 | 2026-08-21 | Service Doc | Service Doc-Pack — The Warp Tunnel | complete | ✓ |
| `docs/services/the-workshop/README.md` | 12.4 | 1691 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — The Workshop (CI/CD Hub) | complete | ✓ |
| `docs/services/think-tank/README.md` | 21.7 | 2972 | 19 | 2026-08-21 | Service Doc | Service Doc-Pack — Think Tank | complete | ✓ |
| `docs/services/tranceflow/README.md` | 14.5 | 1985 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — TranceFlow | complete | ✓ |
| `docs/services/tranquility/README.md` | 16.6 | 2284 | 19 | 2026-08-21 | Service Doc | Service Doc-Pack — Tranquility | complete | ✓ |
| `docs/services/turings-hub/README.md` | 10.3 | 1416 | 17 | 2026-08-21 | Service Doc | Service Doc-Pack — Turing's Hub (AI Personality Creation Centre) | complete | ✓ |
| `docs/services/vrar3d/README.md` | 16.2 | 2296 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — VRAR3D | complete | ✓ |
| `docs/services/warp-radio/README.md` | 19.3 | 2711 | 18 | 2026-08-21 | Service Doc | Service Doc-Pack — Warp Radio | complete | ✓ |
| `docs/solution-packs/README.md` | 5.2 | 994 | 5 | 2026-08-21 | Solution Pack | Solution Packs — index | complete | ✓ |
| `docs/solution-packs/api-marketplace.md` | 10.1 | 1363 | 18 | 2026-08-21 | Solution Pack | Solution Pack — API Marketplace | needs-verification |  |
| `docs/solution-packs/arcadia.md` | 9.9 | 1339 | 18 | 2026-08-21 | Solution Pack | Solution Pack — Arcadia | needs-verification |  |
| `docs/solution-packs/arcadian-exchange.md` | 10.8 | 1467 | 17 | 2026-08-21 | Solution Pack | Solution Pack — Arcadian Exchange | needs-verification |  |
| `docs/solution-packs/chronossphere-arcstream.md` | 10.3 | 1375 | 17 | 2026-08-21 | Solution Pack | Solution Pack — ChronosSphere / ArcStream | needs-verification |  |
| `docs/solution-packs/cryptex.md` | 10.8 | 1449 | 18 | 2026-08-21 | Solution Pack | Solution Pack — Cryptex | needs-verification |  |
| `docs/solution-packs/devocity.md` | 10.7 | 1410 | 18 | 2026-08-21 | Solution Pack | Solution Pack — DevOcity | needs-verification |  |
| `docs/solution-packs/docutari.md` | 10.1 | 1353 | 17 | 2026-08-21 | Solution Pack | Solution Pack — DocUtari | needs-verification |  |
| `docs/solution-packs/fabulousa.md` | 9.9 | 1347 | 18 | 2026-08-21 | Solution Pack | Solution Pack — Fabulousa | needs-verification |  |
| `docs/solution-packs/i-mind.md` | 10.6 | 1408 | 18 | 2026-08-21 | Solution Pack | Solution Pack — I-Mind | needs-verification |  |
| `docs/solution-packs/imaginarium.md` | 10.8 | 1437 | 18 | 2026-08-21 | Solution Pack | Solution Pack — Imaginarium | needs-verification |  |
| `docs/solution-packs/infinity.md` | 11.4 | 1529 | 17 | 2026-08-21 | Solution Pack | Solution Pack — Infinity | needs-verification |  |
| `docs/solution-packs/luminous.md` | 10.0 | 1324 | 16 | 2026-08-21 | Solution Pack | Solution Pack — Luminous | needs-verification |  |
| `docs/solution-packs/resonate.md` | 10.6 | 1401 | 18 | 2026-08-21 | Solution Pack | Solution Pack — Resonate | needs-verification |  |
| `docs/solution-packs/royal-bank-of-arcadia.md` | 10.4 | 1400 | 17 | 2026-08-21 | Solution Pack | Solution Pack — Royal Bank of Arcadia | needs-verification |  |
| `docs/solution-packs/sashas-photo-studio.md` | 10.8 | 1408 | 18 | 2026-08-21 | Solution Pack | Solution Pack — Sashas Photo Studio | needs-verification |  |
| `docs/solution-packs/section-7.md` | 10.8 | 1440 | 18 | 2026-08-21 | Solution Pack | Solution Pack — Section 7 | needs-verification |  |
| `docs/solution-packs/taimra.md` | 10.5 | 1427 | 18 | 2026-08-21 | Solution Pack | Solution Pack — tAimra | needs-verification |  |
| `docs/solution-packs/tateking.md` | 10.8 | 1458 | 18 | 2026-08-21 | Solution Pack | Solution Pack — TateKing | needs-verification |  |
| `docs/solution-packs/the-academy.md` | 10.8 | 1452 | 19 | 2026-08-21 | Solution Pack | Solution Pack — The Academy | needs-verification |  |
| `docs/solution-packs/the-artifactory.md` | 10.2 | 1373 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Artifactory | needs-verification |  |
| `docs/solution-packs/the-basement.md` | 10.6 | 1409 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Basement | needs-verification |  |
| `docs/solution-packs/the-chaos-party.md` | 10.3 | 1433 | 17 | 2026-08-21 | Solution Pack | Solution Pack — The Chaos Party | needs-verification |  |
| `docs/solution-packs/the-citadel.md` | 10.0 | 1359 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Citadel | needs-verification |  |
| `docs/solution-packs/the-digital-grid.md` | 10.5 | 1408 | 17 | 2026-08-21 | Solution Pack | Solution Pack — The Digital Grid | needs-verification |  |
| `docs/solution-packs/the-hive.md` | 10.3 | 1369 | 17 | 2026-08-21 | Solution Pack | Solution Pack — The HIVE | needs-verification |  |
| `docs/solution-packs/the-ice-box.md` | 10.3 | 1388 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Ice Box | needs-verification |  |
| `docs/solution-packs/the-lab.md` | 11.0 | 1504 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Lab | needs-verification |  |
| `docs/solution-packs/the-library.md` | 10.4 | 1403 | 17 | 2026-08-21 | Solution Pack | Solution Pack — The Library | needs-verification |  |
| `docs/solution-packs/the-lighthouse.md` | 10.3 | 1365 | 17 | 2026-08-21 | Solution Pack | Solution Pack — The Lighthouse | needs-verification |  |
| `docs/solution-packs/the-nexus.md` | 10.6 | 1427 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Nexus | needs-verification |  |
| `docs/solution-packs/the-observatory.md` | 10.6 | 1438 | 17 | 2026-08-21 | Solution Pack | Solution Pack — The Observatory | needs-verification |  |
| `docs/solution-packs/the-spark.md` | 9.9 | 1363 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Spark | needs-verification |  |
| `docs/solution-packs/the-studio.md` | 10.5 | 1405 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Studio | needs-verification |  |
| `docs/solution-packs/the-town-hall.md` | 9.9 | 1346 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Town Hall | needs-verification |  |
| `docs/solution-packs/the-void.md` | 11.1 | 1486 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Void | needs-verification |  |
| `docs/solution-packs/the-warp-tunnel.md` | 10.2 | 1387 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Warp Tunnel | needs-verification |  |
| `docs/solution-packs/the-workshop.md` | 10.5 | 1388 | 18 | 2026-08-21 | Solution Pack | Solution Pack — The Workshop | needs-verification |  |
| `docs/solution-packs/think-tank.md` | 10.2 | 1381 | 18 | 2026-08-21 | Solution Pack | Solution Pack — Think Tank | needs-verification |  |
| `docs/solution-packs/tranceflow.md` | 10.6 | 1413 | 18 | 2026-08-21 | Solution Pack | Solution Pack — TranceFlow | needs-verification |  |
| `docs/solution-packs/tranquility.md` | 10.8 | 1428 | 18 | 2026-08-21 | Solution Pack | Solution Pack — Tranquility | needs-verification |  |
| `docs/solution-packs/turing-s-hub.md` | 10.2 | 1403 | 18 | 2026-08-21 | Solution Pack | Solution Pack — Turing's Hub | needs-verification |  |
| `docs/solution-packs/vrar3d.md` | 10.7 | 1426 | 18 | 2026-08-21 | Solution Pack | Solution Pack — VRAR3D | needs-verification |  |
| `docs/solution-packs/warp-radio.md` | 10.6 | 1420 | 18 | 2026-08-21 | Solution Pack | Solution Pack — Warp Radio | needs-verification |  |
| `docs/templates/INDEX.md` | 2.2 | 276 | 7 | 2026-08-21 | Template | Template Library Index | needs-verification | ✓ |
| `docs/vault_security.md` | 11.2 | 1345 | 46 | 2026-08-21 | Docs Root | Vault Security Implementation — Tranc3 Ecosystem | needs-verification |  |
| `requirements-ai.txt` | 1.2 | 138 | 20 | 2026-08-21 | Repo Root | TRANC3 — Extended AI/ML Dependencies (Optional) | needs-verification | ✓ |
| `requirements-security.txt` | 3.0 | 401 | 34 | 2026-08-21 | Repo Root | TRANC3 — Security Scanning Toolchain (dev-only) | needs-verification | ✓ |
| `requirements-test.txt` | 0.8 | 73 | 9 | 2026-08-21 | Repo Root | TRANC3 — Test-only dependencies | needs-verification | ✓ |
| `requirements.txt` | 9.6 | 1192 | 122 | 2026-08-21 | Repo Root | TRANC3 — Python Dependencies | needs-verification | ✓ |
| `ruff_check_out.txt` | 1.9 | 192 | 0 | 2026-08-21 | Repo Root | ruff_check_out.txt | needs-verification | ✓ |


## 3. Key Findings

### 3.1 Broken / dead links from `README.md`
The repo-root `README.md` links to files that do not resolve:

| README link | Status | Note |
|---|---|---|
| `CF_WORKER_MIGRATION_ROADMAP.md` | ❌ Missing at root | Moved to `wiki-content/Architecture-CF_WORKER_MIGRATION_ROADMAP.md` (CLAUDE.md references the new location). README link is stale. |
| `PROJECT_PULSE.md` | ❌ Missing entirely | No such file anywhere in the repo. Dead link. |
| `SECURITY-ASSESSMENT.md` | ❌ Broken relative path | The file exists at `docs/SECURITY-ASSESSMENT.md` but README links to a repo-root path, so the link is broken. |
| `docs/DEPLOYMENT_RUNBOOK.md` | ✅ Valid | Exists. |
| `ARCHITECTURE_THREAT_MODEL.md` | ✅ Valid | Exists. |
| `SECURITY.md` | ✅ Valid | Exists. |

### 3.2 Documentation referencing non-existent code paths
Sampled the highest-risk, most code-referential documents (CLAUDE.md, `docs/API_REFERENCE.md`, `docs/DEPLOYMENT_GUIDE.md`, `docs/architecture/*.md`) and verified every referenced `src/...` path against the actual tree:

- **`docs/API_REFERENCE.md`** — Declares two FastAPI apps: `api.py` (**exists**) and `api_enhanced.py` (**MISSING**). The "Enhanced API" section documents endpoints that have no corresponding entrypoint in the repo. Marked **outdated**.
- **`src/resilience/primitives.py`** — Referenced by architecture docs but **missing** (sibling `src/resilience/circuit_core.py` / `circuit_state.py` / `circuit_breaker.py` do exist). Minor dangling reference.
- **CLAUDE.md** — All sampled module paths (`api.py`, `src/mcp`, `src/workflow`, `src/nanoservices`, `src/core`, `src/entities/platform.py`, `src/roles/registry.py`, `docker-compose.production.yml`, `PLATFORM_ENTITIES.md`) **exist**. CLAUDE.md path references are accurate.
- **68 distinct `src/...` references** across the high-risk docs; only 1 was genuinely missing (`src/resilience/primitives.py`). The architecture docs are largely accurate against the codebase.

> Note: This is a sampled verification of the highest-risk files (per the bead's named list). A full per-file code-path cross-check of all 215 documents was not performed; lower-risk narrative docs were marked `needs-verification`.

### 3.3 Orphaned documentation (no inbound links)
**151 of 215** documentation files are never linked from any other documentation file (full intra-doc link-graph analysis). Notable orphan clusters:
- **`docs/services/` (44 files)** and **`docs/solution-packs/` (44 files)** — Almost entirely orphaned; only `docs/services/INDEX.md` and `docs/solution-packs/README.md` act as local hubs. Most individual service/solution docs are unreachable by navigation.
- **`docs/governance/` (39 files)** — Largely orphaned outside the governance subsystem.
- All repo-root files except those linked from README (see 3.1) are orphaned from the `docs/` tree.

### 3.4 Outdated / needs-verification
| File | Flag | Reason |
|---|---|---|
| `docs/API_REFERENCE.md` | **Outdated** | References non-existent `api_enhanced.py`; version pinned at `0.1.0`. |
| `docs/WINDOWS_DEPLOY.md` | Needs-verification | Windows-specific deploy path; likely drifted from the Linux/self-hosted (Fortiere) posture in CLAUDE.md. |
| `docs/DEPLOYMENT_RUNBOOK.md`, `docs/DEPLOYMENT_GUIDE.md` | Needs-verification | Infrastructure/migration content; cross-check against `docker-compose.production.yml`. |
| All `docs/architecture/*.md` | Mostly accurate | Verified code paths exist; confirm service/port tables against `docker-compose.production.yml` (per downstream topology-map task). |

### 3.5 Recommendations (hand-off to downstream convoy tasks)
1. **Fix README dead links** (3.1) — point `CF_WORKER_MIGRATION_ROADMAP.md` → `wiki-content/...`, `SECURITY-ASSESSMENT.md` → `docs/SECURITY-ASSESSMENT.md`, and either create or remove `PROJECT_PULSE.md`.
2. **Create `docs/DOC_INDEX.md`** as the canonical navigation hub (downstream task: documentation structure) to resolve the 151 orphaned docs.
3. **Rewrite `docs/API_REFERENCE.md`** to reflect the real entrypoint (`api.py`) or restore `api_enhanced.py` (downstream task: fix misalignments).
4. **Wire service/solution-pack docs into the index** so the 88 service + solution-pack files are navigable.
