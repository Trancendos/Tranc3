# auth.py — TRANC3 Authentication
# JWT token management + FastAPI dependency for current user

import datetime
import os
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

# SECRET_KEY must be set in environment — api.py fails fast if missing
SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security    = HTTPBearer()


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
            "id": uid, "username": username,
            "hashed_password": pwd_context.hash(password),
            "tier": "free", "is_active": True,
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
        expire  = datetime.datetime.utcnow() + (
            expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        payload.update({"exp": expire, "iat": datetime.datetime.utcnow(), "type": "access"})
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload


# Singletons
user_manager  = UserManager()
token_manager = TokenManager()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    FastAPI dependency — validates JWT and returns the current user.
    Tries DB-backed manager first, falls back to in-memory.
    """
    payload  = token_manager.decode_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Try DB-backed manager (imported lazily to avoid circular import)
    try:
        import api as _api
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
