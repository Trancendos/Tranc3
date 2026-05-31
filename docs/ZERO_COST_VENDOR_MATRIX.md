# Zero-Cost Vendor & Tool Matrix (Trancendos Fortiere)

**Policy:** Production on **The Citadel** is self-hosted first. Cloud free tiers are **optional overflow** only. Anything with expiring credits or mandatory cards is **conditional**, not guaranteed $0.

Machine-readable registry: `config/zero_cost/providers.yaml`  
Audit: `python scripts/zero_cost_audit.py`

---

## How to read this document

| Verdict | Meaning |
|---------|---------|
| **Approved** | Stays $0 indefinitely at Tranc3 scale when self-hosted or OSS |
| **Conditional** | Can be $0 within caps; card/credits/idle-pause risks |
| **Avoid** | No durable free tier for our use case |

---

## Cloud hyperscalers

### Amazon Web Services (AWS)

| Offering | Limits (typical 2026) | Tranc3 use | Verdict |
|----------|----------------------|------------|---------|
| **Always Free** — Lambda | 1M requests/mo, 400K GB-s | Burst workers, not core | Conditional |
| **Always Free** — DynamoDB | 25 GB, 25 WCU/RCU | Optional edge cache | Conditional |
| **Always Free** — SNS / SQS | 1M/mo each | Event fan-out backup | Conditional |
| **Always Free** — Cognito | 50K MAU | Only if not using Infinity auth | Conditional |
| **$200 signup credit** | 30 days / new accounts | Experiments only | Avoid (expires) |
| **EC2 12-month** | 750 h/mo t2/t3.micro | Legacy; prefer Citadel | Avoid (expires) |

**Tranc3 default:** No AWS dependency in `docker-compose.production.yml`. Use Citadel + SQLite + Traefik.

### Google Cloud (GCP)

| Offering | Limits | Tranc3 use | Verdict |
|----------|--------|------------|---------|
| **Always Free** — Cloud Run | 2M requests/mo | Optional burst API | Conditional |
| **Always Free** — e2-micro | 1 VM/mo (US regions) | Dev sandboxes | Conditional |
| **Always Free** — BigQuery | 1 TiB queries/mo | Analytics experiments | Conditional |
| **$300 trial** | 90 days | PoC only | Avoid (expires) |

### Microsoft Azure

| Offering | Limits | Tranc3 use | Verdict |
|----------|--------|------------|---------|
| **Always Free** — Functions | 1M executions/mo | Not core | Conditional |
| **$200 credit** | 30 days new accounts | PoC only | Avoid (expires) |
| **12-month free** | B1s 750 h/mo etc. | Expires year 1 | Avoid (expires) |

### Oracle Cloud

| Offering | Limits | Tranc3 use | Verdict |
|----------|--------|------------|---------|
| **Always Free ARM** | Up to 4 OCPU / 24 GB (capacity-limited) | Optional Citadel host | Conditional |
| **Always Free storage** | 200 GB block + 20 GB object | Backups | Conditional |
| **$300 trial** | 30 days | PoC | Avoid (expires) |

**Note:** `infrastructure/oracle-cloud/` exists for optional IaC; not required for zero-cost Citadel.

### Cloudflare (legacy path)

| Offering | Limits | Tranc3 use | Verdict |
|----------|--------|------------|---------|
| Workers / KV / D1 | Daily caps (e.g. 100K req/day) | Being replaced by self-hosted workers | Conditional (decommissioning) |
| R2 | 10 GB + request tiers | Optional; IPFS preferred | Conditional |

---

## DevOps, security, dependencies

### HashiCorp

| Product | Free? | Tranc3 use | Verdict |
|---------|-------|------------|---------|
| **Terraform CLI** | BSL — internal use OK | `infrastructure/opentofu` preferred (OpenTofu) | Approved (OpenTofu) |
| **Vault Community** | BSL — self-host | `docker-compose.production.yml` Vault | Approved (self-host) |
| **HCP Terraform** | 500 resources free | Optional remote state | Conditional |

### CVE & dependency scanning (all OSS / free tiers)

| Tool | Cost | Wired in repo |
|------|------|----------------|
| **Trivy** | Apache 2.0 | Add to CI alongside Semgrep |
| **Grype / Syft** | Apache 2.0 | Container SBOM |
| **OSV-Scanner** | Free | `pip-audit`, OSV DB |
| **pip-audit / bandit / safety** | Free | `.forgejo/workflows/security-scan.yml` |
| **Semgrep** | OSS CLI | pre-commit + CI |
| **Gitleaks** | MIT | pre-commit |
| **Dependabot** | Free GitHub | Public mirrors |
| **Renovate** | Free self-hosted CLI | Forgejo cron optional |

