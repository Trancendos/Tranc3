"""JWT authentication router — self-hosted, no external auth service."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

try:
    from fastapi import APIRouter, Depends, HTTPException, status
    from fastapi.security import OAuth2PasswordRequestForm
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("fastapi required") from exc

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None  # type: ignore[assignment]

try:
    import bcrypt

    _BCRYPT_AVAILABLE = True
except ImportError:
    _BCRYPT_AVAILABLE = False

router = APIRouter(prefix="/auth", tags=["auth"])

_JWT_SECRET: str = os.getenv("JWT_SECRET", "changeme-in-production")
_JWT_ALGORITHM = "HS256"
# Short-lived access token; refresh token carries longer validity.
_ACCESS_TTL = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "3600"))
_REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL_SECONDS", str(7 * 86400)))

# In-memory revocation set — replaced by Redis in production via The HIVE.
_revoked_jti: set[str] = set()


def _make_token(sub: str, ttl: int, kind: str = "access") -> str:
    if pyjwt is None:
        raise HTTPException(status_code=500, detail="PyJWT not installed")
    import uuid

    now = int(time.time())
    payload = {
        "sub": sub,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
        "kind": kind,
    }
    return pyjwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _decode_token(token: str) -> dict[str, Any]:
    if pyjwt is None:
        raise HTTPException(status_code=500, detail="PyJWT not installed")
    try:
        payload = pyjwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if payload.get("jti") in _revoked_jti:
        raise HTTPException(status_code=401, detail="Token revoked")
    return payload


def _verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison via bcrypt; falls back to naive check in dev."""
    if _BCRYPT_AVAILABLE:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    # Naive fallback — acceptable only when bcrypt is absent in dev environments.
    return plain == hashed


def _lookup_user(username: str) -> Optional[dict[str, Any]]:
    """Stub user lookup — replace with SQLAlchemy query in production."""
    demo_hash = os.getenv("DEMO_USER_HASH", "demo")
    if username == os.getenv("DEMO_USER", "admin"):
        return {"sub": username, "hashed_password": demo_hash}
    return None


@router.post("/token")
async def login(form: OAuth2PasswordRequestForm = Depends()) -> dict[str, str]:
    """Issue access + refresh tokens via OAuth2 password flow."""
    user = _lookup_user(form.username)
    if user is None or not _verify_password(form.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access = _make_token(user["sub"], _ACCESS_TTL, kind="access")
    refresh = _make_token(user["sub"], _REFRESH_TTL, kind="refresh")
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
    }


@router.post("/refresh")
async def refresh(refresh_token: str) -> dict[str, str]:
    """Exchange a valid refresh token for a new access token."""
    payload = _decode_token(refresh_token)
    if payload.get("kind") != "refresh":
        raise HTTPException(status_code=400, detail="Not a refresh token")
    access = _make_token(payload["sub"], _ACCESS_TTL, kind="access")
    return {"access_token": access, "token_type": "bearer"}


@router.post("/logout")
async def logout(token: str) -> dict[str, str]:
    """Revoke the supplied token by adding its jti to the in-memory set."""
    payload = _decode_token(token)
    _revoked_jti.add(payload["jti"])
    return {"detail": "logged out"}
