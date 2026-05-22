# Tranc3 Research Findings — Phase 3 Comprehensive Discovery
## Zero-Cost Mandate · Frontier Technologies · Future-Proof Architecture

*Compiled: May 2025 | Status: Active Reference Document*

---

## 1. Zero-Cost Cloud Platform Tiers

### Oracle Cloud Infrastructure (OCI) — Best Free Tier

OCI provides the most generous free tier among major cloud providers, making it the primary cloud backend for Tranc3 under the Zero-Cost Mandate.

| Resource | Free Tier Allowance | Notes |
|----------|-------------------|-------|
| AMD Compute | 2 VMs (1/8 OCPU, 1GB RAM each) | Always-free, ARM Ampere A1 also available |
| ARM Compute | 4 A1 cores, 24GB RAM total | Can split into multiple VMs |
| Autonomous DB | 2 instances (20GB each) | Oracle Database or NoSQL |
| Object Storage | 20GB | Standard storage class |
| Outbound Data | 10TB/month | Extremely generous |
| Load Balancer | 1 flexible LB | 10Mbps bandwidth |
| Monitoring | 500M data points/month | Includes alarms, metrics |
| Functions | 2M invocations/month | Serverless compute |
| Vault | 20 keys, 150 secrets | Encryption key management |
| API Gateway | 1M requests/month | 25K requests/minute |

**Tranc3 Integration**: OCI Object Storage provider implemented in `shared_core/architecture/oci_storage.py`. The StorageFactory auto-detects OCI as the preferred cloud provider when available.

### Cloudflare — Edge Computing & CDN

Cloudflare's free tier provides essential edge infrastructure with zero cost, critical for the Tranc3 distributed architecture.

| Resource | Free Tier Allowance | Notes |
|----------|-------------------|-------|
| Workers | 100K requests/day | Serverless edge compute |
| R2 Storage | 10GB storage, 1M Class A ops, 10M Class B ops/month | S3-compatible, no egress fees |
| D1 Database | 5GB storage, 5M rows read, 100K rows written/day | SQLite at the edge |
| KV Namespace | 1GB storage, 100K reads, 1K writes/day | Global key-value store |
| Workers AI | 10K inferences/day | Free AI model inference |
| Pages | Unlimited sites, 500 builds/month | Static site hosting |
| CDN | Unlimited bandwidth | Global anycast network |
| SSL/TLS | Unlimited | Automatic certificate management |

**Tranc3 Integration**: Cloudflare R2 serves as the secondary cloud storage backend. Workers provide edge API endpoints. Workers AI offers free model inference as a zero-cost AI fallback.

### Google Cloud Platform (GCP) Always-Free

| Resource | Free Tier Allowance | Notes |
|----------|-------------------|-------|
| Compute Engine | 1 e2-micro (US regions) | 0.25 vCPU, 1GB RAM |
| Cloud Storage | 5GB | US multi-region |
| Firestore | 1GB storage, 50K reads, 20K writes/day | NoSQL database |
| BigQuery | 10GB storage, 1TB queries/month | Data warehouse |
| Cloud Functions | 2M invocations/month | Node.js, Python, Go |
| Pub/Sub | 10GB/month | Messaging |
| Cloud Run | 2M requests/month | Container compute |

### AWS Free Tier

| Resource | Free Tier Allowance | Notes |
|----------|-------------------|-------|
| Lambda | 1M requests/month, 400K GB-seconds | Serverless compute |
| DynamoDB | 25GB storage, 25 RCU/25 WCU | NoSQL database |
| S3 | 5GB storage | Standard storage (12 months) |
| CloudFront | 1TB transfer/month (12 months) | CDN |
| SQS | 1M requests/month | Message queue |
| CloudWatch | 10 custom metrics, 10 alarms | Monitoring |

**Note**: AWS free tier has 12-month limits on many services, making it less suitable for long-term zero-cost operations compared to OCI and Cloudflare.

### Azure Free Tier

| Resource | Free Tier Allowance | Notes |
|----------|-------------------|-------|
| App Service | 10 web apps (F1 tier) | 60 min CPU/day |
| Functions | 1M requests/month | Serverless compute |
| Cosmos DB | 1000 RU/s, 25GB | NoSQL database |
| Blob Storage | 5GB (12 months) | Hot block blobs |
| DevOps | 5 users, 1 parallel job | CI/CD pipeline |

**Note**: Like AWS, many Azure free services are 12-month introductory offers.

### Zero-Cost Cloud Strategy for Tranc3

The recommended zero-cost cloud stack prioritizes **always-free** services:

