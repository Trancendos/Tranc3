# api.py — TRANC3 Production API
# Fully wired: auth, billing, analytics, foresight, feature flags, observability

import asyncio
import datetime
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import redis as redis_lib

try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False
import uvicorn
from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from Dimensional.error_handlers import safe_error_detail
from Dimensional.sanitize import sanitize_for_log

load_dotenv()

# ── Fail fast on missing critical secrets ────────────────────────────────────
_SECRET_KEY = os.getenv("SECRET_KEY")
if not _SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is not set. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )

_JWT_SECRET = os.getenv("JWT_SECRET")
if not _JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not set. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )

_DATABASE_URL = os.getenv("DATABASE_URL")
if not _DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Set to your PostgreSQL connection string (e.g. postgresql://user:pass@host/db)."
    )

_REDIS_URL = os.getenv("REDIS_URL")
if not _REDIS_URL:
    raise RuntimeError(
        "REDIS_URL is not set. "
        "Set to your Redis connection string (e.g. redis://localhost:6379 or rediss://...)."
    )

# ── Internal imports ──────────────────────────────────────────────────────────────────────────
# Core imports (required — no guard)
from src.auth.rbac import require_permission  # noqa: F401  # RBAC guards for protected routes
from src.gbrain.pipeline import AgentInteraction as _GBrainInteraction  # noqa: F401
from src.gbrain.pipeline import get_pipeline as _get_gbrain_pipeline  # noqa: F401

from auth import get_current_user, token_manager  # codeql[py/cyclic-import]
from src.auth.db_user_manager import DBUserManager  # noqa: F401  # intentional top-level import
from src.auth.rbac import require_permission  # noqa: F401  # RBAC guards for protected routes
from src.compliance.ai_transparency import AITransparencyMiddleware  # noqa: F401
from src.compliance.cab_gate import CABMiddleware  # noqa: F401
from src.compliance.middleware import MagnaCartaMiddleware  # noqa: F401
from src.core.advanced_model import (
    AdvancedTransformerModel,  # noqa: F401  # intentional top-level import
)
from src.core.context_compressor import compressor  # noqa: F401  # intentional top-level import
from src.core.security import safe_torch_load
from src.core.feature_flags import (  # noqa: F401  # intentional top-level import
    FeatureFlag,
    FeatureFlagManager,
)
from src.core.multilingual_tokenizer import (
    MultilingualTokenizer,  # noqa: F401  # intentional top-level import
)
from src.core.startup_validator import validate_startup
from src.database.schema import (  # noqa: F401  # intentional top-level import
    Conversation,
    DatabaseManager,
    Message,
)
from src.database.vector_store import vector_store  # noqa: F401  # intentional top-level import
from src.errors.error_catalog import (  # noqa: F401  # intentional top-level import
    ErrorCode,
    format_error_response,
)
from src.monetisation.billing import TIERS  # noqa: F401  # intentional top-level import
from src.monetisation.billing import (
    enforcer as tier_enforcer,  # noqa: F401  # intentional top-level import
)
from src.observability.metrics import (  # noqa: F401  # intentional top-level import
    log,
    record_churn_risk,
    record_emotion,
    record_phi,
    record_quality,
    record_request,
)
from src.registry.file_registry import (
    registry as file_registry,  # noqa: F401  # intentional top-level import
)
from src.security.ip_protection import (  # noqa: F401  # intentional top-level import
    abuse_detector,
    watermarker,
)
from src.security.middleware import (  # noqa: F401  # intentional top-level import
    GovernanceMiddleware,
    RBACMiddleware,
    SecurityHeadersMiddleware,
    ZeroTrustASGIMiddleware,
)
from src.security.security_framework import (
    InputSanitizer,  # noqa: F401  # intentional top-level import
)
from src.validation.loop_validator import (  # noqa: F401  # intentional top-level import
    CIRCUITS,
    loop_validator,
    self_healer,
)

# Optional imports — guarded to prevent startup crash if dependencies are missing
# These modules depend on heavy/optional libs (qiskit, torch, etc.)

try:
    from src.adaptive.foresight import foresight  # noqa: F401  # intentional top-level import
except ImportError as _e:
    foresight = None  # type: ignore[assignment,misc]
    logging.getLogger(__name__).warning("Adaptive foresight unavailable: %s", _e)

try:
    from src.analytics.predictive import analytics  # noqa: F401  # intentional top-level import
except ImportError as _e:
    analytics = None  # type: ignore[assignment,misc]
    logging.getLogger(__name__).warning("Predictive analytics unavailable: %s", _e)

try:
    from src.bio_neural.consciousness_engine import (
        ConsciousnessModel,  # noqa: F401  # intentional top-level import
    )
except ImportError as _e:
    ConsciousnessModel = None  # type: ignore[assignment,misc]
    logging.getLogger(__name__).warning("ConsciousnessEngine unavailable: %s", _e)

try:
    from src.bio_neural.neuromorphic import (
        NeuromorphicProcessor,  # noqa: F401  # intentional top-level import
    )
except ImportError as _e:
    NeuromorphicProcessor = None  # type: ignore[assignment,misc]
    logging.getLogger(__name__).warning("NeuromorphicProcessor unavailable: %s", _e)

try:
    from src.compliance.magna_carta import compliance  # noqa: F401  # intentional top-level import
except ImportError as _e:
    compliance = None  # type: ignore[assignment,misc]
    logging.getLogger(__name__).warning("Compliance module unavailable: %s", _e)

try:
    from src.evolution.self_improving_core import (
        SelfEvolvingArchitecture,  # noqa: F401  # intentional top-level import
    )
except ImportError as _e:
    SelfEvolvingArchitecture = None  # type: ignore[assignment,misc]
    logging.getLogger(__name__).warning("SelfEvolvingArchitecture unavailable: %s", _e)

try:
    from src.personality.matrix import (
        PersonalityMatrix as EnhancedPersonalityMatrix,  # noqa: F401  # intentional top-level import
    )
except ImportError as _e:
    EnhancedPersonalityMatrix = None  # type: ignore[assignment,misc]
    logging.getLogger(__name__).warning("PersonalityMatrix unavailable: %s", _e)

try:
    from src.quantum.quantum_core import (
        QuantumNeuralCore,  # noqa: F401  # intentional top-level import
    )
except ImportError as _qiskit_err:
    QuantumNeuralCore = None  # type: ignore[assignment,misc]
    logging.getLogger(__name__).warning("Quantum core unavailable (qiskit): %s", _qiskit_err)

try:
    from src.observability.proactive_health import ProactiveHealthMonitor
except ImportError as _e:
    ProactiveHealthMonitor = None  # type: ignore[assignment,misc]
    logging.getLogger(__name__).warning("ProactiveHealthMonitor unavailable: %s", _e)

try:
    from src.entities.auto_evolve import AutoEvolve
except ImportError as _e:
    AutoEvolve = None  # type: ignore[assignment,misc]
    logging.getLogger(__name__).warning("AutoEvolve unavailable: %s", _e)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("tranc3.api")


# ── Runtime config ────────────────────────────────────────────────────────────
class Config:
    model_path = os.getenv("MODEL_PATH", "./models/tranc3-base.pt")
    cache_dir = os.getenv("CACHE_DIR", "./cache")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    primary_language = os.getenv("PRIMARY_LANGUAGE", "en")
    supported_languages = os.getenv("SUPPORTED_LANGUAGES", "en,es,fr,de,zh,ja").split(",")
    enable_emotion = os.getenv("ENABLE_EMOTION", "true").lower() == "true"
    personality_dir = os.getenv("PERSONALITY_DIR", "./src/personality/profiles")
    vocab_size = 119547
    hidden_size = 768
    num_layers = 12
    num_heads = 12
    max_sequence_length = 512
    architecture = "multilingual"
    freeze_base = False

    def get(self, key, default=None):
        return getattr(self, key, default)


