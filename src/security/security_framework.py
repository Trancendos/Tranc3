# src/security/security_framework.py
# TRANC3 Complete Security Framework

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import redis
from fastapi import HTTPException
from fastapi.security import HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================
_JWT_SECRET = os.getenv("JWT_SECRET")
if not _JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET environment variable is not set. "
        "Tokens would be invalidated on every restart. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
SECRET_KEY = _JWT_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()


# ============================================================
# PASSWORD MANAGER
# ============================================================
class PasswordManager:
    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)

    @staticmethod
    def validate_strength(password: str) -> Dict[str, bool]:
        return {
            "min_length": len(password) >= 12,
            "has_upper": any(c.isupper() for c in password),
            "has_lower": any(c.islower() for c in password),
            "has_digit": any(c.isdigit() for c in password),
            "has_special": any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password),
            "not_common": password not in ["password123", "admin123", "tranc3123"],
        }


# ============================================================
# JWT MANAGER
# ============================================================
class JWTManager:
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + (
            expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire, "type": "access", "iat": datetime.utcnow()})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def create_refresh_token(data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh", "iat": datetime.utcnow()})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict:
        try:
            return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from None

    @staticmethod
    def verify_token_type(payload: dict, expected_type: str):
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=401, detail="Invalid token type")


# ============================================================
# RATE LIMITER
# ============================================================
class RateLimiter:
    TIER_LIMITS = {
        "free": {"requests": 100, "window": 3600},
        "pro": {"requests": 1000, "window": 3600},
        "enterprise": {"requests": 100000, "window": 3600},
    }

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def check_rate_limit(self, user_id: str, tier: str = "free") -> Dict:
        limits = self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"])
        key = f"ratelimit:{user_id}:{tier}"
        current = self.redis.incr(key)
        if current == 1:
            self.redis.expire(key, limits["window"])
        ttl = self.redis.ttl(key)
        allowed = current <= limits["requests"]
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(ttl),
                    "X-RateLimit-Limit": str(limits["requests"]),
                },
            )
        return {
            "allowed": True,
            "remaining": max(0, limits["requests"] - current),
            "reset_in": ttl,
        }


# ============================================================
# API KEY MANAGER
# ============================================================
class APIKeyManager:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def generate_api_key(self) -> str:
        return f"tranc3_{secrets.token_urlsafe(32)}"

    def hash_api_key(self, key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def validate_api_key(self, key: str) -> Optional[Dict]:
        key_hash = self.hash_api_key(key)
        cached = self.redis.get(f"apikey:{key_hash}")
        if cached:
            import json

            return json.loads(cached)
        return None

    def cache_api_key(self, key_hash: str, user_data: Dict, ttl: int = 3600):
        import json

        self.redis.setex(f"apikey:{key_hash}", ttl, json.dumps(user_data))

    def revoke_api_key(self, key: str):
        key_hash = self.hash_api_key(key)
        self.redis.delete(f"apikey:{key_hash}")


# ============================================================
# INPUT SANITIZER
# ============================================================
class InputSanitizer:
    BLOCKED_PATTERNS = [
        "<script",
        "javascript:",
        "data:text/html",
        "DROP TABLE",
        "DELETE FROM",
        "INSERT INTO",
        "../",
        "..\\",
        "/etc/passwd",
        "cmd.exe",
    ]

    @classmethod
    def sanitize(cls, text: str) -> str:
        for pattern in cls.BLOCKED_PATTERNS:
            if pattern.lower() in text.lower():
                raise HTTPException(status_code=400, detail="Invalid input detected")
        return text.strip()[:10000]

    @classmethod
    def sanitize_dict(cls, data: dict) -> dict:
        return {k: cls.sanitize(str(v)) if isinstance(v, str) else v for k, v in data.items()}


# ============================================================
# AUDIT LOGGER
# ============================================================
class AuditLogger:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def log_event(self, event_type: str, user_id: str, details: Dict, ip: str = None):
        import json

        event = {
            "event_type": event_type,
            "user_id": user_id,
            "details": details,
            "ip": ip,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.redis.lpush("audit_log", json.dumps(event))
        self.redis.ltrim("audit_log", 0, 99999)
        logger.info(
            "AUDIT: %s | user=%s | ip=%s",
            sanitize_for_log(event_type),
            sanitize_for_log(user_id),
            sanitize_for_log(ip),
        )

    def get_recent_events(self, limit: int = 100) -> List[Dict]:
        import json

        events = self.redis.lrange("audit_log", 0, limit - 1)
        return [json.loads(e) for e in events]


# ============================================================
# SECURITY MIDDLEWARE
# ============================================================
class SecurityHeaders:
    HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }

    @classmethod
    def apply(cls, response):
        for k, v in cls.HEADERS.items():
            response.headers[k] = v
        return response