1. **Primary Compute**: OCI ARM VMs (4 cores, 24GB RAM — enough for the entire Tranc3 stack)
2. **Primary Storage**: OCI Object Storage (20GB) + Cloudflare R2 (10GB) = 30GB total
3. **Edge Compute**: Cloudflare Workers (100K req/day) for API gateway and auth
4. **Edge Database**: Cloudflare D1 (5GB) for lightweight state, KV for config
5. **CDN**: Cloudflare (unlimited bandwidth, global anycast)
6. **AI Inference**: Cloudflare Workers AI (10K inferences/day) as fallback
7. **Database**: OCI Autonomous DB (2 instances, 20GB each) for persistent storage

---

## 2. Zero-Cost AI Provider Stack

### Provider Matrix (Ranked by Cost/Quality)

| Provider | Cost | Models | Context Window | Rate Limit | Best For |
|----------|------|--------|---------------|------------|----------|
| **Ollama** | Free (local) | Llama 3.2, Qwen 2.5, DeepSeek R1 | 8K-65K | Unlimited | General purpose, offline, privacy |
| **Groq** | Free tier | Llama 3.3 70B, Mixtral 8x7B | 8K-32K | 30 req/min | Ultra-low latency (< 100ms) |
| **OpenRouter** | Free models | DeepSeek R1, Llama 3.3 70B, Qwen 2.5 72B | 8K-65K | 20 req/min | Model variety, reasoning |
| **HuggingFace** | Free tier | Llama 3.2 3B, etc. | 4K | Rate-limited | Niche models, experimentation |
| **DeepSeek** | $0.14/M input | deepseek-chat, deepseek-reasoner | 65K | 500 req/min | High-quality, near-zero cost |
| **Cloudflare Workers AI** | Free tier | Llama 2, Mistral, etc. | 4K-8K | 10K/day | Edge inference, zero-latency |

### Routing Chain Architecture

Tranc3 implements a **priority-based failover routing chain** for AI requests:

**Zero-Cost Full Stack** (recommended default):
```
Ollama (local) → Groq (free cloud) → OpenRouter (free models) → Offline (deterministic fallback)
```

**Zero-Cost Cloud Only** (no local hardware):
```
Groq → OpenRouter → HuggingFace → Offline
```

**Zero-Cost Reasoning** (optimized for complex tasks):
```
OpenRouter (deepseek-r1:free) → Groq → Offline
```

**Near-Zero High Quality** (~$0.01/1K requests):
```
DeepSeek API → Groq → OpenRouter → Offline
```

### Model Capability Matrix

**Reasoning Models** (for complex analysis, code generation, planning):
- DeepSeek R1 (free via OpenRouter, local via Ollama) — best reasoning model available free
- Llama 3.3 70B (free via Groq, OpenRouter) — strong general purpose with reasoning

**Code Generation Models**:
- DeepSeek R1 — excellent code understanding and generation
- Llama 3.3 70B — strong code completion
- Qwen 2.5 72B — multilingual code support

**Fast Inference Models** (for chat, simple tasks):
- Groq Llama 3.1 8B Instant — sub-50ms response time
- Ollama Llama 3.2 — unlimited local inference

**Large Context Models** (for document analysis, summarization):
- DeepSeek R1 (65K context) — free via OpenRouter
- Groq Mixtral 8x7B (32K context) — free tier
- Ollama DeepSeek R1 (65K context) — unlimited local

---

## 3. AI Agent Frameworks & Multi-Agent Orchestration

### Leading Open-Source Frameworks (2025)

#### LangGraph (by LangChain)
- **License**: MIT
- **Language**: Python
- **Key Feature**: Graph-based agent workflow with cycles, persistence, and human-in-the-loop
- **Best For**: Complex multi-step reasoning, stateful agent workflows
- **Zero-Cost**: Self-hosted, integrates with Ollama/Groq/OpenRouter
- **Tranc3 Alignment**: Natural fit for Tier 2/Tier 3 AI orchestration — graph-based routing maps to the pillar/hub architecture

#### CrewAI
- **License**: MIT
- **Language**: Python
- **Key Feature**: Role-based agent teams with structured delegation and tool use
- **Best For**: Collaborative AI tasks, content creation, research
- **Zero-Cost**: Self-hosted, provider-agnostic
- **Tranc3 Alignment**: Maps to the multi-agent tier system — each crew member can be a Tier 4 agent with specific capabilities