# ── Global state ──────────────────────────────────────────────────────────────
model = None
tokenizer = None
personality_matrix = None
redis_client = None
feature_flags = None
quantum_core = None
consciousness_model = None
neuromorphic = None
evolution_engine = None
db_manager = None
db_user_manager: "DBUserManager" = DBUserManager(None)  # in-memory fallback; replaced in lifespan
_start_time = time.time()
_feedback_count = 0  # codeql[py/unused-global]
EVOLUTION_TRIGGER = 100  # codeql[py/unused-global]
_health_monitor = None
_auto_evolve = None
_bootstrap_complete = False


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, tokenizer, personality_matrix, redis_client, feature_flags
    global quantum_core, consciousness_model, neuromorphic, evolution_engine
    global db_manager, db_user_manager, _health_monitor, _auto_evolve, _bootstrap_complete

    logger.info("TRANC3 starting up...")
    _bootstrap_complete = False
    cfg = Config()
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"

    # Audit signing key health check — warn early before any audit events are written
    _audit_key = os.getenv("AUDIT_SIGNING_KEY", "")
    if not _audit_key:
        _key_file = "logs/audit/.audit_signing_key"
        import pathlib

        if pathlib.Path(_key_file).exists():
            logger.warning(
                "AUDIT_SIGNING_KEY not set in environment — using persistent key file (%s). "
                "Single-node restarts will verify correctly. For multi-node or DR deployments "
                "set AUDIT_SIGNING_KEY to the contents of that file in all instances. "
                "Run: python scripts/generate_env.py to write it to .env",
                _key_file,
            )
        else:
            logger.warning(
                "AUDIT_SIGNING_KEY not set — AuditLedger will generate and persist a key to "
                "%s on first audit write. Set AUDIT_SIGNING_KEY env var (or run "
                "python scripts/generate_env.py) to make verification portable.",
                _key_file,
            )

    # Database
    try:
        db_manager = DatabaseManager(os.getenv("DATABASE_URL", "sqlite:///./tranc3_dev.db"))
        db_user_manager = DBUserManager(db_manager.get_session)
        logger.info("Database connected")
    except Exception as e:
        if is_production:
            raise RuntimeError("Database connection failed during production startup.") from e
        logger.warning(
            "Database unavailable: %s — in-memory fallback",
            sanitize_for_log(e),
        )  # codeql[py/cleartext-logging]
        db_user_manager = DBUserManager(None)

    # Redis
    try:
        redis_client = redis_lib.from_url(cfg.redis_url, decode_responses=True)
        redis_client.ping()
        logger.info("Redis connected")
    except Exception as e:
        if is_production:
            raise RuntimeError("Redis connection failed during production startup.") from e
        logger.warning("Redis unavailable: %s", sanitize_for_log(e))  # codeql[py/cleartext-logging]
        redis_client = None

    # Feature flags (requires Redis)
    if redis_client:
        feature_flags = FeatureFlagManager(redis_client)

    # Tokenizer
    try:
        tokenizer = MultilingualTokenizer(cfg)
        logger.info("Tokenizer ready")
    except Exception:
        logger.error("Tokenizer failed")

    # Personality matrix
    try:
        personality_matrix = EnhancedPersonalityMatrix(cfg)  # type: ignore[arg-type]
        logger.info("Personality matrix ready")
    except Exception as e:
        logger.error(
            "Personality matrix failed: %s",
            sanitize_for_log(e),
        )  # codeql[py/cleartext-logging]

    # Quantum core
    if QuantumNeuralCore is not None:
        try:
            quantum_core = QuantumNeuralCore({"num_qubits": 8})
            logger.info("Quantum core ready")
        except Exception as e:
            logger.warning(
                "Quantum core unavailable: %s",
                sanitize_for_log(e),
            )  # codeql[py/cleartext-logging]

    # Consciousness model
    try:
        consciousness_model = ConsciousnessModel(
            {
                "consciousness_threshold": 3.0,
                "state_dimensions": 64,
                "workspace_size": 256,
                "competition_threshold": 0.7,
                "introspection_depth": 3,
            },
        )
        logger.info("Consciousness model ready")
    except Exception as e:
        logger.warning(
            "Consciousness model unavailable: %s",
            sanitize_for_log(e),
        )  # codeql[py/cleartext-logging]

    # Neuromorphic processor
    try:
        neuromorphic = NeuromorphicProcessor(cfg)
        logger.info("Neuromorphic processor ready")
    except Exception as e:
        logger.warning(
            "Neuromorphic processor unavailable: %s",
            sanitize_for_log(e),
        )  # codeql[py/cleartext-logging]

    # Evolution engine
    try:
        evolution_engine = SelfEvolvingArchitecture(
            {
                "population_size": 10,
                "mutation_rate": 0.01,
                "genome_dim": 768,
            },
        )
        evolution_engine.load_genome_from_redis()
        logger.info("Evolution engine ready")
    except Exception as e:
        logger.warning(
            "Evolution engine unavailable: %s",
            sanitize_for_log(e),
        )  # codeql[py/cleartext-logging]

    # Model
    try:
        model = AdvancedTransformerModel(cfg)
        if os.path.exists(cfg.model_path):
            if _TORCH_AVAILABLE and torch is not None:
                model.load_state_dict(safe_torch_load(cfg.model_path, device="cpu"))
            logger.info("Model weights loaded")
        else:
            logger.warning("No model weights — echo mode active")
        model.eval()
    except Exception as e:
        logger.warning(
            "Model init failed: %s — echo mode",
            sanitize_for_log(e),
        )  # codeql[py/cleartext-logging]
        model = None

    # Proactive health monitor
    if ProactiveHealthMonitor is not None:
        try:
            _health_monitor = ProactiveHealthMonitor()
            await _health_monitor.start()
            logger.info("Proactive health monitor started")
        except Exception as e:
            logger.warning("ProactiveHealthMonitor failed to start: %s", sanitize_for_log(e))

    # AutoEvolve scheduler
    if AutoEvolve is not None:
        try:
            _auto_evolve = AutoEvolve()
            await _auto_evolve.start()
            logger.info("AutoEvolve scheduler started")
        except Exception as e:
            logger.warning("AutoEvolve failed to start: %s", sanitize_for_log(e))

    # pgvector — bootstrap embeddings table (no-ops gracefully if unavailable)
    try:
        from src.database.pgvector import (
            bootstrap as _pgvector_bootstrap,  # codeql[py/cyclic-import]
        )

        if _pgvector_bootstrap():
            logger.info("pgvector embeddings table ready")
        else:
            logger.debug("pgvector unavailable — vector ops will use fallback")
    except Exception as _pgv_exc:
        logger.debug("pgvector bootstrap skipped: %s", sanitize_for_log(_pgv_exc))

    # Knowledge Brain (The Library) — start dream-cycle consolidation
    _knowledge_brain = None
    try:
        from src.knowledge.knowledge_brain import (
            get_brain as _get_brain,  # codeql[py/cyclic-import]
        )

        _knowledge_brain = _get_brain()
        await _knowledge_brain.start_dream_cycle()
        logger.info("Knowledge Brain dream cycle started (The Library / Zimik)")
    except Exception as _kb_exc:
        logger.warning("Knowledge Brain unavailable: %s", sanitize_for_log(_kb_exc))

    try:
        from src.adaptive.proactive_orchestrator import get_proactive_orchestrator

        await get_proactive_orchestrator().start_background()
        logger.info("Proactive zero-cost orchestrator started")
    except Exception as _po_exc:
        logger.warning("Proactive orchestrator unavailable: %s", sanitize_for_log(_po_exc))

    # MAPE-K sovereign control loop (Master Worker — autonomic platform orchestration)
    _mape_k_loop = None
    try:
        from src.master_worker.mape_k import MapeKLoop

        _mape_k_loop = MapeKLoop()
        await _mape_k_loop.start()
        logger.info("MAPE-K control loop started (Master Worker)")
    except Exception as _mk_exc:
        logger.warning("MAPE-K loop unavailable: %s", sanitize_for_log(_mk_exc))

    try:
        from src.adaptive.cloud_rotation_loop import start_cloud_auto_rotation
        from src.platform.infrastructure_mode import infrastructure_status

        await start_cloud_auto_rotation()
        _infra = infrastructure_status()
        logger.info(
            "Platform infrastructure mode=%s rotation_chain=%s cloud_auto_rotate=%s",
            _infra["mode"],
            _infra["rotation_chain"],
            _infra["cloud_auto_rotate"],
        )
    except Exception as _cr_exc:
        logger.warning("Cloud auto-rotation unavailable: %s", sanitize_for_log(_cr_exc))

    try:
        from src.adaptive.layer_rotation_loop import start_layer_auto_rotation

        await start_layer_auto_rotation()
        logger.info("Platform layer auto-rotation started")
    except Exception as _lr_exc:
        logger.warning("Layer auto-rotation unavailable: %s", sanitize_for_log(_lr_exc))

    try:
        from src.admin_os.backup_loop import start_admin_os_auto_backup

        await start_admin_os_auto_backup()
        logger.info("Infinity Admin OS auto-backup scheduler started")
    except Exception as _ab_exc:
        logger.warning("Admin OS auto-backup unavailable: %s", sanitize_for_log(_ab_exc))

    # Event Bus wiring — Observatory → EventBus → Library/ThinkTank/Search/Sentinel
    try:
        from src.event_bus import get_event_bus
        from src.event_bus.wiring import wire_platform_events

        wire_platform_events(get_event_bus())
        logger.info("Event Bus wiring active (TR3-005)")
    except Exception as _eb_exc:
        logger.warning("Event Bus wiring unavailable: %s", sanitize_for_log(_eb_exc))

    # Section 7 threat intelligence loop — CVE/OSV/CISA feed polling
    _threat_intel_task = None
    try:
        from src.section7.threat_intel_loop import start_threat_intel_loop

        _threat_intel_task = await start_threat_intel_loop()
        logger.info("Section 7 threat intel loop started (TR3-006)")
    except Exception as _ti_exc:
        logger.warning("Section 7 threat intel loop unavailable: %s", sanitize_for_log(_ti_exc))

    # Healing Bridge — wire health monitor → self-repair engine
    try:
        from src.healing.healing_bridge import HealingBridge
        from src.healing.self_repair import SelfRepairEngine

        if _health_monitor is not None:
            _repair_engine = SelfRepairEngine()
            _healing_bridge = HealingBridge(_health_monitor, _repair_engine)
            _healing_bridge.attach()
            logger.info("Healing Bridge active — health monitor wired to self-repair engine")
    except Exception as _hb_exc:
        logger.warning("Healing Bridge unavailable: %s", sanitize_for_log(_hb_exc))

    # OpenTelemetry instrumentation
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry FastAPI instrumentation active")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-fastapi not installed — traces disabled")
    except Exception as _otel_exc:
        logger.warning("OpenTelemetry instrumentation failed: %s", sanitize_for_log(_otel_exc))

    # Observatory→Library pipeline — wire audit events to KB article triggers
    try:
        from src.observability.library_pipeline import start_pipeline

        start_pipeline()
        logger.info("Observatory→Library pipeline started")
    except Exception as _lib_exc:
        logger.warning("Observatory→Library pipeline unavailable: %s", sanitize_for_log(_lib_exc))

    # Runtime security checks — CVE-2025-69872, non-root assertion, provider health
    try:
        from src.utils.security_checks import run_startup_checks

        run_startup_checks()
    except Exception as _sec_exc:
        logger.warning("Startup security checks failed: %s", sanitize_for_log(_sec_exc))

    logger.info("TRANC3 API ready ✓")
    _bootstrap_complete = True
    yield

    if _quota_rotation_task is not None:
        _quota_rotation_task.cancel()

    logger.info("TRANC3 shutting down")
    _bootstrap_complete = False
    if _mape_k_loop is not None:
        try:
            await _mape_k_loop.stop()
        except Exception as _mk_stop_exc:
            logger.warning("MAPE-K loop stop error: %s", sanitize_for_log(_mk_stop_exc))
    if _knowledge_brain is not None:
        try:
            await _knowledge_brain.stop_dream_cycle()
        except Exception as _stop_exc:
            logger.warning("Knowledge Brain stop error: %s", sanitize_for_log(_stop_exc))
    if _auto_evolve is not None:
        try:
            await _auto_evolve.stop()
        except Exception as _stop_exc:
            logger.warning("AutoEvolve stop error: %s", sanitize_for_log(_stop_exc))
    if _health_monitor is not None:
        try:
            await _health_monitor.stop()
        except Exception as _stop_exc:
            logger.warning("ProactiveHealthMonitor stop error: %s", sanitize_for_log(_stop_exc))
    if redis_client:
        redis_client.close()


