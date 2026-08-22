---
title: "Zero-Cost Vendor Matrix"
category: Reference
last-reviewed: 2026-07-27
status: needs-update
---

# Zero-Cost Vendor Matrix

**Owner:** Platform Engineering
**Source of truth:** `config/zero_cost/providers.yaml` (loaded by `src/zero_cost/registry.py`)
**Verification:** `python3 scripts/zero_cost_audit.py` — this document's own presence is one of that
script's two pass conditions (the other being zero rotation-chain validation errors); see
`scripts/zero_cost_audit.py`'s `main()`.

This is the human-readable companion to the registry, not a duplicate of it — when the two
disagree, `providers.yaml` is authoritative and this file should be regenerated/updated to match.

---

## 1. Purpose

`CLAUDE.md`'s "Zero-Cost Self-Hosted Architecture (Fortiere)" section states the platform's goal:
eliminate paid external-service dependencies. This matrix is the enforcement mechanism's own
documentation — it exists so `scripts/zero_cost_audit.py` can confirm (not just assert) that every
provider actually wired into a rotation chain is on an approved, zero-cost list, and that the five
paid AI APIs the mandate exists to avoid stay hard-blocked.

---

## 2. Approved self-hosted / zero-cost providers

30 entries in `approved_self_hosted` (registry `version: 2026-06`), grouped by category:

| Category | Provider ID | Cost / license basis |
|---|---|---|
| AI inference | `litellm` | MIT — self-hosted aggregator proxy, zero-cost |
| AI inference | `ollama` | MIT — local only |
| AI inference | `llama-cpp-python` | MIT — GGUF quantized local inference (CPU/GPU) |
| AI inference (free-tier-gated) | `groq` | Free tier when `GROQ_API_KEY` set — 14.4k req/day cap |
| AI inference (free-tier-gated) | `gemini` | Free tier when `GOOGLE_GEMINI_API_KEY` set |
| AI inference (free-tier-gated) | `github-models` | Free with any GitHub PAT, no card — 50 req/day GPT-4o, 150/day gpt-4o-mini |
| AI inference (free-tier-gated) | `cerebras` | Free tier when `CEREBRAS_API_KEY` set |
| AI inference (free-tier-gated) | `sambanova` | Free tier when `SAMBANOVA_API_KEY` set |
| AI inference (free-tier-gated) | `mistral` | Free tier — 500K tokens/month, `MISTRAL_API_KEY` |
| AI inference (free-tier-gated) | `cohere` | Free tier — 100K tokens/month (token-based), `COHERE_API_KEY` |
| AI inference (free-tier-gated) | `deepseek` | Free tier (soft limits), `DEEPSEEK_API_KEY` |
| CI/CD | `forgejo` | Forgejo OSS — The Workshop |
| CI/CD | `woodpecker-ci` | Apache 2.0 — self-hosted, alongside Forgejo |
| Ingress | `traefik` | OSS |
| Observability | `prometheus` | OSS |
| Observability | `grafana` | OSS |
| Observability | `loki` | OSS |
| Secrets | `vault-ce` | BSL — self-hosted Vault on The Citadel |
| Security scanning | `trivy` | Apache 2.0 |
| Security scanning | `grype` | Apache 2.0 |
| Security scanning | `osv-scanner` | Apache 2.0 |
| Security scanning | `semgrep` | OSS CLI in CI |
| Security scanning | `gitleaks` | MIT |
| Creative | `blender` | GPL — TateKing/TranceFlow pipeline |
| Creative | `penpot` | MPL — Fabulousa |
| Storage | `ipfs` | Self-hosted node |
| Vector DB | `qdrant` | Apache 2.0, self-hosted |
| Vector DB | `chromadb` | Apache 2.0 — local SQLite in dev, Postgres in prod |
| Database | `sqlite` | Public domain |
| Automation | `ansible-core` | GPL — Citadel health probes |

This directly evidences `CLAUDE.md`'s stated architecture principles (SQLite over D1, self-hosted
FastAPI/Ollama over paid APIs, Forgejo over GitHub Actions, Vault over Cloudflare secrets,
IPFS/local storage over R2) — each principle has a real, registered provider backing it.

**Approved free-tier-only providers:** 0 (`approved_free_tier` is currently empty — every
currently-approved free-tier provider is bucketed under `approved_self_hosted` above instead).

---

## 3. Blocked-paid providers (hard stop)

5 entries in `blocked_paid` — `assert_zero_cost()` raises `ValueError` if any of these appear in a
rotation chain or are requested directly:

| Provider ID | Why blocked |
|---|---|
| `openai` | Paid API — the platform's own zero-cost mandate exists specifically to avoid this |
| `anthropic` | Paid API |
| `azure-openai` | Paid API |
| `gpt4` | Paid API alias |
| `claude-api-paid` | Paid API alias |