### Package ecosystems & languages

| Ecosystem | Registry / tool | Cost | Tranc3 |
|-----------|-----------------|------|--------|
| **Python** | PyPI, pip, ruff, pytest | Free | Primary stack |
| **Node.js** | npm, node LTS | Free | `web/`, legacy CF workers |
| **Rust** | crates.io, cargo | Free | nanoservices, Sig |
| **JVM** | Maven Central, Gradle | Free publish/read | Optional integrations |
| **Go** | proxy.golang.org | Free | Workers if added |
| **Ruby** | RubyGems | Free | Rare |
| **PHP** | Packagist | Free | Rare |
| **.NET** | NuGet | Free | Rare |

**Methodology:** Prefer pinned deps (`requirements.txt`, `requirements-worker.txt`), `pip-audit` in CI, SBOM via `make sbom` (Syft).

---

## Creative, 3D, design

| Vendor | Free offering | Tranc3 entity | Verdict |
|--------|---------------|---------------|---------|
| **Blender** | Full GPL app | TranceFlow, `blender-worker` :8050 | **Approved** |
| **Penpot** | Self-hosted MPL | Fabulousa compose service | **Approved** |
| **FFmpeg** | LGPL CLI | TateKing `ffmpeg-worker` :8052 | **Approved** |
| **TripoSR** | OSS model + worker | Sashas Photo Studio :8051 | **Approved** |
| **Adobe Creative Cloud** | Express, Bridge, ~25 Firefly credits/mo | Marketing only | Conditional |
| **Autodesk Fusion** | Personal non-commercial cap | Hobby CAD only | Conditional |
| **Creative Fabrica 3D** | Trial / paid All Access | Not production | **Avoid** |

Example 3D generator sites (Creative Fabrica, Meshy, etc.): treat as **research / trial**; production assets must come from **Blender + self-hosted** pipeline.

---

## AI platforms & directories

| Vendor | Free tier | Tranc3 tier | Verdict |
|--------|-----------|-------------|---------|
| **Ollama** | Unlimited local | AI Gateway tier 1 | **Approved** |
| **OpenRouter `:free` models** | ~50 req/day (unfunded) | Tier 3 fallback | Conditional |
| **Hugging Face Inference** | ~$0.10/mo credits | Tier 2 | Conditional |
| **There's An AI For That** | Browse / list | Think Tank research | Approved (directory) |
| **Futurepedia / Product Hunt** | Browse | Research | Approved (directory) |

**Not used at scale:** Closed APIs without free caps (GPT-4 paid, etc.) unless user supplies keys via The Void.

---

## Windows / ops utilities

| Tool | Cost | Use |
|------|------|-----|
| **Scoop** | MIT | Windows dev installs (The Lab) |
| **Ansible Core** | GPL | `make ansible-health` on Citadel |
| **Docker Engine** | Free (Moby) | Citadel runtime |
| **Forgejo** | OSS | The Workshop CI |

---

## Tranc3-approved production stack (true $0 core)

```text
The Citadel (Docker Compose)
├── Traefik, Vault, Prometheus, Grafana, Loki
├── 38+ FastAPI workers (SQLite per worker)
├── Infinity-Admin + shared entity_overrides DB
├── Swarm coordinator :8053 (manifest polling)
├── Ollama (local inference)
├── IPFS, Qdrant, Penpot, Forgejo (Workshop)
└── Security: Semgrep, bandit, pip-audit, gitleaks (CI)
```

---

## Implementation map (this repo)

| Capability | Path |
|------------|------|
| Production deploy | `deploy/citadel/deploy-production.sh` |
| Entity overrides | `ENTITY_OVERRIDES_DB`, `x-worker-platform` in compose |
| Health + entity metadata | `src/entities/health_metadata.py`, all `/health` |
| Proactive automation | `scripts/swarm_runner.py`, `workers/swarm-coordinator-service/` |
| Ansible probe | `deploy/ansible/playbooks/health-probe.yml` |
| Zero-cost registry | `config/zero_cost/providers.yaml`, `src/zero_cost/` |
| Security CI | `.forgejo/workflows/security-scan.yml`, `proactive-health.yml` |

---

## Research methodology

1. **Discover** — Official vendor free-tier / pricing pages and 2025–2026 guides.  
2. **Classify** — Always-free vs expiring credits vs card-required.  
3. **Map** — Tie each service to a Trancendos entity (see `PLATFORM_ENTITIES.md`).  
4. **Implement** — Only **Approved** items in default production path; **Conditional** behind feature flags / env.  
5. **Audit** — `scripts/zero_cost_audit.py` + Forgejo security workflow.

*Last updated: 2026-05-31. Re-verify vendor pages before relying on caps in production.*
