# Product Lifecycle Gates

> **Generated from `src/townhall/plm.py` by `scripts/generate_plm_docs.py`.**
> Do not edit by hand — change the criteria in code and regenerate.
> `scripts/generate_plm_docs.py --check` fails CI when the two disagree.

## Policy

Every deliverable the platform produces — an application, a game, an
image, a video, a design system, a module, a template or a document —
is raised in The Town Hall as a lifecycle record and moves through the
stages below in order. A stage boundary is a gate.

A gate opens only when every mandatory criterion for that deliverable's
kind carries **passing** evidence. Three consequences follow, and they
are the whole point of the control:

1. **Evidence that failed does not satisfy a criterion.** A test suite
   that ran and went red is evidence against the gate. The most recent
   evidence is the one that counts, so a re-run that fails takes the
   satisfaction away again.
2. **A blocked gate refuses.** `advance()` raises `GateBlocked` and the
   HTTP surface answers 409 with the unmet criteria. It does not return
   a warning, because a gate a caller may ignore is a report.
3. **A waiver is not a pass.** Skipping a criterion requires a written
   reason and a named approver, and the decision is recorded as
   `waived`. The register can always distinguish work that was done
   from work that was excused.

Criteria are declared per deliverable kind. An image faces no build
gate and a module faces no accessibility audit, because a checklist a
deliverable can only half-satisfy trains everyone to waive the half
that never applied.

## Stages

### Concept

Establish that the thing is worth building at all.

| Criterion | Evidence | Supplied by | Applies to | Mandatory |
|---|---|---|---|---|
| `concept.business-case` | business_case | Think Tank | every kind | yes |

- **`concept.business-case`** — Why this is worth building, and what it costs to run.

### Initiation

Authorise the work and name who is accountable for it.

| Criterion | Evidence | Supplied by | Applies to | Mandatory |
|---|---|---|---|---|
| `initiation.authorised` | approval | The Town Hall | every kind | yes |

- **`initiation.authorised`** — The Town Hall has authorised the work to start.

### Design

Settle how it will look and behave before anyone builds it.

| Criterion | Evidence | Supplied by | Applies to | Mandatory |
|---|---|---|---|---|
| `design.reviewed` | design_review | Fabulousa | game, application, design_system, template, image, video | yes |
| `design.accessible` | accessibility_audit | Fabulousa | game, application, design_system, template | yes |

- **`design.reviewed`** — Fabulousa has reviewed the design against the token set.
- **`design.accessible`** — ARIA roles, contrast and keyboard reach audited against WCAG.

### Build

Produce the artefact and prove what went into it.

| Criterion | Evidence | Supplied by | Applies to | Mandatory |
|---|---|---|---|---|
| `build.artefact-registered` | build_artefact | The Artifactory | game, application, module, template | yes |
| `build.scanned` | security_scan | Cryptex | game, application, module, template | yes |

- **`build.artefact-registered`** — The build is in The Artifactory and addressable by digest.
- **`build.scanned`** — Cryptex has scanned the build and its dependencies.

### Validation

Prove it does what it was commissioned to do.

| Criterion | Evidence | Supplied by | Applies to | Mandatory |
|---|---|---|---|---|
| `validation.tested` | test_run | The Chaos Party | every kind | yes |

- **`validation.tested`** — The Chaos Party's suite has run against this deliverable.

### Release

Hand it over with the documentation somebody else can run it from.

| Criterion | Evidence | Supplied by | Applies to | Mandatory |
|---|---|---|---|---|
| `release.documented` | documentation | The Library | every kind | yes |
| `release.authorised` | approval | The Town Hall | every kind | yes |
| `release.lessons` | lessons_learned | The Basement | every kind | no |

- **`release.documented`** — Guide, procedure and policy published to The Library.
- **`release.authorised`** — The Town Hall has authorised release.
- **`release.lessons`** — Lessons recorded and archived to The Basement.

### Closed

Terminal. Nothing leaves this stage.

No gate leaves this stage.

## Criteria by deliverable kind

| Criterion | Stage | Evidence from | game | application | image | video | design_system | module | template | document |
|---|---|---|---|---|---|---|---|---|---|---|
| `concept.business-case` | concept | Think Tank | **required** | **required** | **required** | **required** | **required** | **required** | **required** | **required** |
| `initiation.authorised` | initiation | The Town Hall | **required** | **required** | **required** | **required** | **required** | **required** | **required** | **required** |
| `design.reviewed` | design | Fabulousa | **required** | **required** | **required** | **required** | **required** | — | **required** | — |
| `design.accessible` | design | Fabulousa | **required** | **required** | — | — | **required** | — | **required** | — |
| `build.artefact-registered` | build | The Artifactory | **required** | **required** | — | — | — | **required** | **required** | — |
| `build.scanned` | build | Cryptex | **required** | **required** | — | — | — | **required** | **required** | — |
| `validation.tested` | validation | The Chaos Party | **required** | **required** | **required** | **required** | **required** | **required** | **required** | **required** |
| `release.documented` | release | The Library | **required** | **required** | **required** | **required** | **required** | **required** | **required** | **required** |
| `release.authorised` | release | The Town Hall | **required** | **required** | **required** | **required** | **required** | **required** | **required** | **required** |
| `release.lessons` | release | The Basement | optional | optional | optional | optional | optional | optional | optional | optional |

## Procedure

All paths are relative to the platform API.

1. **Commission.** `POST /creative/commission` with the request in
   words. The creative route table names the Location and the
   deliverable kind, and the Town Hall record opens at *concept*.
   An unroutable request opens nothing — a deliverable naming no
   Location would stall forever at a gate nobody can evidence.
2. **Read the gate.** `GET /townhall/plm/deliverables/{id}/gate`
   lists what this deliverable still needs, and who supplies it.
3. **File evidence.** `POST /townhall/plm/deliverables/{id}/evidence`
   with the criterion id, a reference, and the outcome. File the
   failures too: an unrecorded failure is how a red result gets
   forgotten and re-run until it is green once.
4. **Waive, if you must.** `POST /townhall/plm/deliverables/{id}/waivers`
   with a reason and an approver. Both are required.
5. **Advance.** `POST /townhall/plm/deliverables/{id}/advance`. A 409
   carries the unmet criteria in its body; a 200 moves the record
   to the next stage and writes the gate decision.
6. **Audit.** `GET /townhall/plm/deliverables/{id}/history` returns
   every gate decision oldest first, including which criteria were
   waived and by whom.

## Worked example — a game

- Leaving **concept** needs: `concept.business-case`
- Leaving **initiation** needs: `initiation.authorised`
- Leaving **design** needs: `design.reviewed`, `design.accessible`
- Leaving **build** needs: `build.artefact-registered`, `build.scanned`
- Leaving **validation** needs: `validation.tested`
- Leaving **release** needs: `release.documented`, `release.authorised`

Which is why a request to make a game cannot reach release without Fabulousa having reviewed its design and audited its accessibility, Cryptex having scanned its build, The Chaos Party having tested it, and The Library holding its documentation.