#### AutoGen (by Microsoft Research)
- **License**: MIT
- **Language**: Python
- **Key Feature**: Multi-agent conversation framework with code execution
- **Best For**: Code generation, data analysis, multi-perspective problem solving
- **Zero-Cost**: Self-hosted, works with local models
- **Tranc3 Alignment**: Natural fit for the Neural Bus protocol — agents communicate through structured conversations

#### OpenAI Swarm (Experimental)
- **License**: MIT
- **Language**: Python
- **Key Feature**: Minimalist multi-agent orchestration, lightweight
- **Best For**: Simple agent handoffs, prototype systems
- **Zero-Cost**: Self-hosted
- **Tranc3 Alignment**: Could serve as the lightweight Tier 5 bot orchestration layer

### Recommended Agent Architecture for Tranc3

```
Tier 1: The Sovereign (LangGraph orchestrator)
  └── Tier 2: Primes (CrewAI crews)
        ├── Cornelius (DevOps crew)
        ├── Doctor (Health/Diagnostics crew)
        └── Guardian (Security crew)
              └── Tier 3: Lead AIs (AutoGen agents)
                    └── Tier 4: Microservices (Swarm handoffs)
                          └── Tier 5: Bots/Nanoservices (Direct LLM calls)
```

**Implementation Strategy**:
1. Use LangGraph as the top-level orchestrator (graph-based workflow maps to pillar architecture)
2. Each Prime AI runs as a CrewAI crew with role-based agents
3. Tier 3 agents use AutoGen for multi-perspective analysis
4. Tier 4/5 use lightweight Swarm-style handoffs or direct provider calls
5. All tiers communicate through the Neural Bus protocol

---

## 4. Observability & Monitoring (Zero-Cost)

### Prometheus + Grafana Stack
- **Prometheus**: Time-series metrics collection — already integrated via `/metrics` endpoint
- **Grafana**: Visualization and dashboards — self-hosted, free
- **Alertmanager**: Alert routing and notification — self-hosted, free
- **Tranc3 Integration**: TelemetryMiddleware exposes Prometheus-format metrics at `/metrics`

### OpenTelemetry (Zero-Cost)
- **OTel SDK**: Distributed tracing, metrics, and logs — vendor-neutral standard
- **Jaeger**: Trace visualization — self-hosted, free
- **Tranc3 Integration**: TelemetryMiddleware propagates X-Trace-Id headers, can be extended to export OTel spans

### Health Monitoring
- **HeartbeatAggregator**: Ported from the-hive, provides real-time service health tracking
- **CircuitBreaker**: Already in shared_core, provides resilience against cascading failures
- **DefenseEngine**: Ported from the-citadel, provides firewall + incident tracking

### Log Aggregation
- **Loki**: Log aggregation by Grafana Labs — self-hosted, free, integrates with Grafana
- **Fluentd/Fluent Bit**: Log collection and forwarding — open source
- **Vector**: High-performance observability data pipeline — open source

---

## 5. CI/CD Zero-Cost Solutions

### Forgejo Actions (Recommended)
- **Forgejo**: Self-hosted Git platform (Gitea fork) with built-in CI/CD
- **Actions**: YAML-based workflows, compatible with GitHub Actions syntax
- **Runners**: Self-hosted runners on OCI free-tier VMs
- **Zero-Cost**: Entirely free, runs on own infrastructure

### GitHub Actions (Free Tier)
- **Public repos**: Unlimited minutes
- **Private repos**: 2,000 minutes/month (free tier)
- **Tranc3 Strategy**: Use GitHub Actions for public repo CI, Forgejo for private/internal

### Alternative CI/CD Platforms
| Platform | Free Tier | Notes |
|----------|-----------|-------|
| GitLab CI | 400 minutes/month | Shared runners, Docker-in-Docker |
| CircleCI | 6,000 minutes/month | 1 concurrent job |
| Codefresh | 1,200 minutes/month | Argo-based, Kubernetes-native |
| Woodpecker CI | Unlimited (self-hosted) | Drone fork, lightweight |

---

## 6. Edge Computing & CDN Solutions

### Cloudflare Workers (Primary Edge)
- 100K requests/day free
- Sub-millisecond cold start
- JavaScript/TypeScript/WASM runtime
- KV, D1, R2 integration at the edge
- Workers AI for edge inference

### Deno Deploy (Alternative Edge)
- 1M requests/month free
- TypeScript/JavaScript/WASM
- Global edge network
- Built-in KV database

### Fly.io (Container Edge)
- 3 shared-cpu-1x VMs free (256MB RAM each)
- 160GB outbound data/month
- Anycast global network
- Docker-based deployment

### Vercel (Frontend Edge)
- 100GB bandwidth/month free
- Serverless functions
- Edge runtime
- Next.js optimized

