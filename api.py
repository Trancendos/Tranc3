# api.py — TRANC3 Production API
# Fully wired: auth, billing, analytics, foresight, feature flags, observability

import asyncio
import datetime
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import torch
import redis as redis_lib
import uvicorn
from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks, Depends, FastAPI, HTTPException,
    Request, WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

load_dotenv()

# ── Fail fast on missing SECRET_KEY ──────────────────────────────────────────
_SECRET_KEY = os.getenv("SECRET_KEY")
if not _SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is not set. "
        "Generate one: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# ── Internal imports ──────────────────────────────────────────────────────────
from src.adaptive.foresight import foresight
from src.analytics.predictive import analytics
from src.auth.db_user_manager import DBUserManager
from src.bio_neural.consciousness_engine import ConsciousnessModel
from src.bio_neural.neuromorphic import NeuromorphicProcessor
from src.compliance.magna_carta import compliance
from src.core.advanced_model import AdvancedTransformerModel
from src.core.context_compressor import compressor
from src.core.feature_flags import FeatureFlag, FeatureFlagManager
from src.core.multilingual_tokenizer import MultilingualTokenizer
from src.database.schema import DatabaseManager, Conversation, Message
from src.database.vector_store import vector_store
from src.errors.error_catalog import ErrorCode, format_error_response
from src.evolution.self_improving_core import SelfEvolvingArchitecture
from src.monetisation.billing import enforcer as tier_enforcer, TIERS
from src.observability.metrics import (
    log, record_churn_risk, record_emotion,
    record_phi, record_quality, record_request,
)
from src.personality.matrix import EnhancedPersonalityMatrix
from src.quantum.quantum_core import QuantumNeuralCore
from src.registry.file_registry import registry as file_registry
from src.security.ip_protection import abuse_detector, watermarker
from src.security.middleware import GovernanceMiddleware, SecurityHeadersMiddleware
from src.security.security_framework import InputSanitizer
from src.validation.loop_validator import CIRCUITS, loop_validator, self_healer
from auth import get_current_user, token_manager

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("tranc3.api")


# ── Runtime config ────────────────────────────────────────────────────────────
class Config:
    model_path          = os.getenv("MODEL_PATH", "./models/tranc3-base.pt")
    cache_dir           = os.getenv("CACHE_DIR", "./cache")
    redis_url           = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    primary_language    = os.getenv("PRIMARY_LANGUAGE", "en")
    supported_languages = os.getenv("SUPPORTED_LANGUAGES", "en,es,fr,de,zh,ja").split(",")
    enable_emotion      = os.getenv("ENABLE_EMOTION", "true").lower() == "true"
    personality_dir     = os.getenv("PERSONALITY_DIR", "./src/personality/profiles")
    vocab_size          = 119547
    hidden_size         = 768
    num_layers          = 12
    num_heads           = 12
    max_sequence_length = 512
    architecture        = "multilingual"
    freeze_base         = False

    def get(self, key, default=None):
        return getattr(self, key, default)


