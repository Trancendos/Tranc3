# Research & advancement digest (May 2026)

Consolidates GitHub/org review, external OSS, and vendor landscape for **regulated, zero-cost-first** Tranc3 evolution.

## Trancendos GitHub — use this, not mass merges

| Action | Source |
|--------|--------|
| **Merge** | `cursor/platform-layer-rotation-6d5c`, `cursor/windows-*-6d5c` |
| **Cherry-pick** | `fix/go-grpc-security-81`, `cursor/production-readiness-ci-fixes-2277` |
| **Close without merge** | PRs #84–89, `merge/aeonmind-into-main`, `phase-24/aeonmind-polyglot-v0.9.0` |
| **Port code from** | `infinity-adminOS` (void, webauthn, quantum-safe, policy-engine) |

Run: `python scripts/branch_benefit_audit.py`

## External repos (approved OSS foundations)

| Need | Project |
|------|---------|
| Workflows | n8n → The Digital Grid |
| Wiki | Outline → The Library |
| Observability | SigNoz → The Observatory |
| Documents | Paperless-ngx → DocUtari |
| Design | Penpot → Fabulousa |
| IaC | OpenTofu |
| Vector | Qdrant (self-hosted) |

**Avoid for production:** web-scrape “free API” proxies (e.g. unofficial DeepSeek bridges) — ToS and compliance risk.

## Vendors (overflow only unless noted)

| Vendor | Zero-cost path | Tranc3 |
|--------|----------------|--------|
| Groq, Gemini Flash, Cerebras, SambaNova, HF | Free API keys | AI rotator |
| OpenRouter | `:free` + `openrouter/free` router | AI rotator (enhanced) |
| Ollama | Local | LOCAL_ONLY / HYBRID |
| Anthropic, OpenAI, Perplexity | Paid / trial only | Not default |
| DeepSeek | OpenRouter `:free` or paid API | Not scrape |

## Implemented from this research

- Platform layer rotator (`src/platform/layer_rotator.py`)  
- `openrouter/free` in `zero_cost_config.py`  
- The Town Hall expansion (`docs/THE_TOWN_HALL.md`)  
- This digest  

## Next priorities

1. Merge platform-layer + Windows branches to `main`  
2. infinity-adminOS P1 ports (void, webauthn)  
3. Persistent Town Hall store (SQLite) + Forgejo policy gates  
4. Close stale PRs (`gh pr close 84 86 87 88 89`)
