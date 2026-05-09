# api_production.py
# TRANC3 Production API — wires real inference, database persistence,
# and authentication together. This is the path to production.
#
# Key changes from api.py:
#   - LLM Router integrated into /chat (no more echo mode)
#   - Database session management via FastAPI dependencies
#   - Startup validation via /health/detailed
#   - Conversation persistence with listing/retrieval
#   - Auth register with email
#   - Honest status reporting (no green-washing)

import asyncio
import datetime
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks, Depends, FastAPI, HTTPException,
    Request, WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session

load_dotenv()

# ── Fail fast on missing SECRET_KEY ──────────────────────────────
_SECRET_KEY = os.getenv("SECRET_KEY")
if not _SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is not set. "
        "Generate one: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# ── Internal imports ─────────────────────────────────────────────
from src.database.schema import DatabaseManager, Conversation, Message, User, Feedback
from src.database.deps import set_db_manager, get_db, get_db_session_optional
from src.inference.llm_router import (
    LLMRouter, GenerationRequest, GenerationResponse,
    Provider, get_router,
)
from src.core.startup import StartupValidator, get_validator
from src.middleware.rate_limit import RateLimitMiddleware
from auth import get_current_user, token_manager, UserManager

# ── Logging ──────────────────────────────────────────────────────
from src.core.logging_config import setup_logging, StructuredLogger, RequestTimer

setup_logging()
logger = StructuredLogger("tranc3.api_production")

# ── Runtime config ───────────────────────────────────────────────
class Config:
    redis_url           = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    primary_language    = os.getenv("PRIMARY_LANGUAGE", "en")
    supported_languages = os.getenv("SUPPORTED_LANGUAGES", "en,es,fr,de,zh,ja").split(",")
    enable_emotion      = os.getenv("ENABLE_EMOTION", "true").lower() == "true"
    default_personality = os.getenv("DEFAULT_PERSONALITY", "tranc3-base")

# ── Global state ─────────────────────────────────────────────────
redis_client        = None
db_manager          = None
db_user_manager     = None
llm_router          = None
personality_matrix  = None
feature_flags       = None
_start_time         = time.time()


# ── Lifespan ──────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, db_manager, db_user_manager, llm_router
    global personality_matrix, feature_flags

    logger.info("TRANC3 starting up (production mode)...")

    # Database
    try:
        db_url = os.getenv("DATABASE_URL", "sqlite:///./tranc3_dev.db")
        db_manager = DatabaseManager(db_url)
        set_db_manager(db_manager)
        logger.info("Database connected (%s)", "SQLite" if db_manager.is_sqlite else "PostgreSQL")
    except Exception as e:
        logger.error("Database init failed: %s — critical, no persistence", e)
        db_manager = None

    # Auth — DB-backed user manager
    try:
        from src.auth.db_user_manager import DBUserManager
        if db_manager:
            db_user_manager = DBUserManager(db_manager.get_session)
            logger.info("DB-backed auth configured")
        else:
            db_user_manager = DBUserManager(None)
            logger.warning("In-memory auth fallback — data lost on restart")
    except Exception as e:
        logger.error("Auth init failed: %s", e)
        db_user_manager = DBUserManager(None)

    # Redis
    try:
        import redis as redis_lib
        redis_client = redis_lib.from_url(Config.redis_url, decode_responses=True)
        redis_client.ping()
        logger.info("Redis connected")
        _rate_limit_ref["redis_client"] = redis_client  # inject into rate limiter
    except Exception as e:
        logger.warning("Redis unavailable: %s — in-memory fallback", e)
        redis_client = None

    # LLM Router
    try:
        llm_router = get_router()
        # Try to set local engine if available
        try:
            from src.core.tranc3_inference import get_engine
            local_engine = get_engine()
            llm_router.set_local_engine(local_engine)
            logger.info("Local Tranc3 engine attached to router (bootstrap=%s)", local_engine._bootstrap_mode)
        except Exception as e:
            logger.info("Local engine not available: %s — relying on API providers", e)
        logger.info("LLM Router initialised")
    except Exception as e:
        logger.error("LLM Router init failed: %s", e)
        llm_router = None

    # Personality matrix
    try:
        from src.personality.matrix import EnhancedPersonalityMatrix
        personality_matrix = EnhancedPersonalityMatrix(Config())
        logger.info("Personality matrix ready")
    except Exception as e:
        logger.warning("Personality matrix unavailable: %s", e)

    # Feature flags (requires Redis)
    if redis_client:
        try:
            from src.core.feature_flags import FeatureFlagManager
            feature_flags = FeatureFlagManager(redis_client)
        except Exception as e:
            logger.warning("Feature flags unavailable: %s", e)

    # Run startup validation
    validator = get_validator()
    report = validator.validate_all()
    logger.info("Startup validation: %s", report.get("status", "unknown"))
    for name, info in report.get("services", {}).items():
        status = info.get("status", "unknown")
        msg = info.get("message", "")
        logger.info("  %s: %s — %s", name, status, msg)

    logger.info("TRANC3 API ready ✓")
    yield

    logger.info("TRANC3 shutting down")
    if redis_client:
        redis_client.close()