---

## 7. Security & Cryptography (Zero-Cost)

### Open-Source Security Tools
- **Trivy**: Container/image vulnerability scanning — free, CLI
- **Falco**: Runtime security monitoring — CNCF project
- **Open Policy Agent (OPA)**: Policy-as-code — free, CNCF graduated
- **Sigstore**: Code signing and verification — free, Linux Foundation
- **Cilium**: eBPF-based networking, security, observability — CNCF project

### Tranc3 Security Stack
- **AuditLedger**: SHA-256 chain hashing, HMAC signing — already implemented
- **VaultSecretLoader**: Memory-mapped secrets with RAM zeroization — already implemented
- **DefenseEngine**: Firewall rules, incident management, threat assessment — ported from the-citadel
- **AdaptiveScanner**: Automated security scanning — already implemented
- **AuthMiddleware**: JWT + API Key enforcement — implemented in this session
- **RateLimitMiddleware**: IAM-tier-aware adaptive rate limiting — implemented in this session

---

## 8. Frontend & Dashboard Technologies (Zero-Cost)

### React + TypeScript (Current Stack)
- Tranc3 already uses React with TypeScript
- Vite for fast development builds
- TailwindCSS for styling

### Recommended Enhancements
- **React Query (TanStack Query)**: Server state management — free, open source
- **Zustand**: Lightweight client state management — free, open source
- **Recharts/D3**: Data visualization — free, open source
- **React Flow**: Node-based visual editor — free, open source
- **Storybook**: Component development and documentation — free, open source

---

## 9. Database & Storage Strategy (Zero-Cost)

### Always-Free Database Options
| Database | Free Tier | Best For |
|----------|-----------|----------|
| OCI Autonomous DB | 2 x 20GB | Relational data, SQL |
| Cloudflare D1 | 5GB + 5M reads/day | Edge SQLite, lightweight |
| GCP Firestore | 1GB + 50K reads/day | NoSQL, real-time sync |
| AWS DynamoDB | 25GB + 25 RCU/WCU | NoSQL, key-value |
| Supabase | 500MB + 50K MAU | PostgreSQL, real-time |
| Turso | 9GB + 1B row reads/month | LibSQL, edge SQLite |

### Tranc3 Storage Strategy
1. **Local/TrueNAS**: Primary storage (SSD/HDD, unlimited)
2. **OCI Object Storage**: Cloud backup (20GB free)
3. **Cloudflare R2**: Edge-accessible storage (10GB free, no egress fees)
4. **Cloudflare D1**: Lightweight edge state (5GB free)
5. **Hybrid Provider**: Auto-sync between local and cloud (implemented in storage_factory.py)

---

## 10. Emerging Technologies & Future-Proofing

### WebAssembly (WASM)
- **WASI**: WebAssembly System Interface — portable binary format
- **Component Model**: Composable WASM modules — future of serverless
- **Tranc3 Opportunity**: Tier 5 bots as WASM components — ultra-lightweight, sandboxed, portable
- **Spin (Fermyon)**: WASM application framework — free tier available

### eBPF (Extended Berkeley Packet Filter)
- Kernel-level observability and networking without kernel modules
- Cilium, Falco, Pixie use eBPF
- **Tranc3 Opportunity**: DefenseEngine could use eBPF for real-time network security monitoring

### Local-First Software
- **CRDTs**: Conflict-free Replicated Data Types — offline-first sync
- **Automerge**: JSON CRDT library — free, open source
- **Tranc3 Opportunity**: HybridStorageProvider sync could use CRDTs for conflict resolution

### AI Model Compression
- **Quantization**: GGUF/GGML formats for running large models on consumer hardware
- **LoRA/QLoRA**: Low-rank adaptation for fine-tuning with minimal resources
- **Distillation**: Training smaller models from larger ones
- **Tranc3 Opportunity**: Ollama already supports quantized GGUF models — deploy compressed models on local hardware

### Protocol Buffers & gRPC
- More efficient than REST/JSON for internal service communication
- **Tranc3 Opportunity**: Neural Bus protocol could use gRPC for Tier 3+ agent communication

### WebTransport / HTTP/3
- Bidirectional streaming with QUIC
- Lower latency than WebSocket
- **Tranc3 Opportunity**: Real-time dashboard updates, Neural Bus streaming

---

## 11. Platform-Specific Research Notes

### Microsoft / Azure
- Azure Functions free tier: 1M executions/month
- Azure DevOps: 5 users free, 1 parallel job
- GitHub Actions: 2,000 min/month (private), unlimited (public)
- Semantic Kernel: Microsoft's AI orchestration SDK (C#, Python, Java)

