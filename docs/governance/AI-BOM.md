---
title: "AI-BOM — the models this platform consumes"
category: Reference
last-reviewed: 2026-08-19
status: needs-update
---

# AI-BOM — the models this platform consumes

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-08-19

**Inventory:** [`config/ai_models.yaml`](../../config/ai_models.yaml) ·
**Generator:** [`scripts/ai_bom.py`](../../scripts/ai_bom.py) ·
**Output:** `logs/ai-bom.cyclonedx.json` (CycloneDX 1.6) ·
**Supersedes the "premature" judgement in:** [BOM-MATRIX.md](BOM-MATRIX.md) §3

---

## 1. What changed, and why this is not a reversal

`BOM-MATRIX.md` assessed AI-BOM on 2026-07-31 and recorded it as *"a genuine gap — and
premature"*, on the reasoning that an AI-BOM cataloguing training-data provenance,
hyperparameters and foundational-model lineage would describe a model that does not
exist: `Tranc3Engine` runs in bootstrap mode with no trained weights.

That reasoning was right, and it answered a narrower question than the one that matters.
It was about models Trancendos **trains**. It said nothing about models Trancendos
**consumes** — and the platform consumes sixteen model references across six model
families and two hosted inference providers, every one of which carries a licence, an
origin, and an execution location.

A consumed model raises those questions whether or not anyone ever fine-tunes it. So this
document closes the second half without disturbing the first. Training-lineage AI-BOM
remains premature. Consumption AI-BOM was overdue.

## 2. The problem this solves

Model identifiers are not dependencies in any sense a package manager understands. Nothing
in `requirements.txt` or any `package.json` mentions `llama3.2:1b`, `all-MiniLM-L6-v2` or
`t5-small`. They arrive as bare strings — an env default, an adapter constant, a provider's
capability list — and dependency scanning walks straight past them.

The 2026 OSSRA report names this directly: models may be *deliberately obscured*,
*undeclared*, or *modified from origin*, and 49% of surveyed organisations ship open source
AI/ML models in their products. "You cannot secure what you cannot see" is the whole point.

## 3. What the inventory found

| Family | Licence | Class | Disposition |
|---|---|---|---|
| `sentence-transformers/all-MiniLM-L6-v2` | apache-2.0 | permissive | ACCEPT |
| `nomic-ai/nomic-embed-text-v1.5` | apache-2.0 | permissive | ACCEPT |
| `google-t5/t5-small` | apache-2.0 | permissive | ACCEPT |
| `mistralai/Mistral-7B-Instruct-v0.3` | apache-2.0 | permissive | ACCEPT |
| `Qwen/Qwen2.5-0.5B-Instruct` | apache-2.0 | permissive | ACCEPT |
| **Llama 3.x family** (13 variant ids) | **llama3 / 3.1 / 3.2 / 3.3 Community** | **community** | **REVIEW** |

Plus two hosted providers — OpenRouter `:free` and the Hugging Face Inference API — both
marked REVIEW, because they are the tiers where prompt content leaves the estate.

Every licence value was verified against the publisher's own declaration via
`https://huggingface.co/api/models/{id}` on 2026-08-19, not inferred from the model's
reputation.

## 4. The finding worth acting on: "Built with Llama"

Five of the six model families are Apache-2.0 and need nothing beyond ordinary attribution
on redistribution. The sixth is the most heavily depended-upon family in the estate — Llama
appears across every inference tier, local and hosted — and it is **not open source**.

Meta's Llama Community Licence is not OSI-approved and carries three obligations that
Apache-2.0 habits do not prepare anyone for:

1. **An Acceptable Use Policy** restricting certain applications.
2. **A monthly-active-user threshold** (700 million at time of writing) above which a
   separate licence must be requested from Meta.
3. **Attribution** — products built with it must display **"Built with Llama"**, and
   derivative model names must begin with "Llama".

Of these, (2) is not a live concern and probably never will be. (1) is a policy question
for whatever the platform ends up doing.

**(3) is a live, cheap, and currently unmet obligation.** It applies from first release,
nothing in the product displays it today, and — like every attribution requirement — it is
trivial to satisfy before launch and awkward to retrofit into a released UI and a published
set of screenshots. The estate is undeployed, so the cheap moment is now.

**Recommended action before go-live:** add "Built with Llama" attribution wherever the
product surfaces its AI capabilities, most naturally in Arcadia's front-end footer or an
about/credits panel. This is a small piece of work whose cost is entirely in remembering
to do it, which is what this document is for.

## 5. How this stays true

An inventory that is only a document rots the first time someone adds a model and forgets
to update it. So `scripts/ai_bom.py --check` scans `src/`, `workers/` and `api.py` for
model identifiers and fails when one appears in code but not in the inventory.

That is the same reviewed-versus-unexamined distinction already used by
`SECURITY_ALERT_REGISTER.md` for vulnerabilities and `OBSOLESCENCE-ACCEPTED.md` for dormant
dependencies, applied to a third surface. A model in the inventory is a **decided** risk; a
model only in the code is an **unexamined** one, and only the second fails the build.

Pure detection was rejected as the sole mechanism because it cannot distinguish a model the
platform depends on from one named in a comment or a provider's advertised capability list.
That is not hypothetical — the first run of the detector reported `phi:.2f` (an f-string
format spec rendering a consciousness value) and `llama3.2:user` (a colon-delimited cache
key in a test fixture) as models. Both are now excluded: the Ollama tag pattern requires a
parameter-size suffix, and test trees are skipped.

## 6. Why CycloneDX, and where it goes

Output is CycloneDX 1.6 with `machine-learning-model` components — the same format
`.forgejo/workflows/security-scan.yml` already produces via syft for ordinary dependencies.
That is deliberate: the AI-BOM lands *in* the existing SBOM pipeline and its Dependency-Track
upload rather than beside it, so there is one supply-chain inventory rather than two.

One detail worth noting in the generator: a licence is emitted as a CycloneDX
`license.id` (an SPDX identifier) only when it genuinely is one. The Llama community
licences are emitted as `license.name` instead, because expressing `llama3.2` as an SPDX id
would file it alongside Apache-2.0 and MIT — reproducing, inside the BOM, the exact
confusion this document exists to prevent.

## 7. Regulatory relevance

**EU AI Act.** Organisations must be able to demonstrate what models are present, where
they originated, how they have been modified, and where they execute. The inventory records
all four, including a `data_egress` answer per model — which is the field that distinguishes
"runs locally under Ollama" from "prompt content leaves the estate".

**EU CRA.** Models consumed from third parties are third-party components, and the CRA's
supply-chain accountability extends to them. See
[EU-CRA-PROFILE.md](../../compliance/magna-carta/docs/compliance/EU-CRA-PROFILE.md).

## 8. Review

Re-verify licences at least annually, and whenever a model family is added or a variant's
size changes. That second trigger is not pedantry: the Qwen family is not uniformly
Apache-2.0 across sizes, so changing `qwen2.5:0.5b` to a larger variant is a licence
question wearing the costume of a config tweak.
