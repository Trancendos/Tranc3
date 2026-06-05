# Trancendos Zero-Cost Service Registry

> **Honesty commitment**: This document lists every external service the platform uses or may use.
> Each entry is marked with its true free-tier status. No guesswork — if something is only free for
> 12 months, that is written clearly. If it requires a credit card even for the free tier, that is noted.

---

## ✅ GENUINELY FREE FOREVER (no expiry, no credit card needed)

### Edge / Compute
| Service | Free Limit | Notes | Sign-up |
|---|---|---|---|
| **Cloudflare Workers** | 100,000 req/day | No expiry. The backbone of the platform. | cloudflare.com |
| **Cloudflare Pages** | Unlimited builds + bandwidth | Hosts trancendos.com frontend. No limit on visitors. | cloudflare.com |
| **Cloudflare Workers AI** | ~10,000 req/day | On-platform GPU inference. No API key needed. | cloudflare.com |
| **Cloudflare KV** | 100,000 reads/day, 1,000 writes/day | Used for caching + usage counters. | cloudflare.com |
| **Cloudflare D1** | 25M row reads/day, 50K writes/day, 5GB | SQLite at edge. Primary DB for all Workers. | cloudflare.com |
| **Cloudflare R2** | 10 GB storage, 10M reads/month, 1M writes/month | Zero egress fees. Primary object storage. | cloudflare.com |
| **Cloudflare Queues** | 1,000,000 messages/month | Task queue. Primary queue provider. | cloudflare.com |

### AI Providers (all free-tier text generation)
| Service | Free Limit | Model | Notes |
|---|---|---|---|
| **Groq** | 6,000 RPM, unlimited daily (soft cap) | llama-3.1-8b-instant | Fastest free inference available. |
| **Google Gemini** | 15 RPM / 1M tokens/day | gemini-1.5-flash | Google AI Studio free plan. |
| **Cerebras** | 60 RPM | llama3.1-8b | Wafer-scale chips, very fast. |
| **SambaNova** | 80 requests/day | Meta-Llama-3.1-8B | Hard daily cap — used last in rotation. |
| **OpenRouter** | Free models, no daily cap | llama-3.2-3b:free | Credit system, free models genuinely free. |
| **HuggingFace** | ~1,000 req/day (soft) | Mistral-7B-Instruct | Rate limited but no hard cap on free. |
| **DeepSeek** | Free tier (soft limits) | deepseek-chat | China-based, may have latency from EU. |
| **Mistral AI** | 500K tokens/month | mistral-small-latest | La Plateforme free plan. |
| **Cohere** | 1,000 API calls/month | command-r | Requires account, no credit card. |
| **Together AI** | $1 free credit on signup | Llama-3.2-3B-Turbo | Credit refreshes periodically (not guaranteed). |
| **Fireworks AI** | ~$1/month credit | llama-v3p1-8b-instruct | Free credit, refreshes monthly (not guaranteed). |

### Email
| Service | Free Limit | Notes |
|---|---|---|
| **Resend** | 3,000 emails/month, 100/day | No credit card. Best developer UX. resend.com |
| **Brevo** | 9,000 emails/month, 300/day | No credit card. Best volume for free. brevo.com |
| **Mailjet** | 6,000 emails/month, 200/day | No credit card. mailjet.com |

### Storage
| Service | Free Limit | Notes |
|---|---|---|
| **Cloudflare R2** | 10 GB, zero egress | See above — best choice. |
| **Backblaze B2** | 10 GB, 1 GB/day egress free | Genuinely free forever. backblaze.com |
| **Oracle Cloud Object Storage** | 20 GB | Part of Always Free tier — permanent. oracle.com/cloud |

### Database
| Service | Free Limit | Notes |
|---|---|---|
| **Cloudflare D1** | 5 GB, 25M reads/day | See above. |
| **Turso** | 500 DBs, 1B row reads/month | SQLite, globally distributed, free forever. turso.tech |
| **Neon** | 0.5 GB, 190 compute-hours/month | PostgreSQL serverless, free forever. neon.tech |
| **Supabase** | 500 MB, 50K MAUs | PostgreSQL + Auth + Storage. Pauses after 1 week inactivity on free. supabase.com |

### Search
| Service | Free Limit | Notes |
|---|---|---|
| **Typesense Cloud** | 1M records, unlimited searches | Best free search. No monthly cap on searches. cloud.typesense.org |
| **Meilisearch Cloud** | 100K documents, 10K req/month | Good free tier. meilisearch.com |
| **Algolia** | 10K req/month, 10K records | 10K monthly cap — used as fallback only. algolia.com |