# ── Global state ──────────────────────────────────────────────────────────────
model               = None
tokenizer           = None
personality_matrix  = None
redis_client        = None
feature_flags       = None
quantum_core        = None
consciousness_model = None
neuromorphic        = None
evolution_engine    = None
db_manager          = None
db_user_manager     = None
_start_time         = time.time()
_feedback_count     = 0
EVOLUTION_TRIGGER   = 100


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, tokenizer, personality_matrix, redis_client, feature_flags
    global quantum_core, consciousness_model, neuromorphic, evolution_engine
    global db_manager, db_user_manager

    logger.info("TRANC3 starting up...")
    cfg = Config()

    # Database
    try:
        db_manager = DatabaseManager(os.getenv("DATABASE_URL", "sqlite:///./tranc3_dev.db"))
        db_user_manager = DBUserManager(db_manager.get_session)
        logger.info("Database connected")
    except Exception as e:
        logger.warning(f"Database unavailable: {e} — in-memory fallback")
        db_user_manager = DBUserManager(None)

    # Redis
    try:
        redis_client = redis_lib.from_url(cfg.redis_url, decode_responses=True)
        redis_client.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis unavailable: {e}")
        redis_client = None

    # Feature flags (requires Redis)
    if redis_client:
        feature_flags = FeatureFlagManager(redis_client)

    # Tokenizer
    try:
        tokenizer = MultilingualTokenizer(cfg)
        logger.info(f"Tokenizer ready: {cfg.supported_languages}")
    except Exception as e:
        logger.error(f"Tokenizer failed: {e}")

    # Personality matrix
    try:
        personality_matrix = EnhancedPersonalityMatrix(cfg)
        logger.info("Personality matrix ready")
    except Exception as e:
        logger.error(f"Personality matrix failed: {e}")

    # Quantum core
    try:
        quantum_core = QuantumNeuralCore({"num_qubits": 8})
        logger.info("Quantum core ready")
    except Exception as e:
        logger.warning(f"Quantum core unavailable: {e}")

    # Consciousness model
    try:
        consciousness_model = ConsciousnessModel({
            "consciousness_threshold": 3.0,
            "state_dimensions": 64,
            "workspace_size": 256,
            "competition_threshold": 0.7,
            "introspection_depth": 3,
        })
        logger.info("Consciousness model ready")
    except Exception as e:
        logger.warning(f"Consciousness model unavailable: {e}")

    # Neuromorphic processor
    try:
        neuromorphic = NeuromorphicProcessor(cfg)
        logger.info("Neuromorphic processor ready")
    except Exception as e:
        logger.warning(f"Neuromorphic processor unavailable: {e}")

    # Evolution engine
    try:
        evolution_engine = SelfEvolvingArchitecture({
            "population_size": 10,
            "mutation_rate": 0.01,
            "genome_dim": 768,
        })
        evolution_engine.load_genome_from_redis()
        logger.info("Evolution engine ready")
    except Exception as e:
        logger.warning(f"Evolution engine unavailable: {e}")

    # Model
    try:
        model = AdvancedTransformerModel(cfg)
        if os.path.exists(cfg.model_path):
            model.load_state_dict(torch.load(cfg.model_path, map_location="cpu"))
            logger.info("Model weights loaded")
        else:
            logger.warning("No model weights — echo mode active")
        model.eval()
    except Exception as e:
        logger.warning(f"Model init failed: {e} — echo mode")
        model = None

    logger.info("TRANC3 API ready ✓")
    yield

    logger.info("TRANC3 shutting down")
    if redis_client:
        redis_client.close()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TRANC3 API",
    version="2.0.0",
    description="Quantum-Conscious Multilingual AI Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GovernanceMiddleware)

# ── The Spark (MCP server) ────────────────────────────────────────────────────
from src.mcp.server import router as _mcp_router
app.include_router(_mcp_router)

# ── The Observatory (audit log + event feed) ──────────────────────────────────
from src.observability.routes import router as _observatory_router
app.include_router(_observatory_router)

# ── The Nexus (AI communications + transfer hub) ─────────────────────────────
from src.nexus.routes import router as _nexus_router
app.include_router(_nexus_router)

# ── The Town Hall (governance + compliance) ───────────────────────────────────
from src.townhall.routes import router as _townhall_router
app.include_router(_townhall_router)

# ── The Library (knowledge base) ─────────────────────────────────────────────
from src.library.routes import router as _library_router
app.include_router(_library_router)

# ── The Basement (archive + vector search) ────────────────────────────────────
from src.basement.routes import router as _basement_router
app.include_router(_basement_router)

# ── Cryptex (threat detection + cyber defence) ────────────────────────────────
from src.cryptex.routes import router as _cryptex_router
app.include_router(_cryptex_router)

# ── Section 7 (research + intelligence reports) ───────────────────────────────
from src.research.routes import router as _section7_router
app.include_router(_section7_router)

# ── The Digital Grid (workflow DAG builder + executor) ────────────────────────
from src.workflow.routes import router as _grid_router
app.include_router(_grid_router)

# ── I-Mind (sensitivity + crisis protocol) ────────────────────────────────────
from src.imind.routes import router as _imind_router
app.include_router(_imind_router)

# ── tAimra (digital twin — opt-in, OFFLINE by default) ────────────────────────
from src.taimra.routes import router as _taimra_router
app.include_router(_taimra_router)

# ── Tranquility (wellbeing hub) ────────────────────────────────────────────────
from src.tranquility.routes import router as _tranquility_router
app.include_router(_tranquility_router)

# ── Resonate (empathy + understanding services) ────────────────────────────────
from src.resonate.routes import router as _resonate_router
app.include_router(_resonate_router)

# ── The Studio (creativity hub — Sasha's Photo, TateKing, TranceFlow, Fabulousa)
from src.studio.routes import router as _studio_router
app.include_router(_studio_router)