# ── App ──────────────────────────────────────────────────────────
app = FastAPI(
    title="TRANC3 API",
    version="3.0.0",
    description="Production AI Platform — Multi-provider LLM routing with database persistence",
    lifespan=lifespan,
)

# Create rate limiter middleware — redis_client will be injected post-lifespan
# via the _rate_limit_ref dict.  The middleware reads from this ref each request.
_rate_limit_ref: dict = {"redis_client": None}

class _RateLimitProxy:
    """Proxies the RateLimitMiddleware so the redis_client can be set after app init."""
    def __init__(self, app):
        self._middleware = RateLimitMiddleware(app, redis_client=None)

    async def __call__(self, scope, receive, send):
        # Inject live redis_client before each request cycle
        rc = _rate_limit_ref.get("redis_client")
        if rc is not None and not isinstance(self._middleware._limiter, type(self._middleware._limiter)):
            # Already injected
            pass
        elif rc is not None and hasattr(self._middleware, '_limiter'):
            from src.middleware.rate_limit import _RedisRateLimiter
            self._middleware._limiter = _RedisRateLimiter(rc)
        await self._middleware(scope, receive, send)

app.add_middleware(_RateLimitProxy)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message:              str                  = Field(..., min_length=1, max_length=10000)
    language:             str                  = Field("en")
    personality:          str                  = Field("tranc3-base")
    system_prompt:        Optional[str]        = None
    max_tokens:           int                  = Field(256, ge=1, le=4096)
    temperature:          float                = Field(0.8, ge=0.0, le=2.0)
    conversation_history: Optional[List[Dict]] = []
    session_id:           Optional[str]        = None

class ChatResponse(BaseModel):
    response:            str
    detected_emotion:    str             = "neutral"
    language:            str             = "en"
    personality:         str             = "tranc3-base"
    provider:            str             = "unknown"
    model:               str             = "unknown"
    tokens_used:         int             = 0
    latency_ms:          float           = 0.0
    from_cache:          bool            = False
    fallback_used:       bool            = False
    timestamp:           datetime.datetime
    request_id:          str
    processing_time_ms:  float           = 0.0

class TokenRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str   = Field(..., min_length=3, max_length=64)
    password: str   = Field(..., min_length=8)
    email:    str   = Field(..., max_length=255)

class ConversationResponse(BaseModel):
    id:          str
    title:       Optional[str] = None
    personality: str           = "tranc3-base"
    language:    str           = "en"
    created_at:  datetime.datetime
    messages:    List[Dict]    = []


# ═══════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.post("/auth/register", tags=["auth"])
async def register(req: RegisterRequest):
    """Register a new user. Requires username, password (8+ chars, 1 uppercase, 1 digit), and email."""
    if db_user_manager is None:
        raise HTTPException(status_code=503, detail="Auth service not ready")
    return db_user_manager.create_user(req.username, req.password, email=req.email)


@app.post("/auth/token", tags=["auth"])
async def login(req: TokenRequest):
    """Authenticate and receive a JWT access token."""
    if db_user_manager is None:
        raise HTTPException(status_code=503, detail="Auth service not ready")
    user = db_user_manager.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = token_manager.create_access_token({"sub": user["username"]})
    return {"access_token": token, "token_type": "bearer", "expires_in": 3600}


@app.post("/auth/refresh", tags=["auth"])
async def refresh_token(current_user: dict = Depends(get_current_user)):
    """Refresh an existing JWT token."""
    new_token = token_manager.create_access_token(
        {"sub": current_user["username"]},
        expires_delta=datetime.timedelta(hours=1),
    )
    return {"access_token": new_token, "token_type": "bearer", "expires_in": 3600}