---

## 4. Conditional-cloud providers (real limits, not zero-risk)

`conditional_cloud` entries are free-tier cloud services with a documented cap or expiry risk —
listed for awareness, not part of the always-on rotation chains:

| Provider ID | Category | Limits | Risk |
|---|---|---|---|
| `aws-always-free` | cloud | Lambda 1M/mo, DynamoDB 25GB, SNS/SQS 1M — card required | credits_expire |
| `gcp-always-free` | cloud | e2-micro US, Cloud Run 2M req — billing account required | credits_expire |
| `oracle-always-free` | cloud | 4 OCPU ARM + 200GB — card, capacity often scarce | idle_reclaim |
| `cloudflare-free` | edge | 100K workers req/day — legacy path being retired | quota_caps |
| `openrouter-free` | ai_inference | ~50 req/day `:free` models | daily_cap |
| `huggingface-inference` | ai_inference | ~$0.10/mo inference credits on free account | monthly_cap |
| `supabase-free` | database | 500MB — pauses after 7d idle | idle_pause |
| `github-public` | forge | Unlimited Actions on public repos; 2,000 min/mo private | private_repo_limits |
| `gitlab-free` | forge | 400 compute min/mo shared runners; unlimited self-hosted | monthly_cap |
| `together-ai` | ai_inference | $1 signup credit — refreshes periodically, NOT guaranteed | credits_expire |
| `fireworks-ai` | ai_inference | $1/mo credit — refreshes monthly, NOT guaranteed | credits_expire |

---

## 5. Rotation chains (live audit result)

Verified by running `python3 scripts/zero_cost_audit.py` against the current registry
(`version: 2026-06`) — 0 chain-validation errors across all 6 defined chains:

| Chain | Provider count | Providers (in fallback order) |
|---|---|---|
| `embeddings_default` | 7 | local_embeddings → ollama → huggingface → openrouter_free → cohere_free → voyage_free → offline_embeddings |
| `image_default` | 7 | comfyui_local → stable_diffusion_local → huggingface_inference → replicate_free → pollinations → leonardo_free → offline_image |
| `stt_default` | 7 | whisper_local → faster_whisper → groq_whisper → assemblyai_free → deepgram_free → openai_whisper_free → offline_stt |
| `zero_cost_cloud` | 8 | huggingface → openrouter_free → groq_free → cerebras_free → sambanova_free → mistral_free → github_models_free → offline |
| `zero_cost_full` | 9 | ollama → huggingface → openrouter_free → groq_free → cerebras_free → sambanova_free → mistral_free → github_models_free → offline |
| `zero_cost_local` | 2 | ollama → offline |

`inference_default`/`inference_local`/`inference_full` are legacy aliases (`_CHAIN_ALIASES` in
`src/zero_cost/registry.py`) resolving to `zero_cost_cloud`/`zero_cost_local`/`zero_cost_full`
respectively — not separate chains.

---

## 6. Policy (`providers.yaml`'s `policy` block)

| Setting | Value |
|---|---|
| Model | `zero_cost_first` |
| Max paid providers | `0` |
| Require self-hosted first | `true` |
| Rotation chain size | 6–8 providers |
| Quota hard stop | `true` |
| Daily request limit per provider | 5,000 |
| Cooldown on exhaustion | 3,600s (1 hour) |

---

## 7. Known gap: Cloud-Only default vs. zero-cost mandate

Per `CLAUDE.md`, every Location currently defaults to **Cloud Only** (the ~26 live Cloudflare
Workers), with Hybrid/Local-Only blocked purely on server funding. The AI-inference layer audited
here is genuinely zero-cost today since it's a cross-cutting service (`src/ai_gateway/`), not tied
to per-Location hosting mode — but the *hosting* layer (which Cloudflare Workers vs. self-hosted
Python workers run a given Location) is not zero-cost in the strict self-hosted sense until that
funding gap closes. This is a pre-existing, tracked gap, not new information.

---

## 8. Review schedule

| Activity | Frequency |
|---|---|
| `scripts/zero_cost_audit.py` run | Every PR touching `config/zero_cost/providers.yaml` or `src/zero_cost/registry.py`, and monthly |
| Full re-review of this matrix | Quarterly, aligned with the Magna Carta compliance framework's review cycle |

---

## 9. Cross-references

- `config/zero_cost/providers.yaml` — machine-readable registry (source of truth)
- `src/zero_cost/registry.py` — loader, chain resolution, `assert_zero_cost()` hard stop
- `scripts/zero_cost_audit.py` — the executable audit this document satisfies
- Magna Carta `docs/compliance/ZERO-COST-MATRIX.md` (MC-021) — the estate-wide compliance framing of this same registry