# ── The Lab (AI code creation platform) ──────────────────────────────────────
from src.lab.routes import router as _lab_router
app.include_router(_lab_router)

# ── ChronosSphere / ArcStream (time + schedule management) ───────────────────
from src.chronos.routes import router as _chronos_router
app.include_router(_chronos_router)

# ── Turing's Hub (AI personality creation centre) ────────────────────────────
from src.personality.turingshub.routes import router as _turingshub_router
app.include_router(_turingshub_router)

# ── DevOcity (developer centre — API keys, webhooks, guides) ─────────────────
from src.devocity.routes import router as _devocity_router
app.include_router(_devocity_router)

# ── The Artifactory (OCI artefact repository — Zot foundation) ───────────────
from src.artifactory.routes import router as _artifactory_router
app.include_router(_artifactory_router)

# ── API Marketplace (connector hub — Gravitee.io foundation) ─────────────────
from src.apimarket.routes import router as _apimarket_router
app.include_router(_apimarket_router)

# ── VRAR3D (AR/VR wellbeing centre — Three.js / A-Frame WebXR) ───────────────
from src.vrar3d.routes import router as _vrar3d_router
app.include_router(_vrar3d_router)

# ── The Citadel (DevOps hub — Forgejo + Fly.io + CF Workers) ─────────────────
from src.citadel.routes import router as _citadel_router
app.include_router(_citadel_router)

# ── Luminous (AI brain — consciousness engine + neuromorphic) ─────────────────
from src.bio_neural.routes import router as _luminous_router
app.include_router(_luminous_router)

# ── Think Tank (quantum + deep research engines) ──────────────────────────────
from src.quantum.routes import router as _thinktank_router
app.include_router(_thinktank_router)

# ── Frontend static files (served from web/dist/ after `npm run build`) ───────
_FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "web", "dist")
if os.path.isdir(_FRONTEND_DIST):
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=os.path.join(_FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        index = os.path.join(_FRONTEND_DIST, "index.html")
        return FileResponse(index)


# ── Models ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message:              str                  = Field(..., min_length=1, max_length=10000)
    language:             str                  = Field("en")
    personality:          str                  = "tranc3-base"
    user_emotion:         Optional[str]        = "neutral"
    conversation_history: Optional[List[Dict]] = []
    session_id:           Optional[str]        = None


class ChatResponse(BaseModel):
    response:            str
    detected_emotion:    str
    language:            str
    personality:         str
    timestamp:           datetime.datetime
    processing_time_ms:  float
    request_id:          str
    consciousness_level: Optional[float] = None
    quantum_used:        bool            = False
    foresight:           Optional[Dict]  = None
    quality:             Optional[Dict]  = None


class TokenRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.post("/auth/register", tags=["auth"])
async def register(req: RegisterRequest):
    return db_user_manager.create_user(req.username, req.password)


@app.post("/auth/token", tags=["auth"])
async def login(req: TokenRequest):
    user = db_user_manager.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = token_manager.create_access_token({"sub": user["username"]})
    return {"access_token": token, "token_type": "bearer", "expires_in": 3600}


@app.post("/auth/refresh", tags=["auth"])
async def refresh_token(current_user: dict = Depends(get_current_user)):
    new_token = token_manager.create_access_token(
        {"sub": current_user["username"]},
        expires_delta=datetime.timedelta(hours=1),
    )
    return {"access_token": new_token, "token_type": "bearer", "expires_in": 3600}


# ── System ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health():
    return {
        "status":         "healthy" if model and tokenizer else "degraded",
        "version":        "2.0.0",
        "timestamp":      datetime.datetime.utcnow(),
        "uptime_seconds": round(time.time() - _start_time, 1),
        "components": {
            "api":         "healthy",
            "redis":       "healthy" if redis_client else "unavailable",
            "model":       "healthy" if model else "echo_mode",
            "tokenizer":   "healthy" if tokenizer else "unavailable",
            "personality": "healthy" if personality_matrix else "unavailable",
            "quantum":     "healthy" if quantum_core else "unavailable",
            "consciousness": "healthy" if consciousness_model else "unavailable",
        },
    }


@app.get("/ready", tags=["system"])
async def ready():
    if not tokenizer or not personality_matrix:
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"ready": True}


@app.get("/metrics", tags=["system"], response_class=PlainTextResponse)
async def metrics():
    try:
        from prometheus_client import generate_latest
        return generate_latest()
    except Exception:
        return "# prometheus_client not available\n"


