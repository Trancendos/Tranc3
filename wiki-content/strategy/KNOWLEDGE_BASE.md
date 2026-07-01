# TRANC3 Knowledge Base
**FID: TRANC3-DOC-KB-001 | Version: 1.0.0**

---

## Error Code Reference

Every error in TRANC3 has a structured code, guidance, and self-healing action.

### Auth Errors

| Code | Title | HTTP | Guidance |
|------|-------|------|----------|
| TRANC3-AUTH-001 | Token Expired | 401 | Call `POST /auth/refresh` or re-authenticate via `POST /auth/token` |
| TRANC3-AUTH-002 | Invalid Token | 401 | Send token as `Authorization: Bearer <token>` header |
| TRANC3-AUTH-007 | Weak Password | 400 | Min 8 chars, 1 uppercase, 1 number |
| TRANC3-AUTH-008 | User Exists | 400 | Choose different username or sign in |

### Rate Limit Errors

| Code | Title | HTTP | Guidance |
|------|-------|------|----------|
| TRANC3-RATE-001 | Hourly Limit | 429 | Upgrade via `POST /billing/checkout?tier=pro` |
| TRANC3-RATE-002 | Daily Limit | 429 | Wait until midnight UTC or upgrade |

### Model Errors

| Code | Title | HTTP | Guidance |
|------|-------|------|----------|
| TRANC3-MODEL-001 | Model Not Loaded | 503 | Run `make download-model` then restart |
| TRANC3-MODEL-002 | Echo Mode | 200 | Run `python train.py` to get real weights |
| TRANC3-MODEL-004 | Language Unsupported | 400 | Call `GET /languages` for supported codes |

### Database Errors

| Code | Title | HTTP | Guidance |
|------|-------|------|----------|
| TRANC3-DB-001 | Connection Failed | 503 | Check `DATABASE_URL` in `.env`, run `make migrate` |
| TRANC3-DB-004 | Migration Needed | 503 | Run `alembic upgrade head` |

### Security Errors

| Code | Title | HTTP | Guidance |
|------|-------|------|----------|
| TRANC3-SEC-001 | Input Blocked | 400 | Remove script tags, SQL, or path traversal from message |
| TRANC3-SEC-003 | Integrity Alert | 500 | File tampering detected — contact admin, check `GET /admin/registry` |

---

## File Identity System (FID)

Every file has a unique File ID in the format: `TRANC3-{MODULE}-{NUMBER}`

### FID Modules

| Module Code | Description | Example FID |
|-------------|-------------|-------------|
| ENTRY | Entry point files | TRANC3-ENTRY-001 |
| CORE | Core AI engine | TRANC3-CORE-001 |
| BIO | Bio-neural modules | TRANC3-BIO-001 |
| QUANT | Quantum modules | TRANC3-QUANT-001 |
| EVOL | Evolution engine | TRANC3-EVOL-001 |
| DIST | Distributed/swarm | TRANC3-DIST-001 |
| HOLO | Holographic memory | TRANC3-HOLO-001 |
| SEC | Security | TRANC3-SEC-001 |
| AUTH | Authentication | TRANC3-AUTH-001 |
| DB | Database | TRANC3-DB-001 |
| BILL | Billing | TRANC3-BILL-001 |
| ANAL | Analytics | TRANC3-ANAL-001 |
| ADAP | Adaptive/foresight | TRANC3-ADAP-001 |
| OBS | Observability | TRANC3-OBS-001 |
| PERS | Personality | TRANC3-PERS-001 |
| COMP | Compliance | TRANC3-COMP-001 |
| NANO | Nanoservices | TRANC3-NANO-001 |
| RES | Research/2060 | TRANC3-RES-001 |
| REG | Registry | TRANC3-REG-001 |
| ERR | Error catalog | TRANC3-ERR-001 |
| VAL | Validation | TRANC3-VAL-001 |
| TEST | Tests | TRANC3-TEST-001 |

### Checking a File's Identity

```bash
# Via API
curl http://localhost:8000/admin/registry

# Via Python
from src.registry.file_registry import registry
record = registry.lookup("api.py")
print(record.fid, record.version, record.revision)

# Verify integrity of all files
result = registry.verify_all()
print(result["tampered"])  # Should be empty list
```

---

## Self-Healing Actions

| Action Name | Trigger | What it does |
|-------------|---------|--------------|
| `show_upgrade_prompt` | Rate limit exceeded | Returns upgrade URL in response |
| `attempt_model_reload` | Model not loaded | Tries to reload from MODEL_PATH |
| `use_sqlite_fallback` | DB connection failed | Switches to SQLite local DB |
| `run_migrations` | Migration needed | Runs `alembic upgrade head` |
| `use_env_feature_flags` | Redis unavailable | Reads flags from env vars |

---

## Circuit Breakers

| Circuit | Threshold | Recovery | Protects |
|---------|-----------|----------|---------|
| model_inference | 5 failures | 30s | Transformer forward pass |
| quantum_attention | 3 failures | 10s | Qiskit circuit execution |
| consciousness_phi | 5 failures | 15s | IIT Φ calculation |
| database_write | 3 failures | 60s | SQLAlchemy writes |
| redis_ops | 5 failures | 30s | Redis get/set |
| stripe_api | 3 failures | 120s | Stripe API calls |
| evolution_cycle | 10 failures | 60s | Genetic evolution loop |

---

## Loop Limits

| Loop Context | Max Iterations | Notes |
|-------------|----------------|-------|
| evolution_cycle | 1,000 | Per evolution run |
| consciousness_stream | 10,000 | Per stream simulation |
| swarm_consensus | 50 | Per consensus round |
| retry_loop | 10 | Per operation retry |
| db_retry | 3 | Per DB operation |
| quantum_circuit | 100 | Per circuit execution |

---

## IP Protection

TRANC3 implements multiple layers of intellectual property protection:

1. **File Integrity** — SHA-256 hash + HMAC signature per file, verified at startup
2. **Watermarking** — Zero-width Unicode characters embedded in every AI response
3. **Prompt Injection Detection** — 9 patterns blocked (jailbreak, DAN mode, etc.)
4. **Model Extraction Detection** — 5 patterns blocked (system prompt reveal, weight output, etc.)
5. **IP Rate Abuse** — >100 req/min from one IP triggers 1-hour block
6. **FID Headers** — Every file has a traceable identity header

---

## Quick Diagnostics

```bash
# Check all systems
curl http://localhost:8000/health

# Check feature flags
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/features

# Check file registry integrity
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/admin/registry

# Check circuit breaker status
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/admin/circuits

# Run full test suite
make test

# Check for syntax errors
python -m py_compile api.py auth.py
```
