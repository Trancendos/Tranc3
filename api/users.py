"""Users CRUD router — JWT-protected, self-hosted only."""

from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Depends, HTTPException
    from fastapi.security import OAuth2PasswordBearer
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("fastapi required") from exc

try:
    import os

    import jwt as pyjwt

    _JWT_SECRET = os.getenv("JWT_SECRET", "changeme-in-production")
    _JWT_ALGORITHM = "HS256"
except ImportError:
    pyjwt = None  # type: ignore[assignment]

try:
    from src.database.models import User  # type: ignore[import]

    _MODELS_AVAILABLE = True
except ImportError:
    _MODELS_AVAILABLE = False
    User = None  # type: ignore[misc,assignment]

router = APIRouter(prefix="/users", tags=["users"])
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def _get_current_user(token: str = Depends(_oauth2_scheme)) -> dict[str, Any]:
    """Decode bearer token — delegates to api.auth to honour revocation list."""
    try:
        from api.auth import _decode_token  # type: ignore[import]
        return _decode_token(token)
    except ImportError:
        pass
    # Fallback if api.auth unavailable (standalone usage without full app)
    if pyjwt is None:
        raise HTTPException(status_code=500, detail="PyJWT not installed")
    try:
        return pyjwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/me")
async def get_me(current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    """Return profile of the authenticated user."""
    sub = current_user.get("sub", "unknown")

    if _MODELS_AVAILABLE:
        # Hydrate from DB when the models layer is present.
        try:
            from sqlalchemy import select
            from src.database.session import get_db  # type: ignore[import]

            async for db in get_db():
                result = await db.execute(select(User).where(User.username == sub))
                row = result.scalar_one_or_none()
                if row:
                    return {"id": str(row.id), "username": row.username, "email": getattr(row, "email", None)}
        except Exception:  # noqa: BLE001 — DB unavailable, use token fallback
            pass

    # Graceful fallback when DB is unavailable.
    return {"sub": sub, "source": "token"}


@router.put("/me")
async def update_me(
    updates: dict[str, Any],
    current_user: dict[str, Any] = Depends(_get_current_user),
) -> dict[str, Any]:
    """Update mutable profile fields for the authenticated user."""
    sub = current_user.get("sub", "unknown")
    allowed_fields = {"display_name", "email", "avatar_url"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}

    if _MODELS_AVAILABLE:
        try:
            from sqlalchemy import update
            from src.database.session import get_db  # type: ignore[import]

            async for db in get_db():
                await db.execute(update(User).where(User.username == sub).values(**filtered))
                await db.commit()
                return {"updated": list(filtered.keys()), "sub": sub}
        except Exception:  # noqa: BLE001 — DB unavailable, dry-run
            pass

    return {"updated": list(filtered.keys()), "sub": sub, "source": "dry-run"}