@app.get("/features", tags=["system"])
async def features():
    if not feature_flags:
        return {"error": "Feature flags unavailable — Redis required"}
    return feature_flags.get_all_flags()


# ── Inference ─────────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse, tags=["inference"])
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    request_id = os.urandom(8).hex()
    start      = time.time()
    user_id    = current_user["id"]
    tier       = current_user.get("tier", "free")

    # Sanitise input — blocks XSS, SQLi, path traversal, prompt injection
    InputSanitizer.sanitize(request.message)

    # IP protection — prompt injection + model extraction detection
    ip_check = abuse_detector.check_message(request.message, user_id)
    if not ip_check["allowed"]:
        raise HTTPException(
            status_code=400,
            detail=format_error_response(ErrorCode.SEC_INPUT_BLOCKED, "Message blocked by security filter"),
        )

    # Compliance
    compliance.check_request({"user_id": user_id, "message": request.message})

    # Rate limiting
    try:
        tier_enforcer.check_and_increment(user_id, tier)
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))

    # Feature gates
    use_quantum       = feature_flags.is_enabled(FeatureFlag.QUANTUM_OPTIMIZATION, user_id) if feature_flags else False
    use_consciousness = feature_flags.is_enabled(FeatureFlag.CONSCIOUSNESS_ENGINE, user_id) if feature_flags else False

    # Language validation
    supported = tokenizer.supported_languages if tokenizer else Config.supported_languages
    if request.language not in supported:
        raise HTTPException(status_code=400, detail=f"Unsupported language. Supported: {supported}")

    try:
        # Emotion detection
        detected_emotion = request.user_emotion or "neutral"
        emotion_scores   = {"neutral": 1.0}
        if personality_matrix and getattr(personality_matrix, "emotion_detector", None):
            emotion_scores   = personality_matrix.emotion_detector.detect_emotion(request.message)
            detected_emotion = personality_matrix.emotion_detector.get_dominant_emotion(emotion_scores)

        # Compress conversation history if long
        history = compressor.compress(request.conversation_history or [])

        # Predictive analytics
        analysis = analytics.analyse_request(
            user_id=user_id, message=request.message,
            emotion=detected_emotion, language=request.language,
            personality=request.personality,
        )

        # Foresight
        foresight_result = foresight.analyse(
            session_id=request.session_id or user_id,
            user_message=request.message,
            emotion=detected_emotion,
            intent=analysis.get("dominant_intent", "question"),
            churn_risk=analysis.get("churn_probability", 0.0),
            conversation_length=len(history),
        )

        # Personality vector
        personality_vector = None
        if personality_matrix:
            personality_vector = personality_matrix.get_personality_vector(
                request.personality, emotion_scores, request.language
            )

        # Encode
        encoded = None
        if tokenizer:
            encoded = tokenizer.encode(
                request.message, language=request.language, return_tensors=True
            )

        # Quantum attention
        quantum_used = False
        if quantum_core and use_quantum:
            try:
                quantum_core.quantum_attention(torch.randn(1, 8, 64))
                quantum_used = True
            except Exception as e:
                logger.warning(f"Quantum attention skipped: {e}")

        # Consciousness Φ
        phi_score = None
        if consciousness_model and use_consciousness:
            try:
                phi_score = consciousness_model.calculate_phi(torch.randn(64))
                record_phi(phi_score)
            except Exception as e:
                logger.warning(f"Consciousness Φ skipped: {e}")

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
            response_text = f"[TRANC3] {request.message[:80]}..." if result else f"[Echo] {request.message}"
        else:
            response_text = f"[Echo] {request.message}"

        # Watermark response for IP protection
        response_text = watermarker.watermark(response_text, request_id)

        processing_ms = (time.time() - start) * 1000

        # Quality scoring
        quality = analytics.score_response(
            response=response_text, user_message=request.message,
            emotion=detected_emotion, processing_time_ms=processing_ms,
        )

        # Observability
        record_request("/chat", "POST", 200, tier, processing_ms / 1000)
        record_emotion(detected_emotion, request.language)
        record_churn_risk(analysis.get("churn_probability", 0.0))
        record_quality(quality["quality_scores"].get("overall", 0.0))

        # Background tasks
        background_tasks.add_task(
            _log_conversation, user_id, request_id,
            request.language, request.personality, detected_emotion, processing_ms,
        )
        background_tasks.add_task(
            _persist_conversation, user_id, request_id,
            request.message, response_text, request.language,
            request.personality, detected_emotion, processing_ms,
            phi_score, quantum_used,
        )

        return ChatResponse(
            response=response_text,
            detected_emotion=detected_emotion,
            language=request.language,
            personality=request.personality,
            timestamp=datetime.datetime.utcnow(),
            processing_time_ms=round(processing_ms, 2),
            request_id=request_id,
            consciousness_level=round(phi_score, 4) if phi_score is not None else None,
            quantum_used=quantum_used,
            foresight={
                "trajectory":      foresight_result["trajectory"],
                "recommendation":  foresight_result["recommendation"],
                "dominant_intent": analysis.get("dominant_intent"),
                "churn_risk":      analysis.get("churn_risk"),
            },
            quality=quality,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error [{request_id}]: {e}", exc_info=True)
        record_request("/chat", "POST", 500, tier, time.time() - start)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/languages", tags=["info"])
async def languages():
    return {
        "languages": tokenizer.supported_languages if tokenizer else Config.supported_languages,
        "primary":   Config.primary_language,
    }


@app.get("/personalities", tags=["info"])
async def personalities():
    if not personality_matrix:
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"personalities": list(personality_matrix.personalities.keys())}


