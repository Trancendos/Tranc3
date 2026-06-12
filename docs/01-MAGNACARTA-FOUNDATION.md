# Magna Carta Foundation — Zero-Cost Sovereignty Principle

**Version:** 1.0.0 | **Classification:** UNCLASSIFIED — PUBLIC | **Review:** Quarterly

## 1. Purpose

This document establishes the Magna Carta Zero-Cost Sovereignty Principle as a foundational requirement for the Trancendos / Tranc3 platform. It guarantees that core platform capabilities remain operable without mandatory paid third-party APIs or proprietary vendor lock-in.

## 2. Sovereignty Guarantee

The Tranc3 platform SHALL maintain operational capability across all P0 and P1 services using exclusively:

- **Self-hosted Python/FastAPI workers** (ports 8004–8071)
- **SQLite** per-worker databases (zero cost, no external DB required)
- **Local filesystem + IPFS** (replacing Cloudflare R2)
- **Ollama** (local LLM inference, free, zero egress cost)
- **Forgejo** (self-hosted CI/CD, replacing GitHub Actions)

## 3. Vendor Dependency Register

| Dependency | Type | Cost Tier | Self-Hosted Alternative | Status |
|---|---|---|---|---|
| Cloudflare Workers | Edge compute | Paid (legacy) | FastAPI + Traefik | Migrating |
| Cloudflare D1 | Database | Paid (legacy) | SQLite | Complete |
| Cloudflare R2 | Object storage | Paid (legacy) | IPFS + local volume | Complete |
| Cloudflare KV | Key-value cache | Paid (legacy) | In-memory LRUCache | Complete |
| OpenRouter | AI inference | Free tier | Ollama (local) | Fallback only |
| HuggingFace Inference | AI inference | Free tier | Ollama (local) | Fallback only |

## 4. Five-Tier AI Gateway (Zero-Cost Fallback Chain)

```
Tier 1: Ollama (localhost:11434)         — zero cost, local inference
Tier 2: HuggingFace Inference API        — free tier, external
Tier 3: OpenRouter :free models          — free tier, cloud
Tier 4: TRANC3_BACKEND_URL               — self-hosted (Fly.io free)
Tier 5: OfflineProvider (stub response)  — deterministic, always available
```

No paid provider is required for Tier 1 or Tier 5. The platform is always functional.

## 5. Self-Hosted Worker Inventory

All 38 P0–P3 workers in `docker-compose.production.yml` operate on:
- **Storage:** SQLite (each worker owns `data/databases/<worker>.db`)
- **Compute:** FastAPI + uvicorn (Python 3.11+, no licence cost)
- **Routing:** Traefik (open-source, Apache 2.0)
- **Secrets:** HashiCorp Vault (BSL) or self-hosted KV

## 6. Customer Opt-In for Paid Dependencies

Where a user or integration requires a paid external service (e.g., Stripe for payments, Twilio for SMS), these are:

1. **Explicitly opt-in** — disabled by default in `.env.example`
2. **Isolated to dedicated workers** (`workers/payments-service/`, `workers/sms-service/`)
3. **Never required** for core authentication, governance, AI inference, or compliance

## 7. Compliance Mapping

| Control | Framework | Status |
|---|---|---|
| MC-RULE-005 zero_cost checks | Magna Carta | Enforced |
| ISO27001 A.5.19 Supplier relationships | ISO 27001:2022 | PROGRAMME_ARTEFACT |
| REQ-IA-002 Platform independence | DEFSTAN | COMPLIANT |

## 8. Review History

| Date | Reviewer | Changes |
|---|---|---|
| 2026-06-12 | Trancendos | Initial version — sovereignty principle formalised |