### Queue
| Service | Free Limit | Notes |
|---|---|---|
| **Cloudflare Queues** | 1M messages/month | See above. |
| **Upstash Redis** | 10,000 commands/day | Free forever. upstash.com |

### Compute (self-hosted)
| Service | Free Limit | Notes |
|---|---|---|
| **Oracle Cloud Always Free** | 4 ARM cores, 24GB RAM, 200GB block storage, 20GB object, 10TB/month egress | **Genuinely permanent** — not a trial. Best free compute available. oracle.com/cloud |
| **Google Cloud (e2-micro)** | 1 e2-micro VM (0.25 vCPU, 1GB RAM) | Always free, 1 region only (us-east1/us-west1/us-central1). cloud.google.com |
| **Google Cloud Run** | 2M requests/month, 360,000 GB-seconds | Always free tier for serverless containers. cloud.google.com |

---

## ⚠️ FREE TRIAL ONLY — 12 MONTHS, THEN BILLING STARTS

These platforms offer "free tiers" that expire after 12 months. They are **NOT used** in this platform because they cannot be relied on for permanent zero-cost operation.

| Service | Trial Duration | What happens after 12 months | Decision |
|---|---|---|---|
| **AWS Free Tier** | 12 months only | Billing starts automatically. EC2 t2.micro, S3 5GB, Lambda 1M/month. | ❌ NOT used |
| **Microsoft Azure Free** | 12 months + $200 credit | Billing starts after trial ends. B1s VM, 5GB Blob storage. | ❌ NOT used |

> **Honest note on AWS/Azure**: Both have some services that are "always free" (AWS Lambda 1M req/month, Azure Functions 1M req/month). However, the compute tiers (EC2, Azure VMs) that would matter for hosting are 12-month trials only. We do not rely on these.

---

## ❌ NOT APPLICABLE (no backend APIs relevant to this platform)

| Platform | What it actually is | Why not used |
|---|---|---|
| **AutoCAD** | CAD design software | No backend compute APIs. Drawing tool only. |
| **Adobe Creative Cloud** | Design tools (Photoshop, Illustrator) | No backend compute APIs. Adobe Firefly has an API but it is paid, not free. |

> **Honest note on Adobe**: Adobe does have developer APIs (PDF Services, Creative SDK), but these are paid services. Adobe's free tier is limited to the Creative Cloud desktop apps — there is no permanently free backend API tier relevant to the Trancendos platform. If image generation is needed, Stable Diffusion (self-hosted via Oracle free compute) is the correct zero-cost choice.

---

## Platform Capacity Summary (zero cost, per day)

| Category | Combined Free Capacity |
|---|---|
| **AI inference** | ~18,000 requests/day across 12 providers |
| **Email** | 600 emails/day (Resend 100 + Brevo 300 + Mailjet 200) |
| **Storage** | 40 GB total (R2 10 + B2 10 + Oracle 20) |
| **Database reads** | 25M+/day (D1) + 1B row reads/month (Turso) |
| **Edge requests** | 100,000 req/day (Workers) |
| **Queue messages** | 1M/month (CF Queues) + 10K commands/day (Upstash) |
| **Search** | Unlimited (Typesense) + 10K/month (Meilisearch) + 10K/month (Algolia) |
| **Frontend serving** | Unlimited (CF Pages) |

---

## Cloudflare Workers Deployed

| Worker | URL | Purpose |
|---|---|---|
| `tranc3-ai` | `tranc3-ai.luminous-aimastermind.workers.dev` | AI gateway, 12-provider rotation |
| `tranc3-notifications` | `tranc3-notifications.luminous-aimastermind.workers.dev` | Email rotation |
| `tranc3-storage` | `tranc3-storage.luminous-aimastermind.workers.dev` | Object storage rotation |
| `tranc3-search` | `tranc3-search.luminous-aimastermind.workers.dev` | Search rotation |
| `tranc3-queue` | `tranc3-queue.luminous-aimastermind.workers.dev` | Task queue rotation |
| `infinity-void` | `infinity-void.luminous-aimastermind.workers.dev` | AES-GCM encrypted vault |
| `trancendos-api-gateway` | `trancendos-api-gateway.luminous-aimastermind.workers.dev` | API routing |
| `trancendos-frontend` | `trancendos.com` | React/Vite SPA (CF Pages) |

---

## Deploy Command

```bash
cd cloudflare
./deploy-all.sh secrets   # set API keys interactively
./deploy-all.sh all       # deploy all workers + frontend
```

Total monthly cost: **£0.00**