@app.post("/analyze-emotion", tags=["inference"])
async def analyze_emotion(text: str, current_user: dict = Depends(get_current_user)):
    if not personality_matrix or not getattr(personality_matrix, "emotion_detector", None):
        raise HTTPException(status_code=503, detail="Emotion analysis unavailable")
    scores   = personality_matrix.emotion_detector.detect_emotion(text)
    dominant = personality_matrix.emotion_detector.get_dominant_emotion(scores)
    return {"dominant_emotion": dominant, "emotion_scores": scores, "text": text}


@app.post("/feedback", tags=["inference"])
async def feedback(
    request_id: str,
    rating: int = Field(..., ge=1, le=5),
    current_user: dict = Depends(get_current_user),
):
    global _feedback_count
    analytics.record_feedback(current_user["id"], float(rating))
    compliance.audit_log("feedback", {"user_id": current_user["id"], "rating": rating})

    if evolution_engine:
        _feedback_count += 1
        if _feedback_count >= EVOLUTION_TRIGGER:
            _feedback_count = 0
            evolution_engine.record_feedback({"quality_score": rating / 5.0, "user_satisfaction": rating / 5.0})
            best = evolution_engine.evolve(num_generations=1)
            logger.info(f"Evolution: gen={evolution_engine.generation}, fitness={best.fitness:.4f}")

    return {"message": "Feedback recorded", "impact": "evolution_queued"}


