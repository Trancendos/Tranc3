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
| **Cloudflare Workers AI** | ~10,000 req/day | llama-3.1-8b-instruct | On-platform, zero latency, no key needed. |
| **Groq** | 6,000 RPM, unlimited daily (soft cap) | llama-3.1-8b-instant | Fastest free inference available. |
| **Google Gemini** | 15 RPM / 1M tokens/day | gemini-1.5-flash | Google AI Studio free plan. |
| **GitHub Models** | 50 RPD (GPT-4o), 150 RPD (Llama 3.1 70B) | gpt-4o-mini / llama-3.1-70b | **Requires GitHub account only — no credit card, no payment.** Any PAT works. Rate: 10 RPM, 8K input / 4K output per request. |
| **Cerebras** | 60 RPM | llama3.1-8b | Wafer-scale chips, very fast. |
| **SambaNova** | 80 requests/day | Meta-Llama-3.1-8B | Hard daily cap — used last in rotation. |
| **OpenRouter** | Free models, no daily cap | llama-3.2-3b:free | Credit system, free models genuinely free. |
| **HuggingFace** | ~1,000 req/day (soft) | Mistral-7B-Instruct | Rate limited but no hard cap on free. |
| **DeepSeek** | Free tier (soft limits) | deepseek-chat | China-based, may have latency from EU. |
| **Mistral AI** | 500K tokens/month | mistral-small-latest | La Plateforme free plan. |
| **Cohere** | 100K tokens/month (not 1K req — corrected) | command-r | Requires account, no credit card. |
| **Together AI** | $1 free credit on signup | Llama-3.2-3B-Turbo | Credit refreshes periodically (not guaranteed). |
| **Fireworks AI** | ~$1/month credit | llama-v3p1-8b-instruct | Free credit, refreshes monthly (not guaranteed). |

### AI Providers — Honest Corrections
> **Replicate**: Requires a credit card even for the free tier. NOT zero-cost. Not used.
> **Stability AI**: Free API tier ended in 2024. NOT available. Not used.
> **Cohere**: The free tier is 100K tokens/month (not 1K requests — the limit is token-based).

### Local / Self-Hosted AI (Zero Ongoing Cost)
| Tool | Free Limit | Notes |
|---|---|---|
| **Ollama** | Unlimited (self-hosted) | Runs LLMs locally. Works on Oracle free ARM (slow but free). |
| **llama.cpp / GGUF** | Unlimited (self-hosted) | 7B Q4_K_M runs in ~6GB RAM on Oracle ARM at ~0.5-2 tok/sec. |
| **LocalAI** | Unlimited (self-hosted) | Docker, OpenAI-compatible API. Deploy on Oracle free VM. |
| **Whisper** | Unlimited (self-hosted) | Speech-to-text. whisper-base.en (140MB) runs on CPU. |
| **Piper TTS** | Unlimited (self-hosted) | Neural text-to-speech. MIT license. CPU-only, fast. |

**Honest note on self-hosted inference:** Oracle Cloud Always Free gives you 4 ARM cores and 24GB RAM. A 7B quantized model can run inference, but at ~0.5–2 tokens/second. This is viable for batch tasks or non-real-time use, but not suitable for interactive chat at scale. For real-time use, cloud provider rotation (above) is faster and still free.

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

### CI/CD (Zero-Cost Options)
| Service | Free Limit | Notes |
|---|---|---|
| **Forgejo + Woodpecker CI** | Unlimited (self-hosted) | **Primary CI/CD.** Forgejo at trancendos.com/the-workshop. Woodpecker runs on same Oracle VM. Fully open-source (GPL + Apache 2.0). |
| **GitHub Actions** | 2,000 min/month (private repos) | Free for public repos (unlimited). Self-hosted runners = unlimited minutes. |
| **GitLab CI** | 400 min/month (shared runners) | 10GB storage per project. Self-hosted runners: unlimited. |
| **Bitbucket Pipelines** | 50 min/month | **Very limited** — not recommended unless also using self-hosted runners. |

> **Honest note:** If you use self-hosted runners for GitHub/GitLab/Bitbucket, minutes are unlimited at zero cost — the runner runs on your Oracle free VM. The minute limits only apply to their hosted runners.

### Model Training (Honest Assessment)
| Platform | Free GPU | Limit | Realistic Use |
|---|---|---|---|
| **Kaggle** | T4 (16GB VRAM) | 30 hours/week | **Best for fine-tuning.** LoRA/QLoRA on Mistral 7B works. Use Unsloth for 2-5x speedup. |
| **Google Colab** | T4 / P100 (random) | ~12h session, no weekly cap | Sessions disconnect when idle. Use Kaggle instead for reliability. |
| **HuggingFace Spaces** | T4 (intermittent) | No formal limit | **Not reliable for training.** Use for inference demos only. |

