# TRANC3 — Core AI Platform

[![Codecov](https://codecov.io/gh/Trancendos/Tranc3/branch/main/graph/badge.svg)](https://codecov.io/gh/Trancendos/Tranc3)
[![Ruff](https://img.shields.io/badge/linter-ruff-blue)](https://github.com/astral-sh/ruff)
[![All Contributors](https://img.shields.io/badge/all_contributors-1-orange.svg?style=flat-square)](#contributors)
[![Mergify](https://img.shields.io/endpoint.svg?url=https://dashboard.mergify.com/badges/Trancendos/Tranc3&style=flat)](https://mergify.com)

A self-hosted, zero-cost AI platform built from the ground up. Custom transformer model, autonomous agent orchestration, encrypted secrets vault, and a full observability stack — all running on your infrastructure with no paid external dependencies.

---

## What This Is

TRANC3 is a decoder-only transformer language model — the same architectural family as GPT — built from PyTorch primitives, combined with a production-ready platform that includes 29 self-hosted workers, an MCP tool registry with 45+ tools, and a comprehensive security framework.

The platform is designed to be **compassionate, capable, and honest**. The two included personality profiles are `tranc3-base` (empathetic companion) and `tranc3-builder` (technical assistant). More can be added as JSON files without touching any code.

**Core Principle**: Zero cost. No paid APIs. No third-party dependencies that incur costs. All services are self-hosted Python workers or open-source infrastructure components.

---

## Architecture

### AI Model
- **Model**: Decoder-only transformer with RoPE positional embeddings and SwiGLU activation
- **Tokenizer**: SentencePiece BPE, trained on your data, 32k vocabulary
- **Personality layer**: JSON profile system injected at inference time
- **Training**: AdamW, cosine LR schedule, gradient accumulation, mixed precision

| Size   | Parameters | Hardware       |
|--------|-----------|----------------|
| small  | ~10M      | CPU feasible   |
| medium | ~50M      | GPU recommended|
| large  | ~150M     | Slough-grade   |

### Platform Services
- **29 Python/FastAPI workers** replacing Cloudflare Workers
- **MCP tool registry** with 45+ tools across 5 Spark phases
- **Infinity Void** — AES-256-GCM encrypted secrets vault
- **Autonomous agent orchestration** with goal decomposition and reflection
- **Quantum-inspired routing** and **bio-neural consciousness** modules
- **Full observability**: Prometheus + Grafana + Loki + OpenTelemetry

### What This Replaces

| Cloudflare Service | Self-Hosted Replacement |
|---|---|
| Cloudflare Workers | 29 Python/FastAPI workers |
| Cloudflare D1 | SQLite (per-worker) |
| Cloudflare KV | In-memory rate limiting + SQLite |
| Cloudflare R2 | IPFS + local filesystem |
| Cloudflare Routing | Traefik reverse proxy |
| Cloudflare Analytics | Prometheus + Grafana + Loki |
| Cloudflare Secrets | HashiCorp Vault / Infinity Void |

---

## Quick Start

### Local Development

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install pre-commit hooks
pip install pre-commit && pre-commit install

# Start the backend
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# Start the frontend (separate terminal)
cd web && npm install && npm run dev

# Run the test suite
python -m pytest tests/ -q --tb=short
```

### Docker (Full Stack)

```bash
# Build and run everything
docker compose up -d

# Services: api (8000), web (3000), redis (6379),
#           prometheus (9090), grafana (3001), loki (3100)
```

### Fly.io (Production)

```bash
flyctl deploy --remote-only --app trancendos-backend
```

See [docs/DEPLOYMENT_RUNBOOK.md](docs/DEPLOYMENT_RUNBOOK.md) for the complete deployment guide.

---

## Step-by-Step: First Run

### Step 1 — Prepare training data
```bash
python scripts/prepare_data.py
```
Downloads EmpatheticDialogues and DailyDialog automatically.
To add your own data: place JSONL files in `data/raw/custom/`
Format: `{"turns": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}`

### Step 2 — Train the tokenizer
```bash
python scripts/train_tokenizer.py
```

### Step 3 — Train the model
```bash
# CPU / testing (small model)
python scripts/train.py --size small --max_steps 5000

# GPU (medium model, full training)
python scripts/train.py --size medium
```

### Step 4 — Chat
```bash
python scripts/chat.py --profile tranc3-base
python scripts/chat.py --profile tranc3-builder
```

---

## Project Structure

```
tranc3/
├── src/                          Core source code
│   ├── core/                     Transformer architecture, tokenizer, config
│   ├── personality/              Personality matrix + profile system
│   ├── mcp/                      MCP tool registry (45+ tools)
│   ├── workflow/                 Workflow builder + execution engine
│   ├── ai_gateway/               Multi-provider LLM routing
│   ├── security/                 Security framework
│   ├── observability/            Health, metrics, logging
│   ├── quantum/                  Quantum-inspired routing
│   ├── bio_neural/               Consciousness + neuromorphic modules
│   └── agents/                   Autonomous agent orchestration
├── workers/                      29 self-hosted FastAPI workers
│   ├── infinity-void/            Encrypted secrets vault
│   ├── api-gateway/              API gateway + rate limiting
│   ├── the-grid/                 Digital Grid compute mesh
│   └── ...                       26 additional workers
├── Dimensional/                  Shared utilities (bus, models, security)
├── web/                          React + Vite frontend
├── cloudflare/                   Cloudflare Workers (legacy fallback)
├── tests/                        Test suite (966 tests)
├── scripts/                      Training + utility scripts
├── deploy/                       Deployment configs (Prometheus, Grafana, OTel)
├── docker/                       Dockerfiles + nginx config
├── docs/                         Documentation
├── tranc3-bots/                  Bot integrations
├── Dockerfile                    Production Docker image
├── docker-compose.yml            Full-stack development
├── docker-compose.production.yml Production deployment
├── fly.toml                      Fly.io configuration
├── pyproject.toml                Python project config (ruff, bandit)
├── .pre-commit-config.yaml       Pre-commit hooks (ruff, bandit, semgrep, gitleaks)
└── .forgejo/workflows/           CI/CD pipelines
```

---

## Testing

```bash
# Full suite (966 tests)
python -m pytest tests/ -q --tb=short

# Quick smoke test
python -m pytest tests/test_smoke.py -v

# Security tests
python -m pytest tests/test_security.py -v

# With coverage
python -m pytest tests/ --cov=src --cov-report=html
```

---

## CI/CD Pipeline

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| CI | Push/PR | Smoke tests + lint + full suite |
| Security Scan | Push/PR + weekly | pip-audit, bandit, safety, ruff, semgrep, gitleaks |
| Dependency Audit | Weekly + PR | Python + Node vulnerability scanning |
| Nightly Tests | Daily 03:00 UTC | Full test sweep + lint + type check |
| Deploy Fly.io | Push to main | Backend + bots deployment |
| Deploy Self-Hosted | Push to main (workers/) | Worker image builds + deployment |

### Pre-commit Hooks

Ruff, Black, isort, Bandit, Semgrep, Gitleaks, detect-secrets, Safety, and Typos run on every commit.

---

## Security

- **Path traversal prevention** via `Dimensional/path_validation.py`
- **Log injection prevention** via `Dimensional/sanitize.py`
- **Safe error handling** via `Dimensional/error_handlers.py`
- **AES-256-GCM encryption** in Infinity Void with PBKDF2 key derivation
- **Zero-trust authentication** with JWT + MFA
- **80 justified nosec comments** (bandit suppressions with documented rationale)
- **0 npm vulnerabilities** across all workspaces

See [SECURITY.md](SECURITY.md) and [SECURITY-ASSESSMENT.md](SECURITY-ASSESSMENT.md) for details.

---

## Adding a Personality

Create a new JSON file in `src/personality/profiles/`:

```json
{
  "name": "tranc3-myagent",
  "version": "1.0.0",
  "system_prompt": "Your character definition here.",
  "temperature": 0.75,
  "top_k": 50,
  "top_p": 0.90,
  "repetition_penalty": 1.12,
  "max_new_tokens": 512,
  "tone": "warm",
  "domain_focus": "your-domain",
  "avatar_id": null
}
```

It will be available immediately — no restart, no retraining.

---

## Documentation

| Document | Description |
|----------|-------------|
| [Deployment Runbook](docs/DEPLOYMENT_RUNBOOK.md) | Full deployment guide |
| [Architecture Threat Model](ARCHITECTURE_THREAT_MODEL.md) | Security architecture |
| [CF Worker Migration Roadmap](CF_WORKER_MIGRATION_ROADMAP.md) | Cloudflare → self-hosted plan |
| [Security Assessment](SECURITY-ASSESSMENT.md) | Vulnerability analysis |
| [Project Pulse](PROJECT_PULSE.md) | Current status + metrics |

---

## Contributors

Thanks to all contributors who have helped build the Trancendos platform:

<!-- ALL-CONTRIBUTORS-LIST:START - Do not edit this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%">
        <a href="https://github.com/Trancendos">
          <img src="https://github.com/Trancendos.png" width="100px;" alt="Trancendos"/>
          <br /><sub><b>Trancendos</b></sub>
        </a>
        <br />
        💻 🎨 📖 🤔 🚇 🚧 📆 👀 🛡️
      </td>
    </tr>
  </tbody>
</table>
<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->
<!-- ALL-CONTRIBUTORS-LIST:END -->

To add yourself: comment `@all-contributors please add @username for code,doc` on any PR or issue.

---

## License

Proprietary. All rights reserved.