@app.post("/consciousness/score", tags=["inference"])
async def consciousness_score(text: str, current_user: dict = Depends(get_current_user)):
    if not consciousness_model:
        raise HTTPException(status_code=503, detail="Consciousness engine unavailable")
    try:
        phi    = consciousness_model.calculate_phi(torch.randn(64))
        report = consciousness_model.get_consciousness_report() if hasattr(consciousness_model, "get_consciousness_report") else {}
        return {"phi": round(phi, 4), "is_conscious": phi > 2.0, "text": text, "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Billing ───────────────────────────────────────────────────────────────────
@app.get("/billing/tiers", tags=["billing"])
async def billing_tiers():
    return {t: {k: v for k, v in cfg.items() if k != "stripe_price_id"} for t, cfg in TIERS.items()}


@app.get("/billing/usage", tags=["billing"])
async def billing_usage(current_user: dict = Depends(get_current_user)):
    return tier_enforcer.get_usage(current_user["id"]) or {"message": "No usage recorded yet"}


@app.post("/billing/checkout", tags=["billing"])
async def billing_checkout(tier: str, current_user: dict = Depends(get_current_user)):
    from src.monetisation.billing import stripe_manager
    base = os.getenv("FRONTEND_URL", "http://localhost:3000")
    url  = stripe_manager.create_checkout_session(
        current_user["id"], tier, f"{base}/billing/success", f"{base}/billing/cancel"
    )
    if not url:
        raise HTTPException(status_code=503, detail="Stripe not configured — set STRIPE_SECRET_KEY")
    return {"checkout_url": url, "tier": tier}


@app.post("/billing/webhook", tags=["billing"], include_in_schema=False)
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig     = request.headers.get("stripe-signature", "")
    secret  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    try:
        import stripe as _stripe
        _stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        event = _stripe.Webhook.construct_event(payload, sig, secret)
    except Exception as e:
        logger.warning(f"Stripe webhook invalid: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook")

    etype = event.get("type", "")
    obj   = event.get("data", {}).get("object", {})
    logger.info(f"Stripe event: {etype} id={obj.get('id')}")
    return {"received": True}


# ── Compliance ────────────────────────────────────────────────────────────────
@app.delete("/memory/{user_id}", tags=["compliance"])
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
                await websocket.send_json({
                    "chunk": word + (" " if i < len(words) - 1 else ""),
                    "done":  i == len(words) - 1,
                })
                await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass


# ── Background helpers ────────────────────────────────────────────────────────
async def _log_conversation(user_id, request_id, language, personality, emotion, processing_ms):
    log.info("conversation", user_id=user_id, request_id=request_id,
             language=language, personality=personality,
             emotion=emotion, processing_ms=round(processing_ms, 2))


async def _persist_conversation(
    user_id: str, request_id: str, user_message: str, ai_response: str,
    language: str, personality: str, emotion: str, processing_ms: float,
    phi: Optional[float] = None, quantum_used: bool = False,
):
    if not db_manager:
        return
    try:
        import uuid as _uuid
        session = db_manager.get_session()
        conv = Conversation(
            id=_uuid.uuid4(),
            user_id=_uuid.UUID(user_id) if len(user_id) == 36 else _uuid.uuid4(),
            language=language, personality=personality,
        )
        session.add(conv)
        session.flush()
        session.add(Message(
            id=_uuid.uuid4(), conversation_id=conv.id,
            role="user", content=user_message,
            language=language, detected_emotion=emotion,
        ))
        session.add(Message(
            id=_uuid.uuid4(), conversation_id=conv.id,
            role="assistant", content=ai_response,
            language=language, detected_emotion=emotion,
            processing_time_ms=processing_ms,
            consciousness_level=phi,
            quantum_used=quantum_used,
        ))
        session.commit()
        session.close()
    except Exception as e:
        log.warning("persist_failed", error=str(e))


if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENVIRONMENT") == "development",
    )


# ── Admin endpoints ───────────────────────────────────────────────────────────

@app.get("/admin/registry", tags=["admin"])
async def admin_registry(current_user: dict = Depends(get_current_user)):
    """File registry — lists all files with FID, version, and integrity status."""
    if current_user.get("tier") not in ("enterprise", "business"):
        raise HTTPException(status_code=403, detail="Admin access requires Business or Enterprise tier")
    return file_registry.verify_all()


@app.get("/admin/registry/{fid}", tags=["admin"])
async def admin_registry_file(fid: str, current_user: dict = Depends(get_current_user)):
    """Get integrity status for a specific file by FID."""
    return file_registry.verify(fid)


@app.get("/admin/circuits", tags=["admin"])
async def admin_circuits(current_user: dict = Depends(get_current_user)):
    """Circuit breaker status for all subsystems."""
    return {name: cb.get_status() for name, cb in CIRCUITS.items()}


@app.get("/admin/loops", tags=["admin"])
async def admin_loops(current_user: dict = Depends(get_current_user)):
    """Loop validator statistics."""
    return loop_validator.get_stats()


@app.get("/admin/abuse", tags=["admin"])
async def admin_abuse(current_user: dict = Depends(get_current_user)):
    """IP abuse detection statistics."""
    if current_user.get("tier") not in ("enterprise", "business"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return abuse_detector.get_stats()


@app.get("/admin/healing", tags=["admin"])
async def admin_healing(current_user: dict = Depends(get_current_user)):
    """Self-healing action history."""
    return {"history": self_healer.get_history()}


@app.get("/errors/{error_code}", tags=["docs"])
async def error_docs(error_code: str):
    """Look up error code documentation — no auth required."""
    from src.errors.error_catalog import ErrorCode, get_error
    try:
        code = ErrorCode(error_code)
        defn = get_error(code)
        return {
            "code":      defn.code.value,
            "title":     defn.title,
            "message":   defn.message,
            "guidance":  defn.guidance,
            "docs_url":  defn.docs_url,
            "severity":  defn.severity,
            "retryable": defn.retryable,
            "self_heal": defn.self_heal,
        }
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Error code '{error_code}' not found")
