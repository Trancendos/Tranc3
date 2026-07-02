# Trancendos / Tranc3 — Wiki Home

Welcome to the Trancendos platform wiki. This is the living knowledge base for the Tranc3 project — architecture decisions, service runbooks, governance, strategic analysis, and historical phase reports.

> **Code-adjacent docs** (API reference, design system, deployment scripts, compliance controls) live in the **[repo](https://github.com/Trancendos/Tranc3)** under `docs/`. Everything conceptual or historical lives here.

---

## Quick Navigation

### Platform & Architecture
- [[Platform-Entities]] — All 43 named services, Lead AIs, ports, and status
- [[Architecture-Overview]] — Self-hosted zero-cost stack, service mesh, inference pipeline
- [[Deployment-Topology]] — Traefik, Docker Compose, Fly.io, Cloudflare Workers map
- [[CF-Worker-Migration-Roadmap]] — 26+ workers migrating from CF to Python/FastAPI
- [[Cross-Repo-Synergy]] — 29 infinity-adminOS packages mapped to Python equivalents
- [[Infinity-Architecture]] — Infinity auth/SSO/identity architecture detail
- [[Infinity-Ecosystem-Matrix]] — Full ecosystem service matrix
- [[Tier-Architecture]] — Service tier breakdown (P0–P3)
- [[Framework]] — Foundational framework decisions

### Development Guides
- [[Getting-Started]] — Clone, env setup, first commit
- [[Branch-and-PR-Workflow]] — Branch naming, CI gates, merge strategy
- [[Worker-Development-Guide]] — How to add a new self-hosted Python worker
- [[Integration-Scope-Plan]] — Service integration scope and priorities

### Service Runbooks (extended)
- [[The-Spark-MCP]] — JSON-RPC 2.0, tool registry, SSE bus
- [[The-Digital-Grid]] — DAG builder, workflow executor, event bus
- [[Infinity-Auth]] — OAuth2, SSO, MFA setup and troubleshooting
- [[The-Town-Hall]] — CranBania: Kanban, ITSM, PRINCE2, Agile tools
- [[Vault-The-Void]] — AES-GCM secrets, Shamir unseal procedure

### Strategy & Research
- [[Zero-Cost-Strategy]] — Why self-hosted over paid cloud tiers
- [[Zero-Cost-Cloud-Providers]] — Provider comparison and free tier limits
- [[Zero-Cost-Vendor-Matrix]] — Vendor evaluation matrix
- [[Free-Tier-Registry]] — Registry of all free-tier services in use
- [[Adaptive-Platform-Rotation]] — Platform rotation strategy
- [[Research-Advancement-2026]] — R&D advancement findings 2026
- [[Master-Worker-Zero-Cost]] — Zero-cost worker implementation master plan
- [[Knowledge-Base]] — Platform knowledge base overview

### Governance & Compliance
- [[Magna-Carta-Rules]] — 9 runtime compliance rules, enforcement points
- [[Change-Management]] — CAB workflow, PROC-CHG-001
- [[Data-Protection]] — GDPR/ROPA, PROC-DSR-001, Privacy Impact Assessment
- [[Security-Policies]] — POL-AI-001, POL-OPS-002, POL-PRI-001
- [[AI-Governance]] — EU AI Act classification, bias controls, explainability

### Security Tracking
- [[Security-Alert-Register]] — Platform security alert register
- [[Security-Alert-Dismissals]] — Dismissed/accepted risk register
- [[CVE-Remediation-Report]] — CVE remediation history

### Project Documents (DOC series)
- [[DOC-01-Project-Charter]] — Project charter and scope
- [[DOC-02-System-Architecture]] — System architecture document
- [[DOC-03-API-Reference]] — Initial API reference
- [[DOC-13-Strategic-Analysis]] — Strategic analysis
- [[DOC-14-Zero-Cost-Hosting]] — Zero-cost hosting analysis
- [[DOC-15-Mind-Map]] — Platform mind map
- [[DOC-16-Lotus-Diagram]] — Lotus diagram
- [[DOC-17-SCAMPER-5Whys]] — SCAMPER & 5 Whys analysis
- [[DOC-18-Brainstorming]] — Brainstorming sessions

### Historical Phase Reports
- [[Phase-2-P2-Rollout]] — Phase 2 P2 service rollout
- [[Phase-7-Architecture]] — Phase 7 architecture
- [[Phase-7-Deployment]] — Phase 7 deployment
- [[Phase-8-11-Architecture]] — Phases 8–11 architecture evolution
- [[Phase-20-SWOT-Forensic]] — Phase 20 SWOT & forensic report
- [[Phase-21-SWOT-Forensic]] — Phase 21 SWOT & forensic report
- [[Phase-22-Enhancement]] — Phase 22 enhancement report
- [[Phase-23-Enhancement]] — Phase 23 enhancement report
- [[Phase-23-Forensic-Report]] — Phase 23 forensic report
- [[Phase-24-SWOT-Forensic]] — Phase 24 SWOT & forensic report
- [[Phase-25-Progress-Calculation]] — Phase 25 progress calculation
- [[Phase-25-Repo-Review]] — Phase 25 repository review
- [[Phase-25-UX-Enhancement]] — Phase 25 UX/UI enhancement
- [[Phase-25-Zero-Cost-Assessment]] — Phase 25 zero-cost assessment
- [[Phase-26-Directory-Structure]] — Phase 26 directory structure
- [[Phase-27-Dimensional-Nexus]] — Phase 27 Dimensional Nexus
- [[Phase-28-Advanced-Bridge-Systems]] — Phase 28 advanced bridge systems
- [[Forensic-Report-2026-05-28]] — Forensic report 2026-05-28
- [[Forensic-Assessment-2026-05-31]] — Forensic assessment 2026-05-31
- [[SWOT-Analysis]] — Platform SWOT analysis
- [[Branch-Consolidation]] — Branch consolidation history
- [[Branch-Integration-Report]] — Branch integration report
- [[Production-Forensic-Assessment]] — Production forensic assessment

### Operational History
- [[Project-Pulse]] — Project health pulse snapshots
- [[Revert-Log]] — Revert history and rollback log
- [[Verification]] — Verification reports

### Todo & Backlog
- [[Todo-Platform]] — Platform-level todo items
- [[Todo-Infrastructure]] — Infrastructure todo items
- [[Todo-TypeScript]] — TypeScript sub-project todos

---

*This wiki is the source of truth for conceptual and historical documentation. For code-level docs, see the [repo](https://github.com/Trancendos/Tranc3/tree/main/docs).*