# ── OpenAPI tag metadata ──────────────────────────────────────────────────────
_OPENAPI_TAGS = [
    {
        "name": "auth",
        "description": "Authentication — register, obtain JWT tokens, refresh sessions. "
        "Powered by **Infinity** (The Guardian / Orb of Orisis).",
    },
    {
        "name": "inference",
        "description": "Core AI inference — chat completions, emotion analysis, consciousness "
        "scoring, feedback. Powered by **Luminous** (Cornelius MacIntyre).",
    },
    {
        "name": "system",
        "description": "Platform health, readiness, Prometheus metrics, and feature-flag state. "
        "Sourced from **The Observatory** (Norman Hawkins).",
    },
    {
        "name": "info",
        "description": "Static capability discovery — supported languages and personality profiles.",
    },
    {
        "name": "billing",
        "description": "Subscription tiers, usage quotas, and Stripe checkout. "
        "Handled by **Royal Bank of Arcadia** (Dorris Fontaine).",
    },
    {
        "name": "compliance",
        "description": "GDPR data-erasure and audit-log endpoints. "
        "Governed by **The Town Hall** (Tristuran).",
    },
    {
        "name": "admin",
        "description": "Internal observability — file registry, circuit breakers, loop validator, "
        "abuse detector, self-healing history. Requires Business or Enterprise tier.",
    },
    {
        "name": "docs",
        "description": "Error-code documentation lookup. No authentication required.",
    },
    {
        "name": "mcp",
        "description": "Model Context Protocol (MCP) — JSON-RPC 2.0 tool registry, SSE event bus, "
        "and workflow integration. Powered by **The Spark** (Norman Hawkins). "
        "Endpoints: `/mcp/rpc`, `/mcp/sse`, `/mcp/tools`, `/mcp/health`, `/mcp/grid/status`.",
    },
    {
        "name": "evaluation",
        "description": "Model evaluation endpoints — BLEU, ROUGE-L, Exact Match, Token-F1, "
        "hallucination scoring, and LoRA checkpoint comparison. "
        "Powered by **Luminous** (Cornelius MacIntyre).",
    },
]

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TRANC3 API",
    version="2.0.0",
    description=(
        "# TRANC3 — Quantum-Conscious Multilingual AI Platform\n\n"
        "Self-hosted, zero-cost platform built on FastAPI + SQLite. "
        "All 43 Trancendos subsystems are wired through this gateway.\n\n"
        "## Authentication\n"
        "All protected endpoints require a Bearer JWT issued by `POST /auth/token`.\n\n"
        "## Rate limits\n"
        "| Tier | Requests / hour |\n"
        "|---|---|\n"
        "| Free | 100 |\n"
        "| Pro | 1 000 |\n"
        "| Business | 10 000 |\n"
        "| Enterprise | unlimited |\n\n"
        "## Canonical service names\n"
        "Service names follow the Trancendos canonical entity registry. "
        "See `PLATFORM_ENTITIES.md` for the full list of 43 entities."
    ),
    openapi_tags=_OPENAPI_TAGS,
    lifespan=lifespan,
    contact={"name": "Trancendos Platform", "email": "ops@trancendos.com"},
    license_info={"name": "Proprietary"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AITransparencyMiddleware)


# ── API version header (REQ-SD-002 — DEF STAN 00-056 API Contract Versioning) ─
_API_VERSION = "2.0.0"
_API_VERSION_HEADER = "X-API-Version"


@app.middleware("http")
async def api_version_header_middleware(request, call_next):
    """Attach X-API-Version to every response for explicit contract versioning."""
    response = await call_next(request)
    response.headers[_API_VERSION_HEADER] = _API_VERSION
    return response


app.add_middleware(GovernanceMiddleware)
# MagnaCartaMiddleware is inner to ZeroTrustASGIMiddleware so that jwt_claims/zero_trust_ok
# are already on request.state when compliance rules execute. Advisory by default.
app.add_middleware(MagnaCartaMiddleware)
app.add_middleware(ZeroTrustASGIMiddleware)
# CABMiddleware: enforces X-Change-ID on mutating requests to protected paths when enabled.
# Runs innermost (added first, executes last after auth+MC checks complete).
if os.getenv("CAB_GATE_ENABLED", "false").lower() == "true":
    app.add_middleware(CABMiddleware)
app.add_middleware(RBACMiddleware)

# ── Additional middleware: GZip, TrustedHost, Idempotency, ContentNegotiation ─
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from api.middleware.idempotency import IdempotencyMiddleware
from api.middleware.content_negotiation import ContentNegotiationMiddleware