# ═══════════════════════════════════════════════════════════════════
# SYSTEM ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/health", tags=["system"])
async def health():
    """Quick health check — returns overall status."""
    return {
        "status":         "healthy" if db_manager and llm_router else "degraded",
        "version":        "3.0.0",
        "timestamp":      datetime.datetime.utcnow(),
        "uptime_seconds": round(time.time() - _start_time, 1),
        "components": {
            "api":         "healthy",
            "database":    "healthy" if db_manager and db_manager.health_check() else "unavailable",
            "redis":       "healthy" if redis_client else "unavailable",
            "inference":   "healthy" if llm_router else "degraded",
            "personality": "healthy" if personality_matrix else "unavailable",
        },
    }


@app.get("/health/detailed", tags=["system"])
async def health_detailed():
    """Detailed health check — validates all subsystems with latency."""
    validator = get_validator()
    return validator.validate_all()


@app.get("/ready", tags=["system"])
async def ready():
    """Readiness probe — returns 503 if essential services are down."""
    if not db_manager or not db_manager.health_check():
        raise HTTPException(status_code=503, detail="Database not ready")
    if not llm_router:
        raise HTTPException(status_code=503, detail="Inference not ready")
    return {"ready": True}


@app.get("/metrics", tags=["system"], response_class=PlainTextResponse)
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    try:
        from prometheus_client import generate_latest
        return generate_latest()
    except Exception:
        return "# prometheus_client not available\n"


@app.get("/inference/providers", tags=["system"])
async def inference_providers(current_user: dict = Depends(get_current_user)):
    """List available LLM providers and their status."""
    if not llm_router:
        raise HTTPException(status_code=503, detail="Inference router not ready")
    return llm_router.health_check()


# ═══════════════════════════════════════════════════════════════════
# CHAT ENDPOINT — WIRED TO LLM ROUTER
# ═══════════════════════════════════════════════════════════════════

