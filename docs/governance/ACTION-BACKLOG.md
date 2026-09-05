# Action Backlog — every outstanding item the estate records

**Generated** by `scripts/build_action_backlog.py` from 51 registers across the documentation estate. Do not edit by hand — a hand-kept backlog becomes one more register nobody sweeps.

The estate records outstanding work in dozens of separate registers, each correct about its own domain and blind to the rest. Nobody can answer *what is outstanding across the platform* without reading 320 documents, so nobody asks — and an action in a register nobody sweeps is an action nobody does. This is that sweep.

**201 open items** across **10 epics**.

**31 of 201 are routed to a Location** and link to that Location's solution pack — its architecture, compose-derived routing, user journey and acceptance criteria. The other 170 name no Location, so they have no design material and no one accountable; routing them is the first story in each case, which is what the +1 in their sizing says. That ratio is the single most useful number in this document.

**0 of those 31 carry a Town Hall routing decision** (`/townhall/routing`, exported to `config/estate/backlog_routing.yaml`): a named authority, a written reason, the Location's design pack and an Observatory event. The rest are routed only because a register row happens to mention a Location by name, which is a hint its author left rather than a decision anybody made or can appeal.

The remaining **170 are a queue the Town Hall owes an answer to**, not a number to be made to go away. Assigning them here by judgement would write a decision nobody made into a generated file that reads as derived fact — the same move that made a routing defect read as deliberate design in twenty solution packs.

## Definition of Ready

An item is ready to start when all of these hold. They are properties of this
estate's own gates (`src/townhall/plm.py`), not per-item prose.

| # | Condition | Why it is here |
|---|---|---|
| 1 | The owning Location is named, and its code path exists | An item routed nowhere is an item nobody is accountable for — the defect the CMDB alignment check now prevents |
| 2 | The register row it came from is still open | Registers are swept by regenerating this file; an item closed at source disappears from it |
| 3 | Acceptance is stated as something observable | "Improve X" cannot be gated; "`GET /x` answers 200 in the deployed image" can |
| 4 | Any dependency is itself Ready or Done | PLM refuses a gate whose evidence depends on unfinished work |

## Definition of Done

| # | Condition | Enforced by |
|---|---|---|
| 1 | The change is in the deployed entrypoint, not only in the repository | `scripts/check_creative_routes.py` — several workers ship two apps and only the Dockerfile `CMD` decides which runs |
| 2 | A test exists that fails when the change is reverted | Mutation, by hand: inject the fault, watch the named test fail, restore |
| 3 | Any control added is invoked by something | `scripts/check_guards_are_wired.py` — a control nobody runs reports PASSED and gates nothing |
| 4 | The source register row is closed, and this file regenerated | Otherwise the backlog and the register disagree, which is the condition this file exists to end |
| 5 | A PLM gate decision is recorded | `/townhall/plm` — the Town Hall, not the building Location, decides the gate opened |

## Sizing

Story points are derived from facts about the item, never estimated. Each
item's reasons are printed beside it, so a number can be argued with.

| Contribution | Points |
|---|---|
| Baseline — every item costs something | +1 |
| No Location named; routing has to happen first | +1 |
| Owning Location has no code path on disk | +1 |
| Status is blocked, funding-gated, or needs an owner | +2 |
| Evidence or attestation register rather than a code change | +2 |

Totals are rounded down to the nearest Fibonacci value, so a 13 means
something genuinely unusual rather than a rounding artefact.

## Epic — ISO 27001 controls

Statement-of-applicability controls not yet evidenced.

**38 stories · 114 points**

