# auth.py — TRANC3 Authentication
# JWT token management + FastAPI dependency for current user

import datetime
import logging
import os
import secrets
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def _get_jwt_secret() -> str:
    """Return the JWT signing secret, failing closed for production."""
    secret = os.getenv("JWT_SECRET")
    if secret:
        return secret

    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError(
            "JWT_SECRET is not set. Set a strong random secret before issuing tokens."
        )

    generated = os.environ.setdefault("JWT_SECRET", secrets.token_hex(32))
    logger.warning(
        "JWT_SECRET not set — generated ephemeral JWT secret %s...; "
        "tokens will not survive process restarts.",
        generated[:8],
    )
    return generated


class _BcryptContext:
    """Minimal bcrypt wrapper replacing passlib.CryptContext — avoids crypt DeprecationWarning."""

    def hash(self, password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify(self, plain: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(plain.encode(), hashed.encode())
        except Exception:
            return False


pwd_context = _BcryptContext()
security = HTTPBearer()


class UserManager:
    """
    In-memory user manager — fallback only.
    Production: use src.auth.db_user_manager.DBUserManager.
    """

    def __init__(self):
        self.users: dict = {}

    def create_user(self, username: str, password: str) -> dict:
        if username in self.users:
            raise HTTPException(status_code=400, detail="Username already exists")
        uid = str(len(self.users) + 1)
        self.users[username] = {
            "id": uid,
            "username": username,
            "hashed_password": pwd_context.hash(password),
            "tier": "free",
            "is_active": True,
        }
        return {"user_id": uid, "username": username}

    def authenticate_user(self, username: str, password: str) -> Optional[dict]:
        user = self.users.get(username)
        if not user or not pwd_context.verify(password, user["hashed_password"]):
            return None
        return user if user["is_active"] else None

    def get_user(self, username: str) -> Optional[dict]:
        return self.users.get(username)


class TokenManager:
    """JWT creation and verification."""

    @staticmethod
    def create_access_token(
        data: dict,
        expires_delta: Optional[datetime.timedelta] = None,
    ) -> str:
        payload = data.copy()
        issued_at = datetime.datetime.now(datetime.timezone.utc)
        expire = issued_at + (
            expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        payload.update({"exp": expire, "iat": issued_at, "type": "access"})
        return jwt.encode(payload, _get_jwt_secret(), algorithm=ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict:
        try:
            payload = jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired") from None
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token") from None
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload


# Singletons
user_manager = UserManager()
token_manager = TokenManager()


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> dict:
    """
    FastAPI dependency — validates JWT and returns the current user.
    When REQUIRE_AUTH=false (default in test/dev), returns an anonymous user dict.
    Tries DB-backed manager first, falls back to in-memory.
    """
    if os.getenv("REQUIRE_AUTH", "true").lower() == "false":
        if not credentials:
            return {"username": "anonymous", "is_active": True, "role": "user"}

    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    payload = token_manager.decode_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Try DB-backed manager (imported lazily to avoid circular import)
    try:
        import api as _api  # codeql[py/cyclic-import]

        mgr = getattr(_api, "db_user_manager", None)
        if mgr:
            user = mgr.get_user(username)
            if user:
                return user
    except Exception:
        pass  # nosec B110 — graceful degradation

    # Fallback to in-memory
    user = user_manager.get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    return user