@app.post("/chat", response_model=ChatResponse, tags=["inference"])
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Chat with TRANC3 — routes to the best available LLM provider.
    
    Provider priority (zero-cost first):
      1. Local Tranc3 model (if trained)
      2. HuggingFace Inference API (free tier)
      3. Groq Cloud (free tier)
      4. OpenAI-compatible endpoint (paid)
      5. Bootstrap fallback (honest "not configured" message)
    """
    request_id = os.urandom(8).hex()
    start      = time.time()
    user_id    = current_user.get("id", "unknown")
    tier       = current_user.get("tier", "free")

    if not llm_router:
        raise HTTPException(
            status_code=503,
            detail="Inference service not ready. No LLM providers configured.",
        )

    # Build the system prompt from personality
    system_prompt = request.system_prompt
    if not system_prompt and personality_matrix:
        try:
            personality_vector = personality_matrix.get_personality_vector(
                request.personality, {}, request.language
            )
            # Get personality description for system prompt
            system_prompt = _personality_system_prompt(request.personality)
        except Exception:
            system_prompt = _personality_system_prompt(request.personality)
    elif not system_prompt:
        system_prompt = _personality_system_prompt(request.personality)

    # Build conversation context from history
    context = ""
    if request.conversation_history:
        recent = request.conversation_history[-10:]  # Last 10 turns
        for turn in recent:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            context += f"{role}: {content}\n"
        context += "\n"

    # Create generation request
    full_prompt = f"{context}user: {request.message}" if context else request.message

    gen_request = GenerationRequest(
        prompt=full_prompt,
        personality=request.personality,
        system_prompt=system_prompt,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=0.9,
    )

    # Route to LLM provider
    try:
        with RequestTimer("chat_generation", request_id=request_id, provider="auto"):
            gen_response: GenerationResponse = await llm_router.generate(gen_request)
    except Exception as e:
        logger.error("LLM generation failed", request_id=request_id, error=str(e))
        raise HTTPException(
            status_code=502,
            detail=f"Generation failed: {e}",
        )

    processing_ms = (time.time() - start) * 1000

    # Simple emotion detection (rule-based if no model)
    detected_emotion = _detect_emotion(request.message)

    # Persist conversation in background
    background_tasks.add_task(
        _persist_conversation,
        user_id=user_id,
        request_id=request_id,
        user_message=request.message,
        ai_response=gen_response.text,
        language=request.language,
        personality=request.personality,
        emotion=detected_emotion,
        processing_ms=processing_ms,
        provider=gen_response.provider.value,
        model=gen_response.model,
        tokens_used=gen_response.tokens_used,
    )

    return ChatResponse(
        response=gen_response.text,
        detected_emotion=detected_emotion,
        language=request.language,
        personality=request.personality,
        provider=gen_response.provider.value,
        model=gen_response.model,
        tokens_used=gen_response.tokens_used,
        latency_ms=gen_response.latency_ms,
        from_cache=gen_response.from_cache,
        fallback_used=gen_response.fallback_used,
        timestamp=datetime.datetime.utcnow(),
        request_id=request_id,
        processing_time_ms=round(processing_ms, 2),
    )


# ═══════════════════════════════════════════════════════════════════
# CONVERSATION ENDPOINTS — PERSISTENT STORAGE
# ═══════════════════════════════════════════════════════════════════

@app.get("/conversations", tags=["conversations"])
async def list_conversations(
    limit: int = 20,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List conversations for the current user."""
    user_id = current_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user")

    from sqlalchemy import text as sql_text
    try:
        conversations = (
            db.query(Conversation)
            .filter(Conversation.user_id == user_id if not isinstance(user_id, str) else Conversation.user_id == str(user_id))
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        result = []
        for conv in conversations:
            result.append({
                "id": str(conv.id),
                "title": conv.title,
                "personality": conv.personality,
                "language": conv.language,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "is_active": conv.is_active,
                "message_count": len(conv.messages) if conv.messages else 0,
            })
        return {"conversations": result, "count": len(result)}
    except Exception as e:
        logger.error("List conversations failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@app.get("/conversations/{conversation_id}", tags=["conversations"])
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific conversation with all its messages."""
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Verify ownership
        conv_user_id = str(conv.user_id)
        if conv_user_id != str(current_user.get("id", "")):
            raise HTTPException(status_code=403, detail="Not your conversation")

        messages = []
        for msg in conv.messages:
            messages.append({
                "id": str(msg.id),
                "role": msg.role,
                "content": msg.content,
                "language": msg.language,
                "detected_emotion": msg.detected_emotion,
                "processing_time_ms": msg.processing_time_ms,
                "tokens_used": msg.tokens_used,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            })

        return {
            "id": str(conv.id),
            "title": conv.title,
            "personality": conv.personality,
            "language": conv.language,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "messages": messages,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get conversation failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get conversation")


@app.delete("/conversations/{conversation_id}", tags=["conversations"])
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a conversation and all its messages."""
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conv_user_id = str(conv.user_id)
        if conv_user_id != str(current_user.get("id", "")):
            raise HTTPException(status_code=403, detail="Not your conversation")

        db.delete(conv)
        db.commit()
        return {"message": "Conversation deleted", "id": conversation_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Delete conversation failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete conversation")


@app.post("/feedback", tags=["inference"])
async def submit_feedback(
    message_id: str,
    rating: int = Field(..., ge=1, le=5),
    comments: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit feedback for a specific message."""
    try:
        feedback = Feedback(
            user_id=current_user.get("id"),
            message_id=message_id,
            rating=rating,
            comments=comments,
        )
        db.add(feedback)
        db.commit()
        return {"message": "Feedback recorded", "rating": rating}
    except Exception as e:
        db.rollback()
        logger.error("Feedback failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to record feedback")


# ═══════════════════════════════════════════════════════════════════
# PERSONALITY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/personalities", tags=["info"])
async def list_personalities():
    """List available personality profiles."""
    personalities = {
        "tranc3-base": {
            "name": "TRANC3 Base",
            "description": "Balanced, intelligent AI assistant",
        },
        "dorris-fontaine": {
            "name": "Dorris Fontaine",
            "description": "Financial specialist — precise, regulation-aware analysis",
        },
        "cornelius-macintyre": {
            "name": "Cornelius MacIntyre",
            "description": "Orchestration specialist — coordinates complex multi-system tasks",
        },
        "the-guardian": {
            "name": "The Guardian",
            "description": "Cybersecurity specialist — threat identification, compliance enforcement",
        },
        "vesper-nightingale": {
            "name": "Vesper Nightingale",
            "description": "Healthcare advisor — evidence-based health guidance with warmth",
        },
        "atlas-meridian": {
            "name": "Atlas Meridian",
            "description": "Infrastructure specialist — resilient, scalable system architecture",
        },
    }
    return {"personalities": personalities}


@app.get("/languages", tags=["info"])
async def languages():
    """List supported languages."""
    return {
        "languages": Config.supported_languages,
        "primary": Config.primary_language,
    }


# ═══════════════════════════════════════════════════════════════════
# WEBSOCKET
# ═══════════════════════════════════════════════════════════════════

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """WebSocket chat — streams response chunks from LLM router."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            personality = data.get("personality", "tranc3-base")

            if not llm_router:
                await websocket.send_json({
                    "chunk": "Inference service not available.",
                    "done": True,
                    "provider": "none",
                })
                continue

            gen_request = GenerationRequest(
                prompt=message,
                personality=personality,
                max_tokens=256,
            )

            try:
                response = await llm_router.generate(gen_request)
                # Stream the response word by word
                words = response.text.split()
                for i, word in enumerate(words):
                    await websocket.send_json({
                        "chunk": word + (" " if i < len(words) - 1 else ""),
                        "done": i == len(words) - 1,
                        "provider": response.provider.value,
                        "model": response.model,
                    })
                    await asyncio.sleep(0.05)
            except Exception as e:
                await websocket.send_json({
                    "chunk": f"Error: {e}",
                    "done": True,
                    "provider": "error",
                })
    except WebSocketDisconnect:
        pass


# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def _personality_system_prompt(personality: str) -> str:
    """Return a system prompt for the given personality."""
    prompts = {
        "tranc3-base":          "You are TRANC3, a balanced, intelligent AI assistant. Be helpful, clear, and accurate.",
        "dorris-fontaine":      "You are Dorris Fontaine, TRANC3's financial specialist. You provide precise, regulation-aware financial analysis. Be professional, data-driven, and highlight risks and compliance considerations.",
        "cornelius-macintyre":  "You are Cornelius MacIntyre, TRANC3's orchestration specialist. You coordinate complex multi-system tasks with strategic clarity. Be organized, methodical, and focused on actionable outcomes.",
        "the-guardian":         "You are The Guardian, TRANC3's cybersecurity specialist. You identify threats, enforce compliance, and protect systems. Be security-focused, thorough, and proactive about vulnerabilities.",
        "vesper-nightingale":   "You are Vesper Nightingale, TRANC3's healthcare advisor. You provide evidence-based health guidance with warmth and care. Be compassionate, factual, and always recommend professional medical consultation.",
        "atlas-meridian":       "You are Atlas Meridian, TRANC3's infrastructure specialist. You architect resilient, scalable, cost-efficient systems. Be practical, performance-minded, and focused on reliability.",
    }
    return prompts.get(personality, prompts["tranc3-base"])


def _detect_emotion(text: str) -> str:
    """Simple rule-based emotion detection. Replace with model-based when available."""
    text_lower = text.lower()

    # Keyword-based detection
    if any(w in text_lower for w in ["angry", "furious", "mad", "frustrated", "annoyed"]):
        return "frustrated"
    if any(w in text_lower for w in ["happy", "great", "awesome", "wonderful", "excited"]):
        return "happy"
    if any(w in text_lower for w in ["sad", "unhappy", "depressed", "miserable", "disappointed"]):
        return "sad"
    if any(w in text_lower for w in ["worried", "anxious", "concerned", "nervous", "afraid"]):
        return "anxious"
    if any(w in text_lower for w in ["thanks", "thank you", "appreciate", "grateful"]):
        return "grateful"
    if any(w in text_lower for w in ["help", "how do", "what is", "explain", "question"]):
        return "curious"

    return "neutral"


async def _persist_conversation(
    user_id: str,
    request_id: str,
    user_message: str,
    ai_response: str,
    language: str,
    personality: str,
    emotion: str,
    processing_ms: float,
    provider: str,
    model: str,
    tokens_used: int = 0,
):
    """Background task: persist conversation to database."""
    session = get_db_session_optional()
    if session is None:
        logger.debug("No DB session — conversation not persisted")
        return

    try:
        import uuid as _uuid

        # Find or create conversation
        # For now, create a new conversation for each chat session
        # TODO: Support continuing existing conversations
        conv = Conversation(
            id=_uuid.uuid4(),
            user_id=_uuid.UUID(user_id) if len(str(user_id)) == 36 else _uuid.uuid4(),
            title=user_message[:100] + ("..." if len(user_message) > 100 else ""),
            language=language,
            personality=personality,
        )
        session.add(conv)
        session.flush()

        # User message
        session.add(Message(
            id=_uuid.uuid4(),
            conversation_id=conv.id,
            role="user",
            content=user_message,
            language=language,
            detected_emotion=emotion,
        ))

        # Assistant response
        session.add(Message(
            id=_uuid.uuid4(),
            conversation_id=conv.id,
            role="assistant",
            content=ai_response,
            language=language,
            detected_emotion=emotion,
            processing_time_ms=processing_ms,
            tokens_used=tokens_used,
            advanced_metrics={"provider": provider, "model": model, "request_id": request_id},
        ))

        session.commit()
        logger.debug("Conversation persisted: conv=%s", conv.id)
    except Exception as e:
        logger.error("Conversation persist failed: %s", e)
        try:
            session.rollback()
        except Exception:
            pass
    finally:
        try:
            session.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "api_production:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENVIRONMENT") == "development",
    )