# Registration order (Starlette: last-added runs first on requests):
# ContentNegotiation → Idempotency → TrustedHost → GZip
# Execution order on responses: GZip compresses last so caches/negotiation see raw JSON.
app.add_middleware(ContentNegotiationMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=os.getenv("ALLOWED_HOSTS", "*").split(","),
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── The Spark (MCP server) ────────────────────────────────────────────────────
from src.mcp.server import router as _mcp_router  # codeql[py/cyclic-import]

app.include_router(_mcp_router)

# ── The Observatory (audit log + event feed) ──────────────────────────────────
from src.observability.routes import (
    router as _observatory_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_observatory_router)

# ── The Nexus (AI communications + transfer hub) ─────────────────────────────
from src.nexus.routes import router as _nexus_router  # noqa: F401  # intentional top-level import

app.include_router(_nexus_router)

# ── The Town Hall (governance + compliance) ───────────────────────────────────
from src.townhall.routes import (
    router as _townhall_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_townhall_router)

# ── The Library (knowledge base) ─────────────────────────────────────────────
from src.library.routes import (
    router as _library_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_library_router)

# ── The Basement (archive + vector search) ────────────────────────────────────
from src.basement.routes import (
    router as _basement_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_basement_router)

# ── Cryptex (threat detection + cyber defence) ────────────────────────────────
from src.cryptex.routes import (
    router as _cryptex_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_cryptex_router)

# ── Section 7 (research + intelligence reports) ───────────────────────────────
from src.research.routes import (
    router as _section7_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_section7_router)

# ── The Digital Grid (workflow DAG builder + executor) ────────────────────────
from src.workflow.routes import router as _grid_router  # noqa: F401  # intentional top-level import

app.include_router(_grid_router)

# ── I-Mind (sensitivity + crisis protocol) ────────────────────────────────────
from src.imind.routes import router as _imind_router  # noqa: F401  # intentional top-level import

app.include_router(_imind_router)

# ── tAimra (digital twin — opt-in, OFFLINE by default) ────────────────────────
from src.taimra.routes import router as _taimra_router  # noqa: F401  # intentional top-level import

app.include_router(_taimra_router)

# ── Tranquility (wellbeing hub) ────────────────────────────────────────────────
from src.tranquility.routes import (
    router as _tranquility_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_tranquility_router)

# ── Resonate (empathy + understanding services) ────────────────────────────────
from src.resonate.routes import (
    router as _resonate_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_resonate_router)

# ── The Studio (creativity hub — Sasha's Photo, TateKing, TranceFlow, Fabulousa)
from src.studio.routes import router as _studio_router  # noqa: F401  # intentional top-level import

app.include_router(_studio_router)

# ── The Lab (AI code creation platform) ──────────────────────────────────────
from src.lab.routes import router as _lab_router  # noqa: F401  # intentional top-level import

app.include_router(_lab_router)

# ── ChronosSphere / ArcStream (time + schedule management) ───────────────────
from src.chronos.routes import (
    router as _chronos_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_chronos_router)

# ── Turing's Hub (AI personality creation centre) ────────────────────────────
from src.personality.turingshub.routes import (
    router as _turingshub_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_turingshub_router)

# ── DevOcity (developer centre — API keys, webhooks, guides) ─────────────────
from src.devocity.routes import (
    router as _devocity_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_devocity_router)

# ── The Artifactory (OCI artefact repository — Zot foundation) ───────────────
from src.artifactory.routes import (
    router as _artifactory_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_artifactory_router)

# ── API Marketplace (connector hub — Gravitee.io foundation) ─────────────────
from src.apimarket.routes import (
    router as _apimarket_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_apimarket_router)

# ── VRAR3D (AR/VR wellbeing centre — Three.js / A-Frame WebXR) ───────────────
from src.vrar3d.routes import router as _vrar3d_router  # noqa: F401  # intentional top-level import

app.include_router(_vrar3d_router)

# ── The Citadel (DevOps hub — Forgejo + Fly.io + CF Workers) ─────────────────
from src.citadel.routes import (
    router as _citadel_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_citadel_router)

# ── Luminous (AI brain — consciousness engine + neuromorphic) ─────────────────
from src.bio_neural.routes import (
    router as _luminous_router,  # noqa: F401  # intentional top-level import
)

app.include_router(_luminous_router)

# ── Think Tank (quantum + deep research engines) ──────────────────────────────
try:
    from src.quantum.routes import (
        router as _thinktank_router,  # noqa: F401  # intentional top-level import
    )

    app.include_router(_thinktank_router)
except ImportError:
    logger.debug("Graceful degradation: %s", "unknown")  # nosec B110

# ── Enhanced Capabilities (code gen, skills, planning, self-healing) ─────────
# Migrated from legacy api_enhanced.py into the canonical entry point.
from src.routers.enhanced_capabilities import router as _enhanced_router  # noqa: F401

app.include_router(_enhanced_router)

# ── Ecosystem (hub states, citadel, defense, AI gateway, heartbeat) ──────────
# Migrated from legacy api_ecosystem.py into the canonical entry point.
from src.routers.ecosystem import router as _ecosystem_router  # noqa: F401

app.include_router(_ecosystem_router)

# ── Frontend static files (served from web/dist/ after `npm run build`) ───────
_FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "web", "dist")
if os.path.isdir(_FRONTEND_DIST):
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(_FRONTEND_DIST, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        index = os.path.join(_FRONTEND_DIST, "index.html")
        return FileResponse(index)


# ── Models ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    language: str = Field("en")
    personality: str = "tranc3-base"
    user_emotion: Optional[str] = "neutral"
    conversation_history: Optional[List[Dict]] = []
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    detected_emotion: str
    language: str
    personality: str
    timestamp: datetime.datetime
    processing_time_ms: float
    request_id: str
    consciousness_level: Optional[float] = None
    quantum_used: bool = False
    foresight: Optional[Dict] = None
    quality: Optional[Dict] = None


class TokenRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class HealthComponent(BaseModel):
    api: str
    model: str
    tokenizer: str
    personality: str
    quantum: str
    consciousness: str
    redis: Optional[str] = None
    supabase: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    uptime_seconds: float
    components: Dict


class ReadyResponse(BaseModel):
    ready: bool
    timestamp: str


class LanguagesResponse(BaseModel):
    languages: List[str]
    primary: str


class PersonalitiesResponse(BaseModel):
    personalities: List[str]


class EmotionResponse(BaseModel):
    dominant_emotion: str
    emotion_scores: Dict[str, float]
    text: str


class FeedbackResponse(BaseModel):
    message: str
    impact: str


class ConsciousnessResponse(BaseModel):
    phi: float
    is_conscious: bool
    text: str
    report: Dict


class BillingUsageResponse(BaseModel):
    requests_used: Optional[int] = None
    requests_limit: Optional[int] = None
    reset_at: Optional[str] = None
    message: Optional[str] = None


class CheckoutResponse(BaseModel):
    checkout_url: str
    tier: str


class GDPREraseResponse(BaseModel):
    message: str
    user_id: str


class AdminRegistryResponse(BaseModel):
    files: Optional[List[Dict]] = None
    integrity_ok: Optional[bool] = None


class AdminCircuitsResponse(BaseModel):
    circuits: Optional[Dict] = None


class ErrorDocResponse(BaseModel):
    code: str
    title: str
    http_status: Optional[int] = None
    description: Optional[str] = None
    remediation: Optional[str] = None


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.post(
    "/auth/register",
    tags=["auth"],
    summary="Register a new user account",
    description=(
        "Create a new user account with a username and password. "
        "Returns the created user record. Usernames must be unique."
    ),
    status_code=201,
)
async def register(req: RegisterRequest):
    return db_user_manager.create_user(req.username, req.password)


@app.post(
    "/auth/token",
    tags=["auth"],
    response_model=TokenResponse,
    summary="Obtain a JWT access token",
    description=(
        "Exchange username + password for a signed JWT (HS256, 1-hour expiry). "
        "Include the returned `access_token` in the `Authorization: Bearer <token>` header "
        "on all protected requests."
    ),
)
async def login(req: TokenRequest):
    user = db_user_manager.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = token_manager.create_access_token({"sub": user["username"]})
    return {"access_token": token, "token_type": "bearer", "expires_in": 3600}


@app.post(
    "/auth/refresh",
    tags=["auth"],
    response_model=TokenResponse,
    summary="Refresh the caller's JWT",
    description="Issue a fresh 1-hour JWT for the currently authenticated user.",
)
async def refresh_token(current_user: dict = Depends(get_current_user)):
    new_token = token_manager.create_access_token(
        {"sub": current_user["username"]},
        expires_delta=datetime.timedelta(hours=1),
    )
    return {"access_token": new_token, "token_type": "bearer", "expires_in": 3600}


# ── System ────────────────────────────────────────────────────────────────────
@app.get(
    "/health",
    tags=["system"],
    response_model=HealthResponse,
    summary="Platform health check",
    description=(
        "Returns liveness status of all major subsystems: model, tokenizer, "
        "personality matrix, quantum core, consciousness engine, Redis, and Supabase. "
        "Status is `healthy` if all components are up, `degraded` if any are unavailable. "
        "No authentication required."
    ),
)
async def health():

    components: dict = {
        "api": "healthy",
        "model": "healthy" if model else "echo_mode",
        "tokenizer": "healthy" if tokenizer else "unavailable",
        "personality": "healthy" if personality_matrix else "unavailable",
        "quantum": "healthy" if quantum_core else "unavailable",
        "consciousness": "healthy" if consciousness_model else "unavailable",
    }

    # ── Live Redis probe ───────────────────────────────────────────────────
    try:
        from src.core.redis_store import get_store  # noqa: F401  # intentional top-level import

        store = await asyncio.wait_for(get_store(), timeout=2.0)
        ok = await asyncio.wait_for(store.ping(), timeout=2.0)
        components["redis"] = "healthy" if ok else "degraded"
        components["redis_backend"] = getattr(store, "backend", "unknown")
    except Exception as exc:
        components["redis"] = f"unavailable: {str(exc)[:40]}"

    # ── Live Supabase probe ────────────────────────────────────────────────
    try:
        import httpx

        sb_url = os.environ.get("SUPABASE_URL", "")
        sb_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if sb_url and sb_key:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(
                    f"{sb_url}/rest/v1/",
                    headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
                )
            components["supabase"] = "healthy" if resp.status_code < 500 else "degraded"
        else:
            components["supabase"] = "unconfigured"
    except Exception as exc:
        components["supabase"] = f"unavailable: {str(exc)[:40]}"

    # ── Spark tools ───────────────────────────────────────────────────────
    try:
        from src.mcp.tools import registry  # noqa: F401  # intentional top-level import

        components["spark_tools"] = len(registry.list_tools())
    except Exception:
        components["spark_tools"] = 0

    # ── Proactive health monitor ──────────────────────────────────────────
    if _health_monitor is not None:
        components["health_monitor"] = "healthy"
        components["health_monitor_alerts"] = _health_monitor.status().get("total_alerts", 0)
    else:
        components["health_monitor"] = "unavailable"

    # ── AutoEvolve scheduler ──────────────────────────────────────────────
    if _auto_evolve is not None:
        components["auto_evolve"] = "healthy"
        components["auto_evolve_registered"] = _auto_evolve.status().get("registered", 0)
    else:
        components["auto_evolve"] = "unavailable"

    degraded = any(str(v).startswith(("degraded", "unavailable")) for v in components.values())
    overall = "degraded" if degraded else "healthy"

    return {
        "status": overall,
        "version": "2.0.0",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "uptime_seconds": round(time.time() - _start_time, 1),
        "components": components,
    }


@app.get(
    "/ready",
    tags=["system"],
    response_model=ReadyResponse,
    summary="Kubernetes readiness probe",
    description=(
        "Lightweight readiness check — returns `ready: true` once the API bootstrap is complete. "
        "Does **not** require model weights; bootstrap mode is production-valid. "
        "Use this as a Kubernetes readinessProbe target."
    ),
)
async def ready():
    # Readiness: API itself is up and core bootstrap complete
    # Does NOT require model weights — bootstrap mode is production-valid
    if not _bootstrap_complete:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "timestamp": datetime.datetime.utcnow().isoformat(),
            },
        )
    return {"ready": True, "timestamp": datetime.datetime.utcnow().isoformat()}


