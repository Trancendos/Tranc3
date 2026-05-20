# src/database/schema.py
# TRANC3 Complete Database Schema (SQLAlchemy + Alembic)

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    Index,
    BigInteger,
    text,
    TypeDecorator,
    CHAR,
)
from sqlalchemy.orm import declarative_base, relationship, Session
from datetime import datetime
import uuid


# Cross-dialect UUID type — stores as CHAR(36) on any backend,
# uses native UUID where available (PostgreSQL).
class _GUID(TypeDecorator):
    """Platform-independent GUID type (replaces PostgreSQL-only UUID)."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID

            return dialect.type_descriptor(PG_UUID())
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        return str(value) if isinstance(value, uuid.UUID) else value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return value


Base = declarative_base()


# ============================================================
# USERS
# ============================================================
class User(Base):
    __tablename__ = "users"

    id = Column(_GUID(), primary_key=True, default=uuid.uuid4)
    username = Column(String(64), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    tier = Column(String(20), default="free")  # free, pro, enterprise
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    preferences = Column(JSON, default={})
    metadata_ = Column("metadata", JSON, default={})

    # Relationships
    conversations = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    api_keys = relationship(
        "APIKey", back_populates="user", cascade="all, delete-orphan"
    )
    feedback = relationship("Feedback", back_populates="user")

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
    )


# ============================================================
# CONVERSATIONS
# ============================================================
class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(_GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(_GUID(), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=True)
    language = Column(String(10), default="en")
    personality = Column(String(64), default="tranc3-base")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    metadata_ = Column("metadata", JSON, default={})

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_conversations_user_id", "user_id"),
        Index("ix_conversations_created_at", "created_at"),
    )


# ============================================================
# MESSAGES
# ============================================================
class Message(Base):
    __tablename__ = "messages"

    id = Column(_GUID(), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(_GUID(), ForeignKey("conversations.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    language = Column(String(10), default="en")
    detected_emotion = Column(String(50), nullable=True)
    processing_time_ms = Column(Float, nullable=True)
    consciousness_level = Column(Float, nullable=True)
    quantum_used = Column(Boolean, default=False)
    tokens_used = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    advanced_metrics = Column(JSON, default={})
    embedding = Column(JSON, nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    feedback = relationship("Feedback", back_populates="message")

    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_created_at", "created_at"),
    )


# ============================================================
# API KEYS
# ============================================================
class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(_GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(_GUID(), ForeignKey("users.id"), nullable=False)
    key_hash = Column(String(255), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    tier = Column(String(20), default="free")
    rate_limit = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    usage_count = Column(BigInteger, default=0)
    permissions = Column(JSON, default={})

    user = relationship("User", back_populates="api_keys")


# ============================================================
# FEEDBACK
# ============================================================
class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(_GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(_GUID(), ForeignKey("users.id"), nullable=False)
    message_id = Column(_GUID(), ForeignKey("messages.id"), nullable=True)
    rating = Column(Integer, nullable=False)  # 1-5
    categories = Column(JSON, default=[])
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)
    evolution_applied = Column(Boolean, default=False)

    user = relationship("User", back_populates="feedback")
    message = relationship("Message", back_populates="feedback")


# ============================================================
# EVOLUTION EVENTS
# ============================================================
class EvolutionEvent(Base):
    __tablename__ = "evolution_events"

    id = Column(_GUID(), primary_key=True, default=uuid.uuid4)
    generation = Column(Integer, nullable=False)
    fitness_score = Column(Float, nullable=False)
    mutation_rate = Column(Float, nullable=False)
    population_size = Column(Integer, nullable=False)
    improvements = Column(JSON, default={})
    applied_at = Column(DateTime, default=datetime.utcnow)
    model_version = Column(String(50), nullable=False)
    metrics_before = Column(JSON, default={})
    metrics_after = Column(JSON, default={})


# ============================================================
# QUANTUM SESSIONS
# ============================================================
class QuantumSession(Base):
    __tablename__ = "quantum_sessions"

    id = Column(_GUID(), primary_key=True, default=uuid.uuid4)
    request_id = Column(String(64), nullable=False)
    num_qubits = Column(Integer, nullable=False)
    circuit_type = Column(String(50), nullable=False)
    phi_score = Column(Float, nullable=True)
    execution_time_ms = Column(Float, nullable=False)
    shots = Column(Integer, nullable=False)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    circuit_data = Column(JSON, default={})


# ============================================================
# SYSTEM METRICS
# ============================================================
class SystemMetric(Base):
    __tablename__ = "system_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    labels = Column(JSON, default={})
    recorded_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_system_metrics_name_time", "metric_name", "recorded_at"),
    )


# ============================================================
# DATABASE MANAGER
# ============================================================
class DatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        from sqlalchemy.orm import sessionmaker

        SessionLocal = sessionmaker(bind=self.engine)
        return SessionLocal()

    def health_check(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