> **Honest bottom line on training:** Training an LLM from scratch at zero cost is not feasible. Fine-tuning an existing model (Llama 3.1 8B or Mistral 7B with LoRA on Kaggle) is realistic and zero-cost. The Tranc3Engine architecture exists in code but has no trained weights — it falls back to provider rotation. Fine-tuned weights from Kaggle would be stored as LoRA adapters and loaded at inference time.

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
| **AI inference** | ~18,048 requests/day across 13 cloud providers + unlimited via self-hosted Ollama |
| **Email** | 600 emails/day (Resend 100 + Brevo 300 + Mailjet 200) |
| **Storage** | 40 GB total (R2 10 + B2 10 + Oracle 20) |
| **Database reads** | 25M+/day (D1) + 1B row reads/month (Turso) |
| **Edge requests** | 100,000 req/day (Workers) |
| **Queue messages** | 1M/month (CF Queues) + 10K commands/day (Upstash) |
| **Search** | Unlimited (Typesense) + 10K/month (Meilisearch) + 10K/month (Algolia) |
| **Frontend serving** | Unlimited (CF Pages) |
| **CI/CD** | Unlimited (Forgejo + Woodpecker on Oracle VM) |
| **Self-hosted compute** | 4 ARM cores, 24GB RAM, 200GB storage (Oracle Always Free) |

---

## Cloudflare Workers Deployed

| Worker | URL | Purpose |
|---|---|---|
| `tranc3-ai` | `tranc3-ai.luminous-aimastermind.workers.dev` | AI gateway, 13-provider rotation (incl. GitHub Models) |
| `tranc3-notifications` | `tranc3-notifications.luminous-aimastermind.workers.dev` | Email rotation |
| `tranc3-storage` | `tranc3-storage.luminous-aimastermind.workers.dev` | Object storage rotation |
| `tranc3-search` | `tranc3-search.luminous-aimastermind.workers.dev` | Search rotation |
| `tranc3-queue` | `tranc3-queue.luminous-aimastermind.workers.dev` | Task queue rotation |
| `infinity-void` | `infinity-void.luminous-aimastermind.workers.dev` | AES-GCM encrypted vault |
| `trancendos-api-gateway` | `trancendos-api-gateway.luminous-aimastermind.workers.dev` | API routing |
| `trancendos-frontend` | `trancendos.com` | React/Vite SPA (CF Pages) |

---

## Free Package Ecosystems & Libraries

All packages below are free forever (MIT / Apache 2.0 / BSD). None require payment.

### Python (PyPI) — AI/ML
| Package | Version | Use | License |
|---|---|---|---|
| `llama-cpp-python` | 0.3.x | Local GGUF inference (llama.cpp binding) | MIT |
| `chromadb` | 1.0.x | Self-hosted vector store (SQLite in dev) | Apache 2.0 |
| `peft` | 0.15.x | LoRA/QLoRA fine-tuning adapters | Apache 2.0 |
| `bitsandbytes` | 0.47.x | 4-bit/8-bit quantization (CUDA only) | MIT |
| `instructor` | 1.8.x | Structured LLM outputs with Pydantic | MIT |
| `sentence-transformers` | pinned | Embedding generation (already in stack) | Apache 2.0 |
| `hnswlib` | — | HNSW nearest-neighbour vector search | Apache 2.0 |

### JavaScript / Node.js (npm)
| Package | Use | CF Workers? |
|---|---|---|
| `@xenova/transformers` | Browser/edge transformer inference (ONNX) | Yes (WASM only) |
| `onnxruntime-web` | ONNX model execution in browser/Workers | Yes |
| `vectra` | In-memory vector DB for Node.js | Yes |
| `hnswlib-node` | HNSW vector indexing | No (native) |
| `wrangler` | Cloudflare Workers CLI | N/A (dev tool) |
| `miniflare` | Local CF Workers emulator | N/A (dev tool) |

### Rust (Cargo)
| Crate | Use | Notes |
|---|---|---|
| `candle` (HuggingFace) | Native Rust LLM inference | Apache 2.0, CUDA/Metal support |
| `tract` | ONNX inference | Production-proven, CPU-only |
| `ort` | Official ONNX Rust bindings | Apache 2.0 |
| `hnswlib-rs` | HNSW vector search | Apache 2.0 |
| `tantivy` | Full-text + vector search | MIT |

### Java/Kotlin (Maven/Gradle)
> **Honest note:** Do not do AI training on the JVM. Java is suitable for orchestration, API gateways, and business logic only. For inference, call Python/Rust microservices via HTTP.

| Library | Use | License |
|---|---|---|
| `onnxruntime` (Java) | Inference from ONNX models | Apache 2.0 |
| `djl` (Deep Java Library, Amazon) | Inference wrapper (calls native runtimes) | Apache 2.0 |

---

## Deploy Command

```bash
cd cloudflare
./deploy-all.sh secrets   # set API keys interactively
./deploy-all.sh all       # deploy all workers + frontend
```

Total monthly cost: **£0.00**