### Google / GCP
- Vertex AI: Free trial credits, not always-free
- Colab: Free GPU runtime for ML experimentation
- Flutter/Dart: Cross-platform app development — free
- Android: Largest mobile platform — free SDK

### Samsung / Tizen
- Tizen: Open-source OS for IoT, TV, wearables
- SmartThings: IoT platform with developer SDK
- **Tranc3 Opportunity**: Tizen app for dashboard on Samsung TVs

### Apple / Swift
- Swift Open Source: Server-side Swift with Vapor framework
- CoreML: On-device ML inference
- **Tranc3 Opportunity**: iOS/macOS dashboard app with CoreML for local AI

### ChatGPT / OpenAI
- GPT-4o mini: Cheapest model, $0.15/M input
- Assistants API: Persistent AI agents with tools
- **Tranc3 Integration**: OpenRouter provides GPT-4o-mini free tier access

### Perplexity
- API available for search-augmented generation
- sonar model: Real-time web search + synthesis
- **Tranc3 Integration**: Could serve as the Knowledge Pillar's search backbone

### HuggingFace
- Serverless Inference API: Free tier for many models
- Transformers library: Open-source ML framework
- Datasets: Free dataset hosting and discovery
- Spaces: Free ML demo hosting (Gradio/Streamlit)

### OpenRouter
- 28+ free models including DeepSeek R1, Llama 3.3 70B, Qwen 2.5 72B
- Unified API for 200+ models
- Free tier: 20 requests/minute for free models
- **Tranc3 Integration**: Primary free cloud AI provider

### Groq
- LPU (Language Processing Unit) inference: sub-100ms latency
- Free tier: 30 requests/minute, 14,400/day
- Models: Llama 3.3 70B, Mixtral 8x7B, Gemma 2 9B
- **Tranc3 Integration**: Implemented as GroqProvider, second in routing chain

### DeepSeek
- DeepSeek R1: Open-source reasoning model rivaling GPT-4
- API pricing: $0.14/M input (deepseek-chat), $0.55/M input (deepseek-reasoner)
- OpenRouter free tier provides deepseek/deepseek-r1:free
- **Tranc3 Integration**: Implemented as DeepSeekProvider, primary near-zero-cost option

### Qwen (Alibaba)
- Qwen 2.5 72B: Available free via OpenRouter
- Multilingual capabilities (especially Asian languages)
- Various model sizes (0.5B to 72B)

### Maven / Gradle
- Maven: Java build automation — free, Apache License
- Gradle: Build automation with Kotlin DSL — free, Apache License
- **Tranc3 Note**: Python-based stack uses pip/poetry, not directly relevant

### Node.js
- Server-side JavaScript runtime — free, MIT License
- npm: Largest package registry — free for open source
- **Tranc3 Integration**: Used for Cloudflare Workers (TypeScript/JavaScript edge compute)

### Bitbucket / GitLab
- Bitbucket: Free tier for small teams (5 users), CI/CD pipelines
- GitLab: Free tier with CI/CD, container registry, monitoring
- **Tranc3 Note**: Forgejo is preferred for self-hosted, GitHub for public repos

---

## 12. Zero-Cost Mandate Compliance Summary

### Infrastructure ($0/month)
- **Compute**: OCI ARM VMs (4 cores, 24GB RAM) ✓
- **Storage**: OCI (20GB) + Cloudflare R2 (10GB) + Local NAS ✓
- **CDN**: Cloudflare (unlimited) ✓
- **Edge Compute**: Cloudflare Workers (100K req/day) ✓
- **Database**: OCI Autonomous DB + Cloudflare D1 ✓

### AI/ML ($0/month with free tiers)
- **Primary AI**: Ollama (local, unlimited) ✓
- **Cloud AI**: Groq (30 req/min) + OpenRouter (20 req/min) ✓
- **Reasoning**: DeepSeek R1 via OpenRouter (free) ✓
- **Edge AI**: Cloudflare Workers AI (10K inferences/day) ✓

### DevOps ($0/month)
- **CI/CD**: Forgejo Actions (self-hosted) ✓
- **Monitoring**: Prometheus + Grafana (self-hosted) ✓
- **Security**: Trivy + OPA (self-hosted, open source) ✓
- **Logging**: Loki + Fluent Bit (self-hosted) ✓

### Total Monthly Cost: $0.00

---

*This document is a living reference. Updates should be made as new zero-cost services become available and as the Tranc3 architecture evolves.*