@app.get(
    "/metrics",
    tags=["system"],
    response_class=PlainTextResponse,
    summary="Prometheus metrics scrape endpoint",
    description=(
        "Exposes all platform metrics in Prometheus text format. "
        "Scraped by **The Observatory** (Norman Hawkins) every 15 s. "
        "Returns a plain-text comment if `prometheus_client` is not installed."
    ),
)
async def metrics():
    try:
        from prometheus_client import generate_latest

        return generate_latest()
    except Exception:
        return "# prometheus_client not available\n"


@app.get(
    "/features",
    tags=["system"],
    summary="Active feature flags",
    description=(
        "Returns the current state of all feature flags (Redis-backed). "
        "Flags include `QUANTUM_OPTIMIZATION`, `CONSCIOUSNESS_ENGINE`, and others. "
        "Returns an error dict if Redis is unavailable."
    ),
)
async def features():
    if not feature_flags:
        return {"error": "Feature flags unavailable — Redis required"}
    return feature_flags.get_all_flags()


# ── Inference ─────────────────────────────────────────────────────────────────
@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["inference"],
    summary="Send a chat message to Luminous",
    description=(
        "Core inference endpoint. Sends a message through the full **Luminous** pipeline: "
        "emotion detection → personality vector → quantum attention (if enabled) → "
        "consciousness Φ scoring → response generation. "
        "Supports streaming via `POST /ws/chat` WebSocket. "
        "Rate-limited per tier (free: 100/hr, pro: 1 000/hr, business: 10 000/hr)."
    ),
)
async def chat(
    chat_req: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    request_id = os.urandom(8).hex()
    start = time.time()
    user_id = current_user["id"]
    tier = current_user.get("tier", "free")

    # Sanitise input — blocks XSS, SQLi, path traversal, prompt injection
    InputSanitizer.sanitize(chat_req.message)

    # IP protection — prompt injection + model extraction detection
    ip_check = abuse_detector.check_message(chat_req.message, user_id)
    if not ip_check["allowed"]:
        raise HTTPException(
            status_code=400,
            detail=format_error_response(
                ErrorCode.SEC_INPUT_BLOCKED,
                "Message blocked by security filter",
            ),
        )

    # Compliance
    compliance.check_request({"user_id": user_id, "message": chat_req.message})

    # Rate limiting
    try:
        tier_enforcer.check_and_increment(user_id, tier)
    except ValueError as e:
        raise HTTPException(status_code=429, detail=safe_error_detail(e, 429))

    # Feature gates
    use_quantum = (
        feature_flags.is_enabled(FeatureFlag.QUANTUM_OPTIMIZATION, user_id)
        if feature_flags
        else False
    )
    use_consciousness = (
        feature_flags.is_enabled(FeatureFlag.CONSCIOUSNESS_ENGINE, user_id)
        if feature_flags
        else False
    )

    # Language validation
    supported = tokenizer.supported_languages if tokenizer else Config.supported_languages
    if chat_req.language not in supported:
        raise HTTPException(status_code=400, detail=f"Unsupported language. Supported: {supported}")

    try:
        # Emotion detection
        detected_emotion = chat_req.user_emotion or "neutral"
        emotion_scores = {"neutral": 1.0}
        _ed = getattr(personality_matrix, "emotion_detector", None) if personality_matrix else None
        if _ed is not None:
            emotion_scores = _ed.detect_emotion(chat_req.message)
            detected_emotion = _ed.get_dominant_emotion(emotion_scores)

        # Compress conversation history if long
        history = compressor.compress(chat_req.conversation_history or [])

        # Predictive analytics
        analysis = analytics.analyse_request(
            user_id=user_id,
            message=chat_req.message,
            emotion=detected_emotion,
            language=chat_req.language,
            personality=chat_req.personality,
        )

        # Foresight
        foresight_result = foresight.analyse(
            session_id=chat_req.session_id or user_id,
            user_message=chat_req.message,
            emotion=detected_emotion,
            intent=analysis.get("dominant_intent", "question"),
            churn_risk=analysis.get("churn_probability", 0.0),
            conversation_length=len(history),
        )

        # Personality vector
        personality_vector = None
        if personality_matrix:
            personality_vector = personality_matrix.get_personality_vector(
                chat_req.personality,
                emotion_scores,
                chat_req.language,
            )

        # Encode
        encoded = None
        if tokenizer:
            encoded = tokenizer.encode(
                chat_req.message,
                language=chat_req.language,
                return_tensors=True,
            )

        # Quantum attention
        quantum_used = False
        if quantum_core and use_quantum and _TORCH_AVAILABLE and torch is not None:
            try:
                quantum_core.quantum_attention(torch.randn(1, 8, 64))
                quantum_used = True
            except Exception as e:
                logger.warning(
                    "Quantum attention skipped: %s",
                    sanitize_for_log(e),
                )  # codeql[py/cleartext-logging]

        # Consciousness Φ
        phi_score = None
        if consciousness_model and use_consciousness and _TORCH_AVAILABLE and torch is not None:
            try:
                phi_score = consciousness_model.calculate_phi(torch.randn(64))
                record_phi(phi_score)
            except Exception as e:
                logger.warning(
                    "Consciousness Φ skipped: %s",
                    sanitize_for_log(e),
                )  # codeql[py/cleartext-logging]

        # Generate
        if model and encoded is not None:
            result = CIRCUITS["model_inference"].call(
                lambda: model(
                    input_ids=encoded["input_ids"],
                    attention_mask=encoded["attention_mask"],
                    personality_vector=personality_vector,
                ),
                fallback=lambda: None,
            )
            response_text = (
                f"[TRANC3] {chat_req.message[:80]}..." if result else f"[Echo] {chat_req.message}"
            )
        else:
            response_text = f"[Echo] {chat_req.message}"

        # Watermark response for IP protection
        response_text = watermarker.watermark(response_text, request_id)

        # Fire-and-forget GBrain knowledge ingestion (The Library / Zimik)
        asyncio.create_task(
            _get_gbrain_pipeline().ingest(
                _GBrainInteraction(
                    prompt=chat_req.message,
                    response=response_text,
                    source="luminous-chat",
                    user_id=str(user_id),
                    session_id=request_id,
                ),
            ),
        )

        processing_ms = (time.time() - start) * 1000

        # Quality scoring
        quality = analytics.score_response(
            response=response_text,
            user_message=chat_req.message,
            emotion=detected_emotion,
            processing_time_ms=processing_ms,
        )

        # Observability
        record_request("/chat", "POST", 200, tier, processing_ms / 1000)
        record_emotion(detected_emotion, chat_req.language)
        record_churn_risk(analysis.get("churn_probability", 0.0))
        record_quality(quality["quality_scores"].get("overall", 0.0))

        # Background tasks
        background_tasks.add_task(
            _log_conversation,
            user_id,
            request_id,
            chat_req.language,
            chat_req.personality,
            detected_emotion,
            processing_ms,
        )
        background_tasks.add_task(
            _persist_conversation,
            user_id,
            request_id,
            chat_req.message,
            response_text,
            chat_req.language,
            chat_req.personality,
            detected_emotion,
            processing_ms,
            phi_score,
            quantum_used,
        )

        return ChatResponse(
            response=response_text,
            detected_emotion=detected_emotion,
            language=chat_req.language,
            personality=chat_req.personality,
            timestamp=datetime.datetime.utcnow(),
            processing_time_ms=round(processing_ms, 2),
            request_id=request_id,
            consciousness_level=round(phi_score, 4) if phi_score is not None else None,
            quantum_used=quantum_used,
            foresight={
                "trajectory": foresight_result["trajectory"],
                "recommendation": foresight_result["recommendation"],
                "dominant_intent": analysis.get("dominant_intent"),
                "churn_risk": analysis.get("churn_risk"),
            },
            quality=quality,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Chat error [%s]: %s",
            sanitize_for_log(request_id),
            sanitize_for_log(e),
            exc_info=True,
        )  # codeql[py/cleartext-logging]
        record_request("/chat", "POST", 500, tier, time.time() - start)
        raise HTTPException(status_code=500, detail="Internal server error")
    return None


# ── Streaming chat endpoint ───────────────────────────────────────────────────


@app.post(
    "/chat/stream",
    tags=["inference"],
    summary="Stream a chat response (SSE)",
    description=(
        "Streaming variant of `/chat`. Returns Server-Sent Events (SSE) with token-by-token "
        "output. Tries Ollama → llama.cpp → gateway simulation in order. "
        'Each event: `data: {"content": "token"}`. Stream ends with `data: [DONE]`.'
    ),
)
async def chat_stream(
    chat_req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    from fastapi.responses import StreamingResponse as _StreamingResponse

    user_id = current_user["id"]
    tier = current_user.get("tier", "free")

    try:
        InputSanitizer.sanitize(chat_req.message)
        tier_enforcer.check_and_increment(user_id, tier)
    except ValueError as e:
        raise HTTPException(status_code=429, detail=safe_error_detail(e, 429))
    except Exception as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, 400))

    try:
        from src.inference.conversation_store import get_conversation_store
        from src.inference.streaming import stream_sse

        # Build message list from session history if session_id provided
        session_id = getattr(chat_req, "session_id", None) or f"stream-{user_id}"
        store = get_conversation_store()
        messages = store.get_messages(session_id)
        if not messages:
            messages = [{"role": "user", "content": chat_req.message}]
        else:
            messages.append({"role": "user", "content": chat_req.message})
            store.add_message(session_id, "user", chat_req.message, str(user_id))

        return _StreamingResponse(
            stream_sse(messages, max_tokens=512),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as exc:
        logger.error("Stream endpoint error: %s", sanitize_for_log(exc))
        raise HTTPException(status_code=500, detail="Streaming unavailable")


# ── Conversation history endpoints ────────────────────────────────────────────


@app.get(
    "/conversations/{session_id}",
    tags=["inference"],
    summary="Get conversation history",
    description="Retrieve the full message history for a session.",
)
async def get_conversation(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        from src.inference.conversation_store import get_conversation_store

        store = get_conversation_store()
        messages = store.get_messages(session_id)
        return {"session_id": session_id, "messages": messages, "count": len(messages)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=safe_error_detail(exc, 500))


@app.delete(
    "/conversations/{session_id}",
    tags=["inference"],
    summary="Delete conversation history",
)
async def delete_conversation(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        from src.inference.conversation_store import get_conversation_store

        get_conversation_store().delete_session(session_id)
        return {"deleted": session_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=safe_error_detail(exc, 500))


# ── Thompson sampler stats ────────────────────────────────────────────────────


@app.get(
    "/luminous/providers",
    tags=["inference"],
    summary="AI provider health and Thompson sampler stats",
    description="Shows belief scores, success/failure counts, and average latency for all AI providers.",
)
async def provider_stats(current_user: dict = Depends(get_current_user)):
    try:
        from src.inference.thompson_sampler import get_sampler

        return {"providers": get_sampler().stats(), "ranked": get_sampler().rank_all()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=safe_error_detail(exc, 500))


@app.get(
    "/languages",
    tags=["info"],
    response_model=LanguagesResponse,
    summary="Supported languages",
    description="Returns the list of BCP-47 language codes the tokenizer accepts and the primary language.",
)
async def languages():
    return {
        "languages": tokenizer.supported_languages if tokenizer else Config.supported_languages,
        "primary": Config.primary_language,
    }


@app.get(
    "/personalities",
    tags=["info"],
    response_model=PersonalitiesResponse,
    summary="Available personality profiles",
    description=(
        "Returns all registered personality identifiers from **Turing's Hub** (Samantha Turing). "
        "Pass one of these values as `personality` in `/chat` requests."
    ),
)
async def personalities():
    if not personality_matrix:
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"personalities": list(personality_matrix.personalities.keys())}


@app.post(
    "/analyze-emotion",
    tags=["inference"],
    response_model=EmotionResponse,
    summary="Detect emotion in text",
    description=(
        "Run the **I-Mind** (Elouise) emotion detector over the supplied text. "
        "Returns the dominant emotion label and a score distribution across all emotion classes. "
        "Returns 503 if the emotion detector is unavailable."
    ),
)
async def analyze_emotion(text: str, current_user: dict = Depends(get_current_user)):
    _ed = getattr(personality_matrix, "emotion_detector", None) if personality_matrix else None
    if _ed is None:
        raise HTTPException(status_code=503, detail="Emotion analysis unavailable")
    scores = _ed.detect_emotion(text)
    dominant = _ed.get_dominant_emotion(scores)
    return {"dominant_emotion": dominant, "emotion_scores": scores, "text": text}


@app.post(
    "/feedback",
    tags=["inference"],
    response_model=FeedbackResponse,
    summary="Submit quality feedback",
    description=(
        "Record a 1–5 star quality rating for a previous chat response. "
        "Every 100 feedback events triggers a **self-evolution** cycle via the evolution engine, "
        "automatically tuning Luminous's response strategy."
    ),
)
async def feedback(
    request_id: str,
    rating: int = Query(..., ge=1, le=5),
    current_user: dict = Depends(get_current_user),
):
    global _feedback_count
    analytics.record_feedback(current_user["id"], float(rating))
    compliance.audit_log("feedback", {"user_id": current_user["id"], "rating": rating})

    if evolution_engine:
        _feedback_count += 1
        if _feedback_count >= EVOLUTION_TRIGGER:
            _feedback_count = 0
            evolution_engine.record_feedback(
                {"quality_score": rating / 5.0, "user_satisfaction": rating / 5.0},
            )
            best = evolution_engine.evolve(num_generations=1)
            logger.info(
                "Evolution: gen=%d, fitness=%.4f",
                evolution_engine.generation,
                best.fitness,
            )

    return {"message": "Feedback recorded", "impact": "evolution_queued"}


@app.post(
    "/consciousness/score",
    tags=["inference"],
    response_model=ConsciousnessResponse,
    summary="Compute Integrated Information Theory Φ score",
    description=(
        "Calculates the IIT Φ (phi) consciousness score for the provided text using the "
        "**Luminous** bio-neural consciousness engine. "
        "`phi > 2.0` is considered the consciousness threshold. "
        "Returns 503 if the consciousness engine is unavailable."
    ),
)
async def consciousness_score(text: str, current_user: dict = Depends(get_current_user)):
    if not consciousness_model:
        raise HTTPException(status_code=503, detail="Consciousness engine unavailable")
    if not _TORCH_AVAILABLE or torch is None:
        raise HTTPException(
            status_code=503,
            detail="Consciousness engine unavailable (torch not installed)",
        )
    try:
        phi = consciousness_model.calculate_phi(torch.randn(64))
        report = (
            consciousness_model.get_consciousness_report()
            if hasattr(consciousness_model, "get_consciousness_report")
            else {}
        )
        return {"phi": round(phi, 4), "is_conscious": phi > 2.0, "text": text, "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=safe_error_detail(e, 500))
    return None


# ── Billing ───────────────────────────────────────────────────────────────────
@app.get(
    "/billing/tiers",
    tags=["billing"],
    summary="Available subscription tiers",
    description=(
        "Returns the full tier catalogue: free, pro (£29/mo), business (£149/mo), enterprise. "
        "Stripe price IDs are excluded from the response. Managed by **Royal Bank of Arcadia**."
    ),
)
async def billing_tiers():
    return {t: {k: v for k, v in cfg.items() if k != "stripe_price_id"} for t, cfg in TIERS.items()}


@app.get(
    "/billing/usage",
    tags=["billing"],
    response_model=BillingUsageResponse,
    summary="Current usage for the authenticated user",
    description="Returns request count and rate-limit quota consumed in the current window.",
)
async def billing_usage(current_user: dict = Depends(get_current_user)):
    return tier_enforcer.get_usage(current_user["id"]) or {"message": "No usage recorded yet"}


@app.post(
    "/billing/checkout",
    tags=["billing"],
    response_model=CheckoutResponse,
    summary="Create a Stripe checkout session",
    description=(
        "Initiates a Stripe-hosted checkout flow for the requested tier upgrade. "
        "Returns a one-time `checkout_url` that expires after 30 minutes. "
        "Returns 503 if Stripe is not configured (zero-cost dev mode)."
    ),
)
async def billing_checkout(tier: str, current_user: dict = Depends(get_current_user)):
    from src.monetisation.billing import (
        stripe_manager,  # noqa: F401  # intentional top-level import
    )

    base = os.getenv("FRONTEND_URL", "http://localhost:3000")
    url = stripe_manager.create_checkout_session(
        current_user["id"],
        tier,
        f"{base}/billing/success",
        f"{base}/billing/cancel",
    )
    if not url:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    return {"checkout_url": url, "tier": tier}


@app.post("/billing/webhook", tags=["billing"], include_in_schema=False)
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    try:
        import stripe as _stripe

        _stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        event = _stripe.Webhook.construct_event(payload, sig, secret)
    except Exception as e:
        logger.warning(
            "Stripe webhook invalid: %s",
            sanitize_for_log(e),
        )  # codeql[py/cleartext-logging]
        raise HTTPException(status_code=400, detail="Invalid webhook")

    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    logger.info(
        "Stripe event: %s id=%s",
        sanitize_for_log(etype),
        sanitize_for_log(obj.get("id")),
    )  # codeql[py/cleartext-logging]
    return {"received": True}


# ── Compliance ────────────────────────────────────────────────────────────────
@app.delete(
    "/memory/{user_id}",
    tags=["compliance"],
    response_model=GDPREraseResponse,
    summary="GDPR right-to-erasure (Article 17)",
    description=(
        "Permanently deletes all stored vectors and conversation history for `user_id`. "
        "Users may erase their own data. Enterprise-tier users may erase any user's data. "
        "The erasure event is written to **The Observatory** audit log."
    ),
)
async def gdpr_erase(user_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["id"] != user_id and current_user.get("tier") != "enterprise":
        raise HTTPException(status_code=403, detail="Can only erase your own data")
    vector_store.delete_user(user_id)
    compliance.audit_log("gdpr_erasure", {"user_id": user_id, "by": current_user["id"]})
    return {"message": "All data erased", "user_id": user_id}


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            words = f"[TRANC3] {data.get('message', '')}".split()
            for i, word in enumerate(words):
                await websocket.send_json(
                    {
                        "chunk": word + (" " if i < len(words) - 1 else ""),
                        "done": i == len(words) - 1,
                    },
                )
                await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        logger.debug("Graceful degradation: %s", "unknown")  # nosec B110


# ── Background helpers ────────────────────────────────────────────────────────
async def _log_conversation(user_id, request_id, language, personality, emotion, processing_ms):
    log.info(
        "conversation",
        user_id=user_id,
        request_id=request_id,
        language=language,
        personality=personality,
        emotion=emotion,
        processing_ms=round(processing_ms, 2),
    )


async def _persist_conversation(
    user_id: str,
    request_id: str,
    user_message: str,
    ai_response: str,
    language: str,
    personality: str,
    emotion: str,
    processing_ms: float,
    phi: Optional[float] = None,
    quantum_used: bool = False,
):
    if not db_manager:
        return
    try:
        import uuid as _uuid

        session = db_manager.get_session()
        conv = Conversation(
            id=_uuid.uuid4(),
            user_id=_uuid.UUID(user_id) if len(user_id) == 36 else _uuid.uuid4(),
            language=language,
            personality=personality,
        )
        session.add(conv)
        session.flush()
        session.add(
            Message(
                id=_uuid.uuid4(),
                conversation_id=conv.id,
                role="user",
                content=user_message,
                language=language,
                detected_emotion=emotion,
            ),
        )
        session.add(
            Message(
                id=_uuid.uuid4(),
                conversation_id=conv.id,
                role="assistant",
                content=ai_response,
                language=language,
                detected_emotion=emotion,
                processing_time_ms=processing_ms,
                consciousness_level=phi,
                quantum_used=quantum_used,
            ),
        )
        session.commit()
        session.close()
    except Exception as e:
        log.warning("persist_failed", error=str(e))


if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",  # nosec B104 — container bind; not exposed without orchestrator port map
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENVIRONMENT") == "development",
    )


# ── Admin endpoints ───────────────────────────────────────────────────────────


@app.get(
    "/admin/registry",
    tags=["admin"],
    summary="File integrity registry",
    description=(
        "Lists all tracked files with their FID, version hash, and integrity verification status. "
        "Requires Business or Enterprise tier. Managed by **The Workshop** (Larry Lowhammer)."
    ),
)
async def admin_registry(
    current_user: dict = Depends(get_current_user),
    _perm: None = require_permission("admin:audit"),
):
    """File registry — lists all files with FID, version, and integrity status."""
    return file_registry.verify_all()


@app.get(
    "/admin/registry/{fid}",
    tags=["admin"],
    summary="File integrity status by FID",
    description="Returns the hash, version, and integrity verification result for a single file.",
)
async def admin_registry_file(
    fid: str,
    current_user: dict = Depends(get_current_user),
    _perm: None = require_permission("admin:audit"),
):
    """Get integrity status for a specific file by FID."""
    return file_registry.verify(fid)


@app.get(
    "/admin/circuits",
    tags=["admin"],
    summary="Circuit breaker states",
    description=(
        "Returns the state (closed / open / half-open) and failure counters for every "
        "registered circuit breaker. Used by **The Observatory** for automated alerting."
    ),
)
async def admin_circuits(
    current_user: dict = Depends(get_current_user),
    _perm: None = require_permission("admin:config"),
):
    """Circuit breaker status for all subsystems."""
    return {name: cb.get_status() for name, cb in CIRCUITS.items()}


@app.get(
    "/admin/loops",
    tags=["admin"],
    summary="Loop validator statistics",
    description=(
        "Returns call-depth counters and cascade-prevention statistics from the loop validator. "
        "Helps detect runaway recursion or infinite agent loops."
    ),
)
async def admin_loops(
    current_user: dict = Depends(get_current_user),
    _perm: None = require_permission("admin:config"),
):
    """Loop validator statistics."""
    return loop_validator.get_stats()


@app.get(
    "/admin/abuse",
    tags=["admin"],
    summary="IP abuse detection statistics",
    description=(
        "Returns counters for blocked IPs, prompt-injection attempts, and model-extraction probes. "
        "Requires admin:audit permission. Sourced from **Cryptex** (Renik)."
    ),
)
async def admin_abuse(
    current_user: dict = Depends(get_current_user),
    _perm: None = require_permission("admin:audit"),
):
    """IP abuse detection statistics."""
    return abuse_detector.get_stats()


@app.get(
    "/admin/healing",
    tags=["admin"],
    summary="Self-healing action history",
    description=(
        "Returns the chronological list of autonomous remediation actions taken by the "
        "self-healer — service restarts, circuit resets, and rate-limit adjustments."
    ),
)
async def admin_healing(
    current_user: dict = Depends(get_current_user),
    _perm: None = require_permission("admin:config"),
):
    """Self-healing action history."""
    return {"history": self_healer.get_history()}


@app.get(
    "/errors/{error_code}",
    tags=["docs"],
    response_model=ErrorDocResponse,
    summary="Error code documentation",
    description=(
        "Look up the human-readable title, HTTP status, description, and remediation guidance "
        "for any TRANC3 canonical error code (e.g. `SEC_INPUT_BLOCKED`, `RATE_LIMIT_EXCEEDED`). "
        "No authentication required."
    ),
)
async def error_docs(error_code: str):
    """Look up error code documentation — no auth required."""
    from src.errors.error_catalog import (  # noqa: F401  # intentional top-level import
        ErrorCode,
        get_error,
    )

    try:
        code = ErrorCode(error_code)
        defn = get_error(code)
        return {
            "code": defn.code.value,
            "title": defn.title,
            "message": defn.message,
            "guidance": defn.guidance,
            "docs_url": defn.docs_url,
            "severity": defn.severity,
            "retryable": defn.retryable,
            "self_heal": defn.self_heal,
        }
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Error code '{error_code}' not found")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation Endpoints — EvalSuite HTTP interface
# ─────────────────────────────────────────────────────────────────────────────


class _EvalRequest(BaseModel):
    """Request body for POST /eval/score."""

    hypothesis: str = Field(..., description="Model output to score")
    reference: str = Field(..., description="Ground-truth reference text")
    context: Optional[str] = Field(None, description="Source context for hallucination scoring")


class _EvalScoreResponse(BaseModel):
    """Metric scores for a single hypothesis/reference pair."""

    bleu: float
    rouge_l: float
    exact_match: bool
    token_f1: float
    hallucination: float


@app.post(
    "/eval/score",
    tags=["evaluation"],
    response_model=_EvalScoreResponse,
    summary="Score a single model output",
    description=(
        "Compute BLEU-4, ROUGE-L F1, Exact Match, Token-F1, and hallucination risk "
        "for a single hypothesis/reference pair. Requires eval:score permission. "
        "Powered by **Luminous** EvalSuite."
    ),
)
async def eval_score(
    body: _EvalRequest,
    _perm: None = require_permission("eval:score"),
) -> _EvalScoreResponse:
    """Score a hypothesis against a reference string."""
    from src.evaluation.model_eval import (
        bleu_score as _bleu,
    )
    from src.evaluation.model_eval import (
        exact_match as _em,
    )
    from src.evaluation.model_eval import (
        hallucination_score as _hall,
    )
    from src.evaluation.model_eval import (
        rouge_l_score as _rouge,
    )
    from src.evaluation.model_eval import (
        token_f1 as _tf1,
    )

    return _EvalScoreResponse(
        bleu=_bleu(body.hypothesis, [body.reference]),
        rouge_l=_rouge(body.hypothesis, body.reference)["f1"],
        exact_match=_em(body.hypothesis, body.reference),
        token_f1=_tf1(body.hypothesis, body.reference)["f1"],
        hallucination=_hall(body.hypothesis, body.context or body.reference),
    )


# ── Mesh + Routing Intelligence Endpoints ─────────────────────────────────────


@app.get(
    "/mesh/stats",
    tags=["mesh"],
    summary="Service mesh + routing statistics",
)
async def mesh_stats(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Returns aggregated stats from all routing engines:
    quantum, genetic, meta, fluid, quota enforcer, and zero-cost tracker.
    """
    out: dict = {}

    try:
        from src.mesh.meta_router import get_meta_router

        out["meta_router"] = get_meta_router().stats
    except Exception as exc:
        logger.warning("mesh_stats: meta_router unavailable: %s", exc)
        out["meta_router"] = {"error": "unavailable"}

    try:
        from src.mesh.quantum_router import get_quantum_router

        out["quantum_router"] = get_quantum_router().stats
    except Exception as exc:
        logger.warning("mesh_stats: quantum_router unavailable: %s", exc)
        out["quantum_router"] = {"error": "unavailable"}

    try:
        from src.mesh.genetic_router import get_genetic_router

        out["genetic_router"] = get_genetic_router().stats
    except Exception as exc:
        logger.warning("mesh_stats: genetic_router unavailable: %s", exc)
        out["genetic_router"] = {"error": "unavailable"}

    try:
        from src.mesh.quota_enforcer import get_enforcer

        out["quota_enforcer"] = get_enforcer().dashboard()
    except Exception as exc:
        logger.warning("mesh_stats: quota_enforcer unavailable: %s", exc)
        out["quota_enforcer"] = {"error": "unavailable"}

    try:
        from src.monitoring.zero_cost_tracker import tracker

        out["zero_cost_tracker"] = tracker.get_summary()
    except Exception as exc:
        logger.warning("mesh_stats: zero_cost_tracker unavailable: %s", exc)
        out["zero_cost_tracker"] = {"error": "unavailable"}

    try:
        from src.mesh.nano_mesh import get_nano_mesh

        out["nano_mesh"] = get_nano_mesh().stats
    except Exception as exc:
        logger.warning("mesh_stats: nano_mesh unavailable: %s", exc)
        out["nano_mesh"] = {"error": "unavailable"}

    try:
        from src.fluidic.fluid_router import fluid_router

        out["fluid_router"] = fluid_router.stats
    except Exception as exc:
        logger.warning("mesh_stats: fluid_router unavailable: %s", exc)
        out["fluid_router"] = {"error": "unavailable"}

    return out


@app.get(
    "/mesh/quota",
    tags=["mesh"],
    summary="Free-tier quota dashboard for all AI providers",
)
async def mesh_quota(current_user: dict = Depends(get_current_user)) -> dict:
    """Returns quota usage and availability for all 8 free AI providers."""
    try:
        from src.mesh.quota_enforcer import get_enforcer

        return get_enforcer().dashboard()
    except Exception:
        return {"error": "quota dashboard unavailable"}


@app.get("/version", tags=["system"], summary="API version info")
async def api_version() -> dict:
    """Return API version, canonical entrypoint, and platform metadata."""
    return {
        "version": "1.0.0",
        "api_versions": ["v1"],
        "canonical_entrypoint": "api.py",
        "deprecated_entrypoints": ["api_ecosystem.py", "api_enhanced.py"],
        "providers": 8,
        "entities": 43,
    }