| Story | Location | Design | Status | Pts | Sized because | Source |
|---|---|---|---|---|---|---|
| Information security roles and responsibilities | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:24` |
| Segregation of duties | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:25` |
| Contact with authorities | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:27` |
| Contact with special interest groups | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:28` |
| Threat intelligence | Cryptex | [pack](../solution-packs/cryptex.md) | Partial | 3 | baseline (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:29` |
| Inventory of information and other assets | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:31` |
| Acceptable use of information and assets | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:32` |
| Classification of information | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:34` |
| Labelling of information | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:35` |
| Information security in supplier relationships | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:41` |
| Addressing information security within supplier agreements | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:42` |
| Managing information security in the ICT supply chain | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:43` |
| Monitoring, review, and change management of supplier services | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:44` |
| Information security incident management planning | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:46` |
| Assessment and decision on information security events | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:47` |
| Response to information security incidents | The Ice Box | [pack](../solution-packs/the-ice-box.md) | Planned | 3 | baseline (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:48` |
| Learning from information security incidents | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:49` |
| Information security during disruption | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:51` |
| ICT readiness for business continuity | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:52` |
| Legal, statutory, regulatory, and contractual requirements | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:53` |
| Independent review of information security | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:57` |
| Compliance with policies, rules, and standards | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:58` |
| Documented operating procedures | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:59` |
| Background check process for contributors planned | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:67` |
| Terms and conditions of employment | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:68` |
| Information security awareness, education, and training | The Academy | [pack](../solution-packs/the-academy.md) | Planned | 3 | baseline (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:69` |
| Disciplinary process | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:70` |
| Responsibilities after termination | Infinity | [pack](../solution-packs/infinity.md) | Planned | 3 | baseline (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:71` |
| Confidentiality or non-disclosure agreements | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:72` |
| User endpoint devices | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:106` |
| Capacity management | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:111` |
| Protection against malware | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:112` |
| Data masking | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:116` |
| Data leakage prevention | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:117` |
| Information backup | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:118` |
| Redundancy of information processing facilities | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:119` |
| Use of privileged utility programs | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:123` |
| Web filtering | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/ISO27001_SOA.md:128` |

## Epic — DefStan alignment

UK Defence Standard clauses awaiting evidence or exemption.

**12 stories · 36 points**

| Story | Location | Design | Status | Pts | Sized because | Source |
|---|---|---|---|---|---|---|
| Vault encrypted; SQLite workers not encrypted at rest | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:39` |
| SPF (-all) + DMARC (p=none) published; no DKIM/real relay yet | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:40` |
| Bootstrap mode stub; full moderation pipeline planned | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:50` |
| ServiceMesh timeouts; global policy not standardised | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:52` |
| The Ice Box / Warp Tunnel planned (WAV-001) | The Ice Box | [pack](../solution-packs/the-ice-box.md) | PLANNED | 3 | baseline (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:53` |
| Benchmarks exist; CI regression gate planned | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:67` |
| PR workflow enforced; formal CAB process planned | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:80` |
| CLAUDE.md engineering ref; dedicated runbooks planned | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:92` |
| Backup procedures and DR testing planned (WAV-002) | _unrouted_ | — | PLANNED | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:93` |
| Fly.io rolling deploys; self-hosted rolling strategy partial | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:94` |
| MCP versioning complete; REST API versioning partial | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:103` |
| Threat model has data flow; full ROPA planned | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/defstan/COMPLIANCE_REGISTER.md:121` |

## Epic — SOC 2 evidence

Trust-services criteria awaiting an evidence artefact.

**6 stories · 18 points**

| Story | Location | Design | Status | Pts | Sized because | Source |
|---|---|---|---|---|---|---|
| docs/governance/MANAGEMENT-REVIEW-TEMPLATE.md | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/SOC2-EVIDENCE-SCHEDULE.md:13` |
| Org chart, role definitions | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/SOC2-EVIDENCE-SCHEDULE.md:14` |
| PROC-TRN-001 attestation register | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/SOC2-EVIDENCE-SCHEDULE.md:15` |
| CC1.5 Accountability | _unrouted_ | — | Not started | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/SOC2-EVIDENCE-SCHEDULE.md:16` |
| CC2.2 Internal communication | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/SOC2-EVIDENCE-SCHEDULE.md:23` |
| CC7.3 Incident response | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/SOC2-EVIDENCE-SCHEDULE.md:67` |

## Epic — Regulatory alignment

FCA, AI governance and other regulatory registers.

**24 stories · 72 points**

| Story | Location | Design | Status | Pts | Sized because | Source |
|---|---|---|---|---|---|---|
| Art. 9, 13, 15, 50 addressed; Art. 16/17 pending | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/AI_GOVERNANCE.md:14` |
| §6, 8, 9 in place; certification audit not yet scheduled | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/AI_GOVERNANCE.md:15` |
| GOVERN/MAP/MEASURE active; MANAGE partial | _unrouted_ | — | Partial | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/AI_GOVERNANCE.md:16` |
| AI transparency headers (X-AI-Generated) not yet implemented | _unrouted_ | — | In Progress | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md:10` |
| GDPR DSR automated workflow not yet deployed | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md:11` |
| Secret management: remaining workers not using vault-service | _unrouted_ | — | In Progress | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md:12` |
| HIPAA BAA programme — activate when HIPAA_PROFILE enabled | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md:13` |
| External penetration test (annual) | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md:14` |
| Staff policy attestation (PROC-TRN-001) | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md:15` |
| SOC 2 Type II readiness assessment | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md:16` |
| FCA Consumer Duty gap analysis | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md:17` |
| MAGNA_CARTA_ENABLED staging enablement | _unrouted_ | — | In Progress | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md:18` |
| Bias measurement first run (PROC-AI-002) | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md:19` |
| Internal audit programme — first audit | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md:20` |
| Consumer Duty outcomes | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/FCA-ALIGNMENT.md:140` |
| Supplier resilience | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/FCA-ALIGNMENT.md:143` |
| Legal review of PHI data flows | _unrouted_ | — | Open | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/HIPAA-ALIGNMENT.md:81` |
| BAA executed with all relevant providers | _unrouted_ | — | Open | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/HIPAA-ALIGNMENT.md:82` |
| PHI-specific access controls tested | _unrouted_ | — | Open | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/HIPAA-ALIGNMENT.md:83` |
| Staff trained on HIPAA obligations | _unrouted_ | — | Open | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/HIPAA-ALIGNMENT.md:84` |
| Breach notification procedure documented (72-hour notice requirement) | _unrouted_ | — | Open | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/HIPAA-ALIGNMENT.md:85` |
| Annual HIPAA risk assessment scheduled | _unrouted_ | — | Open | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/HIPAA-ALIGNMENT.md:86` |
| Incident response plan updated for PHI breach scenarios | _unrouted_ | — | Open | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/HIPAA-ALIGNMENT.md:87` |
| Partially implemented | _unrouted_ | — | PARTIAL | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/compliance/TRANC3-REGISTER-BRIDGE.md:83` |

## Epic — Assurance programmes

Penetration testing and independent assurance.

**4 stories · 12 points**

| Story | Location | Design | Status | Pts | Sized because | Source |
|---|---|---|---|---|---|---|
| Auth flows + API surface | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/evidence/PEN-TEST-PROGRAMME.md:32` |
| External professional | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/evidence/PEN-TEST-PROGRAMME.md:33` |
| Internal red team | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/evidence/PEN-TEST-PROGRAMME.md:34` |
| External professional | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/evidence/PEN-TEST-PROGRAMME.md:35` |

## Epic — Internal audit

Audit programme findings and follow-ups.

**5 stories · 15 points**

| Story | Location | Design | Status | Pts | Sized because | Source |
|---|---|---|---|---|---|---|
| Access Control & Authentication (CC6, IA) | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/governance/INTERNAL-AUDIT-PROGRAMME.md:14` |
| Change Management & CAB Gate (CC8, MC-003) | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/governance/INTERNAL-AUDIT-PROGRAMME.md:15` |
| Privacy & Data Rights (GDPR, MC-001) | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/governance/INTERNAL-AUDIT-PROGRAMME.md:16` |
| AI Governance (EU AI Act, MC-005) | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/governance/INTERNAL-AUDIT-PROGRAMME.md:17` |
| Full ISMS scope audit | _unrouted_ | — | Planned | 3 | baseline (+1); no Location named — routing first (+1); evidence/attestation register, not a code change (+2) | `docs/governance/INTERNAL-AUDIT-PROGRAMME.md:18` |

## Epic — Creative delivery

The creative routing and PLM remediation register.

**8 stories · 15 points**

| Story | Location | Design | Status | Pts | Sized because | Source |
|---|---|---|---|---|---|---|
| Issue `PENPOT_TOKEN` into The Void | Fabulousa | [pack](../solution-packs/fabulousa.md) | Needs owner | 3 | baseline (+1); status `Needs owner` — impeded, not merely unstarted (+2) | `docs/architecture/FORENSIC-ASSESSMENT-CREATIVE-DELIVERY.md:201` |
| Fabulousa serves `tokens.ts`, components and widgets | Fabulousa | [pack](../solution-packs/fabulousa.md) | Open | 1 | baseline (+1) | `docs/architecture/FORENSIC-ASSESSMENT-CREATIVE-DELIVERY.md:202` |
| Accessibility validator + axe/pa11y in CI | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `docs/architecture/FORENSIC-ASSESSMENT-CREATIVE-DELIVERY.md:203` |
| Chaos Party and Cryptex file PLM evidence automatically | Cryptex | [pack](../solution-packs/cryptex.md) | Open | 1 | baseline (+1) | `docs/architecture/FORENSIC-ASSESSMENT-CREATIVE-DELIVERY.md:204` |
| Run the entrypoint audit across all ~80 workers | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `docs/architecture/FORENSIC-ASSESSMENT-CREATIVE-DELIVERY.md:205` |
| Lab verification sidecar (node/go/rustc/javac) | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `docs/architecture/FORENSIC-ASSESSMENT-CREATIVE-DELIVERY.md:206` |
| Deploy TranceFlow / TateKing / Warp Radio `worker.py | TranceFlow | [pack](../solution-packs/tranceflow.md) | Open | 1 | baseline (+1) | `docs/architecture/FORENSIC-ASSESSMENT-CREATIVE-DELIVERY.md:207` |
| Godot, ffmpeg, ComfyUI as services | _unrouted_ | — | Funding-gated | 3 | baseline (+1); no Location named — routing first (+1); status `Funding-gated` — impeded, not merely unstarted (+2) | `docs/architecture/FORENSIC-ASSESSMENT-CREATIVE-DELIVERY.md:208` |

## Epic — Location flow wiring

Declared Location-to-Location flows that nothing routes to.

**4 stories · 4 points**

| Story | Location | Design | Status | Pts | Sized because | Source |
|---|---|---|---|---|---|---|
| Workflow and pipeline execution routes through The Digital Grid | The Digital Grid | [pack](../solution-packs/the-digital-grid.md) | partial | 1 | baseline (+1) | `docs/governance/LOCATION-FLOW-CONTRACT.md:91` |
| The Workshop holds repositories and mirrors to GitHub, GitLab and Bitbucket | The Workshop | [pack](../solution-packs/the-workshop.md) | partial | 1 | baseline (+1) | `docs/governance/LOCATION-FLOW-CONTRACT.md:93` |
| All financial regulation routes through Royal Bank of Arcadia | Arcadia | [pack](../solution-packs/arcadia.md) | partial | 1 | baseline (+1) | `docs/governance/LOCATION-FLOW-CONTRACT.md:94` |
| All testing routes through The Chaos Party | The Chaos Party | [pack](../solution-packs/the-chaos-party.md) | partial | 1 | baseline (+1) | `docs/governance/LOCATION-FLOW-CONTRACT.md:103` |

## Epic — Historical findings

Items carried from earlier assessments — verify before working.

**17 stories · 30 points**

| Story | Location | Design | Status | Pts | Sized because | Source |
|---|---|---|---|---|---|---|
| Designate api.py as canonical entry point | _unrouted_ | — | Pending | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:261` |
| Fix test_event_bus_subscribe_publish failure | _unrouted_ | — | Pending | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:262` |
| Document all 46 workers in CLAUDE.md | _unrouted_ | — | Pending | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:273` |
| Rust crypto layer for The Void (PyO3 FFI) | The Void | [pack](../solution-packs/the-void.md) | Planned | 1 | baseline (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:280` |
| Rewrite monitoring/health-aggregator in Go | _unrouted_ | — | Planned | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:281` |
| api.py refactor (split 64KB file into domain modules) | _unrouted_ | — | Pending | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:283` |
| The Lab service foundation | The Lab | [pack](../solution-packs/the-lab.md) | Planned | 1 | baseline (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:284` |
| Go rewrite: queue-service, rate-limit-service | _unrouted_ | — | Planned | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:290` |
| Full Section 7 with automated scheduling | Section 7 | [pack](../solution-packs/section-7.md) | Planned | 1 | baseline (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:291` |
| Rust rewrite: nanoservices hot paths | _unrouted_ | — | Planned | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:292` |
| Imaginarium service foundation | Imaginarium | [pack](../solution-packs/imaginarium.md) | Planned | 1 | baseline (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:293` |
| Town Hall governance service | _unrouted_ | — | Planned | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-FORENSIC_REPORT_2026_05_28.md:294` |
| Git Repository | _unrouted_ | — | Pending | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-PHASE20_SWOT_FORENSIC.md:125` |
| Extended tasks (this phase) | _unrouted_ | — | In progress | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-PHASE25_PROGRESS_CALCULATION.md:26` |
| Finalization | _unrouted_ | — | Planned | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-PHASE25_PROGRESS_CALCULATION.md:27` |
| Current Phase | _unrouted_ | — | In progress | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-PHASE26_DIRECTORY_STRUCTURE.md:545` |
| Phase 3 — CF cutover | _unrouted_ | — | Not started | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Historical-PRODUCTION_FORENSIC_ASSESSMENT.md:101` |

## Epic — Platform engineering

Everything else the estate has recorded as outstanding.

**83 stories · 153 points**

| Story | Location | Design | Status | Pts | Sized because | Source |
|---|---|---|---|---|---|---|
| tranc3-ts/src/hubs/townhall/ | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/THE_TOWN_HALL.md:17` |
| Persistent DB / Forgejo PR gates | _unrouted_ | — | Planned | 2 | baseline (+1); no Location named — routing first (+1) | `docs/THE_TOWN_HALL.md:18` |
| Live pack, scoped to what exists; gaps flagged | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md:119` |
| GOV + RACI + TFM + DSM + ESM + POL + STD only | _unrouted_ | — | Planned | 2 | baseline (+1); no Location named — routing first (+1) | `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md:120` |
| severely strained standing — but always redeemable | _unrouted_ | — | blocked | 3 | baseline (+1); no Location named — routing first (+1); status `blocked` — impeded, not merely unstarted (+2) | `docs/governance/AI-RELATIONSHIP-MATRIX.md:90` |
| the `api` service in `docker-compose.development.yml` runs the same `tranc3-backend` monolith, so this enti… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/api-marketplace/README.md:142` |
| same monolith router via the `api` service in `docker-compose.uat.yml | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/api-marketplace/README.md:143` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `cron-servi… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/chronosphere-arcstream/README.md:183` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `cron-service` worker is **not*… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/chronosphere-arcstream/README.md:184` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `cryptex` w… | Cryptex | [pack](../solution-packs/cryptex.md) | Partial | 1 | baseline (+1) | `docs/services/cryptex/README.md:167` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `cryptex` worker is **not** in … | Cryptex | [pack](../solution-packs/cryptex.md) | Partial | 1 | baseline (+1) | `docs/services/cryptex/README.md:168` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `devocity` … | DevOcity | [pack](../solution-packs/devocity.md) | Partial | 1 | baseline (+1) | `docs/services/devocity/README.md:154` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `devocity` worker is **not** in… | DevOcity | [pack](../solution-packs/devocity.md) | Partial | 1 | baseline (+1) | `docs/services/devocity/README.md:155` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `imind` wor… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/i-mind/README.md:149` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `imind` worker is **not** in th… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/i-mind/README.md:150` |
| the `api` service in `docker-compose.development.yml` runs the same `tranc3-backend` monolith, so this enti… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/luminous/README.md:119` |
| same monolith router via the `api` service in `docker-compose.uat.yml | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/luminous/README.md:120` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `resonate` … | Resonate | [pack](../solution-packs/resonate.md) | Partial | 1 | baseline (+1) | `docs/services/resonate/README.md:142` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `resonate` worker is **not** in… | Resonate | [pack](../solution-packs/resonate.md) | Partial | 1 | baseline (+1) | `docs/services/resonate/README.md:143` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `taimra` wo… | tAimra | [pack](../solution-packs/taimra.md) | Partial | 1 | baseline (+1) | `docs/services/taimra/README.md:144` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `taimra` worker is **not** in t… | tAimra | [pack](../solution-packs/taimra.md) | Partial | 1 | baseline (+1) | `docs/services/taimra/README.md:145` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `artifactor… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-artifactory/README.md:185` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `artifactory-service` worker is… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-artifactory/README.md:186` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `basement` … | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-basement/README.md:147` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `basement` worker is **not** in… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-basement/README.md:148` |
| Traefik, Alertmanager, OTel Collector, Loki+Promtail, and IPFS are **not** present in UAT — only 3 of the 8… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-citadel/README.md:159` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `the-grid` … | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-digital-grid/README.md:148` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `the-dutchy… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-dutchy/README.md:148` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `the-dutchy` worker is **not** … | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-dutchy/README.md:149` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the two standalone workers… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-lab/README.md:167` |
| same monolith router via `api` in `docker-compose.uat.yml` — `the-lab` and `lab-service` are **not** in thi… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-lab/README.md:168` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `library-se… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-library/README.md:186` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `library-service` worker is **n… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-library/README.md:187` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `monitoring… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-observatory/README.md:160` |
| the `api` service in `docker-compose.development.yml` runs the same `tranc3-backend` monolith, so this enti… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-spark/README.md:169` |
| same monolith router via the `api` service in `docker-compose.uat.yml | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-spark/README.md:170` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `the-studio… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-studio/README.md:136` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `the-studio` worker is **not** … | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-studio/README.md:137` |
| the `api` service in `docker-compose.development.yml` runs the `/townhall/*` monolith router — the standalo… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-town-hall/README.md:115` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `cranbania` worker is **not** i… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/the-town-hall/README.md:116` |
| the `api` service in `docker-compose.development.yml` runs the same `tranc3-backend` monolith, so this enti… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/think-tank/README.md:158` |
| same monolith router via the `api` service in `docker-compose.uat.yml | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/think-tank/README.md:159` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `tranquilit… | Tranquility | [pack](../solution-packs/tranquility.md) | Partial | 1 | baseline (+1) | `docs/services/tranquility/README.md:139` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `tranquility` worker is **not**… | Tranquility | [pack](../solution-packs/tranquility.md) | Partial | 1 | baseline (+1) | `docs/services/tranquility/README.md:140` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `turings-hu… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/turings-hub/README.md:113` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `turings-hub-service` worker is… | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `docs/services/turings-hub/README.md:114` |
| the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `vrar3d` wo… | VRAR3D | [pack](../solution-packs/vrar3d.md) | Partial | 1 | baseline (+1) | `docs/services/vrar3d/README.md:149` |
| same monolith router via `api` in `docker-compose.uat.yml` — the standalone `vrar3d` worker is **not** in t… | VRAR3D | [pack](../solution-packs/vrar3d.md) | Partial | 1 | baseline (+1) | `docs/services/vrar3d/README.md:150` |
| Shamir's Secret Sharing for multi-party key recovery | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `docs/vault_security.md:300` |
| TPM 2.0 integration for platform-bound keys (available on most modern hardware) | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `docs/vault_security.md:301` |
| Secret scanning integration with GitHub Advanced Security (requires GitHub Enterprise) | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `docs/vault_security.md:304` |
| Automated compliance reporting (SOC 2, ISO 27001) (requires commercial tooling) | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `docs/vault_security.md:305` |
| TelemetryMiddleware` — trace ID propagation, metrics collection | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:375` |
| RateLimitMiddleware` — sliding window, tier multipliers, header injection | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:376` |
| AuthMiddleware` — JWT validation, API key, public path whitelist | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:377` |
| DefenseEngine` — rule evaluation, incident lifecycle, threat assessment | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:378` |
| HeartbeatAggregator` — scoring, alerting, trend analysis, deduplication | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:379` |
| GroqProvider` — complete(), health_check(), fallback | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:380` |
| DeepSeekProvider` — complete(), health_check(), fallback | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:381` |
| ZeroCostConfig` — provider discovery, chain selection, model catalog | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:382` |
| OCIStorageProvider` — upload, download, health check | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:383` |
| Full middleware stack — request through all middleware layers | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:386` |
| Ecosystem API — all new endpoints with authentication | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:387` |
| AI Gateway routing — failover through zero-cost chain | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:388` |
| Hybrid storage auto-sync — background task lifecycle | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-ARCHITECTURE_UPDATE.md:389` |
| Auth middleware, resilience patterns, compliance scanner | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-CROSS_REPO_SYNERGY.md:21` |
| Docker configs, deployment scripts | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-CROSS_REPO_SYNERGY.md:34` |
| Documentation | _unrouted_ | — | Partial | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Architecture-CROSS_REPO_SYNERGY.md:39` |
| Dashboard tile in Infinity Admin OS (future) | Infinity | [pack](../solution-packs/infinity.md) | Open | 1 | baseline (+1) | `wiki-content/Strategy-ADAPTIVE_PLATFORM_ROTATION.md:170` |
| Observatory alerts on failover (future) | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Strategy-ADAPTIVE_PLATFORM_ROTATION.md:171` |
| React Native app | _unrouted_ | — | Not started | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Strategy-DOC-13-Strategic-Analysis.md:169` |
| Stripe account created and verified | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Strategy-DOC-14-Zero-Cost-Hosting.md:89` |
| Pro tier price created (£29/mo) | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Strategy-DOC-14-Zero-Cost-Hosting.md:90` |
| Business tier price created (£149/mo) | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Strategy-DOC-14-Zero-Cost-Hosting.md:91` |
| Webhook endpoint configured | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Strategy-DOC-14-Zero-Cost-Hosting.md:92` |
| Free tier rate limits enforced | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Strategy-DOC-14-Zero-Cost-Hosting.md:93` |
| Upgrade prompts in frontend when limits hit | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Strategy-DOC-14-Zero-Cost-Hosting.md:94` |
| RapidAPI listing created (API marketplace) | API Marketplace | [pack](../solution-packs/api-marketplace.md) | Open | 1 | baseline (+1) | `wiki-content/Strategy-DOC-14-Zero-Cost-Hosting.md:95` |
| GitHub Sponsors profile set up | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Strategy-DOC-14-Zero-Cost-Hosting.md:96` |
| Affiliate programme page live | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Strategy-DOC-14-Zero-Cost-Hosting.md:97` |
| Git commit & push to main | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Todo-todo.md:51` |
| Git commit and push | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Todo-todo.md:78` |
| Push to GitHub — ⚠️ Token expired; commit ready locally on branch feat/phase28-advanced-bridge-systems | _unrouted_ | — | Open | 2 | baseline (+1); no Location named — routing first (+1) | `wiki-content/Todo-tranc3-ts-todo.md:22` |

---

**Total: 201 stories, 469 points.**

Velocity is not asserted here. This estate has no measured throughput to divide by, and a sprint count derived from an invented velocity would be the kind of confident, unfounded number the rest of these documents exist to avoid.
