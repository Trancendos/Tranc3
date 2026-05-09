# TRANC3 — AI Platform

Multi-personality AI assistant with LLM routing, conversation persistence, and production-grade infrastructure.

## Current Status

**This project is in active development.** It is not yet production-ready, but significant progress has been made. Here is an honest assessment:

| Component | Status | Notes |
|-----------|--------|-------|
| Production API | ✅ Working | `api_production.py` with LLM routing, auth, DB persistence |
| LLM Router | ✅ Working | Multi-provider: Local → HuggingFace → Groq → OpenAI → Fallback |
| Authentication | ✅ Working | JWT with DB-backed user management |
| Database Schema | ✅ Working | Cross-dialect (PostgreSQL + SQLite), Alembic migrations |
| Conversation Persistence | ✅ Working | Full CRUD for conversations and messages |
| Personality System | ✅ Working | 6 personalities with tailored system prompts |
| Rate Limiting | ✅ Working | Token bucket with Redis + in-memory fallback |
| Structured Logging | ✅ Working | JSON or console format, per-request timing |
| Docker Deployment | ✅ Working | Dockerfile + docker-compose with PostgreSQL, Redis, observability |
| Startup Validation | ✅ Working | Honest health checks that report degraded/healthy per subsystem |
| Local Tranc3 Model | ⚠️ Bootstrap | Custom transformer exists but is not trained; falls back to API providers |
| MCP Integration | ⚠️ Stub | Model Context Protocol server skeleton exists, not wired end-to-end |
| Vector Store | ⚠️ Stub | ChromaDB referenced but not integrated into the API |
| Quantum Module | ❌ Not functional | Quantum computing module is conceptual/demonstration code |
| Billing/Stripe | ❌ Not integrated | Stripe keys in env but no payment flow |
| Frontend | ⚠️ Separate repo | Web UI exists but is not part of this backend repo |

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────┐
│   Frontend   │────▶│           TRANC3 Production API          │
│  (React)     │     │         (api_production.py)              │
└─────────────┘     │                                          │
                     │  ┌──────────┐  ┌──────────┐  ┌───────┐ │
                     │  │LLM Router│  │   Auth   │  │ Rate  │ │
                     │  │          │  │(JWT+DB)  │  │Limit  │ │
                     │  │ Local ──▶│  │          │  │       │ │
                     │  │ HF ────▶│  └──────────┘  └───────┘ │
                     │  │ Groq ──▶│                              │
                     │  │ OpenAI ▶│  ┌──────────────────────┐  │
                     │  │Fallback▶│  │  Personality Matrix   │  │
                     │  └──────────┘  │  (6 AI personalities) │  │
                     │                └──────────────────────┘  │
                     │                                          │
                     │  ┌──────────────────────────────────────┐│
                     │  │        Database (PostgreSQL/SQLite)  ││
                     │  │  Users · Conversations · Messages    ││
                     │  │  Feedback · API Keys · Metrics       ││
                     │  └──────────────────────────────────────┘│
                     └──────────────────────────────────────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/Trancendos/Tranc3.git
cd Tranc3
git checkout production-readiness-impl

# Configure
cp .env.example .env
# Set at minimum: SECRET_KEY, HF_API_KEY

# Install and run
pip install -r requirements.txt
uvicorn api_production:app --reload

# Test
curl http://localhost:8000/health
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for full production deployment instructions.

## API Endpoints

### Authentication
- `POST /auth/register` — Create account (username, email, password)
- `POST /auth/token` — Login, get JWT
- `POST /auth/refresh` — Refresh token

### Chat
- `POST /chat` — Send message, get AI response (routed through LLM router)
- `WebSocket /ws/chat` — Streaming chat

### Conversations
- `GET /conversations` — List user's conversations
- `GET /conversations/{id}` — Get conversation with messages
- `DELETE /conversations/{id}` — Delete conversation

### System
- `GET /health` — Basic liveness check
- `GET /health/detailed` — Per-subsystem health status
- `GET /ready` — Readiness check (all critical deps up)
- `GET /metrics` — Request counts, cache stats, provider usage
- `GET /inference/providers` — Available LLM providers and their status

### Info
- `GET /personalities` — List available AI personalities
- `GET /languages` — Supported languages
- `POST /feedback` — Submit feedback on a response

## Personalities

| Name | Description |
|------|-------------|
| tranc3-base | Balanced, intelligent general-purpose assistant |
| dorris-fontaine | Financial specialist — regulation-aware analysis |
| cornelius-macintyre | Orchestration specialist — multi-system coordination |
| the-guardian | Cybersecurity specialist — threat identification |
| vesper-nightingale | Healthcare advisor — evidence-based guidance |
| atlas-meridian | Infrastructure specialist — resilient system architecture |

## LLM Provider Priority

The router tries providers in order, falling back automatically:

1. **Local Tranc3** — Custom model (if trained weights available)
2. **HuggingFace** — Free tier inference API
3. **Groq** — Free tier, fast inference
4. **OpenAI** — Paid, highest quality
5. **Bootstrap Fallback** — Honest message explaining no provider is configured

## Configuration

All configuration is via environment variables. See [.env.example](.env.example) for the full list.

Key variables:
- `SECRET_KEY` — **Required.** JWT signing key.
- `DATABASE_URL` — PostgreSQL or SQLite connection string.
- `HF_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY` — LLM provider keys.
- `REDIS_URL` — For distributed rate limiting and caching.
- `LOG_LEVEL` — DEBUG, INFO, WARNING, ERROR.
- `LOG_FORMAT` — `console` (human-readable) or `json` (structured).

## Testing

```bash
# Run all production readiness tests (59 tests)
python -m pytest tests/test_production_api.py -v

# Run specific test classes
python -m pytest tests/test_production_api.py::TestLLMRouter -v
python -m pytest tests/test_production_api.py::TestRateLimiter -v
python -m pytest tests/test_production_api.py::TestStructuredLogging -v
```

## Project Structure

```
Tranc3/
├── api_production.py          # Production FastAPI app (v3.0.0)
├── api.py                     # Legacy echo-mode API (deprecated)
├── auth.py                    # Authentication (JWT, UserManager)
├── src/
│   ├── core/
│   │   ├── startup.py         # Startup validator (honest health checks)
│   │   ├── logging_config.py  # Structured JSON/console logging
│   │   └── __init__.py        # Lazy imports (avoids torch at import time)
│   ├── database/
│   │   ├── schema.py          # Cross-dialect DB schema (PostgreSQL + SQLite)
│   │   └── deps.py            # FastAPI DB session dependency
│   ├── inference/
│   │   └── llm_router.py      # Multi-provider LLM router with fallback
│   ├── middleware/
│   │   └── rate_limit.py      # Token bucket rate limiting (Redis + in-memory)
│   ├── auth/
│   │   └── db_user_manager.py # DB-backed user management
│   └── personality/
│       └── matrix.py          # Personality system
├── migrations/
│   └── versions/
│       └── 002_complete.py    # Migration for all missing tables
├── docker/
│   ├── Dockerfile.api         # Production API Docker image
│   └── Dockerfile.web         # Frontend Docker image
├── docker-compose.yml         # Full stack deployment
├── tests/
│   └── test_production_api.py # 59 tests covering all new code
├── .env.example               # Environment variable reference
└── DEPLOYMENT.md              # Deployment runbook
```

## What's Not Ready Yet

Being honest about what still needs work:

- **Local model training** — The custom Tranc3 transformer architecture exists but has no trained weights. The LLM router correctly falls back to API providers.
- **MCP (Model Context Protocol)** — Server skeleton exists but is not wired into the API pipeline.
- **Vector store / RAG** — ChromaDB is referenced but not integrated. No retrieval-augmented generation pipeline.
- **Quantum computing module** — Conceptual/demonstration code only. Not used in the API.
- **Billing** — Stripe environment variables exist but no payment flow is implemented.
- **Load testing** — No load tests have been run. Performance under concurrent traffic is unknown.
- **End-to-end tests** — Unit tests cover individual components but there are no full integration tests with a running server.

## License

See [LICENSE](LICENSE) for details.
