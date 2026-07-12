# src/auth/db_user_manager.py
# DB-backed user manager — replaces in-memory UserManager
# Root cause fix from 5 Whys #2

import datetime
import logging
import uuid
from typing import Optional

import bcrypt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


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

# Map billing tiers to default RBAC roles
_TIER_ROLE_MAP = {
    "free": "user",
    "pro": "operator",
    "business": "operator",
    "enterprise": "admin",
    "admin": "admin",
}


def _tier_to_roles(tier: str) -> list:
    """Return RBAC role list for a billing tier."""
    return [_TIER_ROLE_MAP.get(tier, "user")]


class DBUserManager:
    """
    Persistent user management backed by SQLAlchemy.
    Drop-in replacement for the in-memory UserManager in auth.py.
    Falls back to in-memory if DB is unavailable.
    """

    def __init__(self, db_session_factory=None):
        self._session_factory = db_session_factory
        self._fallback: dict = {}  # in-memory fallback
        self._use_db = db_session_factory is not None
        logger.info("DBUserManager initialised — DB=%s", "enabled" if self._use_db else "fallback")

    def _get_session(self) -> Optional[Session]:
        if self._session_factory:
            try:
                return self._session_factory()
            except Exception as e:
                logger.warning("DB session failed: %s — using fallback", sanitize_for_log(e))
        return None

    def create_user(self, username: str, password: str, email: str = "") -> dict:
        # Password strength check (SCAMPER-S action)
        self._validate_password(password)

        session = self._get_session()
        if session:
            try:
                from src.database.schema import User

                existing = session.query(User).filter(User.username == username).first()
                if existing:
                    raise HTTPException(status_code=400, detail="Username already exists")

                user = User(
                    id=uuid.uuid4(),
                    username=username,
                    email=email or f"{username}@tranc3.local",
                    hashed_password=pwd_context.hash(password),
                    tier="free",
                    is_active=True,
                    created_at=datetime.datetime.utcnow(),
                )
                session.add(user)
                session.commit()
                session.refresh(user)
                logger.info("User created in DB: %s", sanitize_for_log(username))
                return {"user_id": str(user.id), "username": username, "tier": "free"}
            except HTTPException:
                raise
            except Exception as e:
                session.rollback()
                logger.error("DB create_user failed: %s — using fallback", sanitize_for_log(e))
            finally:
                session.close()

        # Fallback
        if username in self._fallback:
            raise HTTPException(status_code=400, detail="Username already exists")
        user_id = str(uuid.uuid4())
        self._fallback[username] = {
            "id": user_id,
            "username": username,
            "hashed_password": pwd_context.hash(password),
            "tier": "free",
            "is_active": True,
            "created_at": datetime.datetime.utcnow(),
            "roles": _tier_to_roles("free"),
        }
        return {"user_id": user_id, "username": username, "tier": "free"}

    def authenticate_user(self, username: str, password: str) -> Optional[dict]:
        session = self._get_session()
        if session:
            try:
                from src.database.schema import User

                user = session.query(User).filter(User.username == username).first()
                if not user:
                    return None
                if not pwd_context.verify(password, user.hashed_password):
                    return None
                if not user.is_active:
                    return None
                # Update last login
                user.last_login = datetime.datetime.utcnow()  # type: ignore[assignment]
                session.commit()
                return {
                    "id": str(user.id),
                    "username": user.username,
                    "tier": user.tier,
                    "is_active": user.is_active,
                }
            except Exception as e:
                logger.error("DB authenticate_user failed: %s", sanitize_for_log(e))
            finally:
                session.close()

        # Fallback
        user = self._fallback.get(username)
        if not user:
            return None
        if not pwd_context.verify(password, user["hashed_password"]):
            return None
        return user

    def get_user(self, username: str) -> Optional[dict]:
        session = self._get_session()
        if session:
            try:
                from src.database.schema import User

                user = session.query(User).filter(User.username == username).first()
                if user:
                    return {
                        "id": str(user.id),
                        "username": user.username,
                        "tier": user.tier,
                        "is_active": user.is_active,
                        "roles": _tier_to_roles(user.tier),
                    }
            except Exception as e:
                logger.error("DB get_user failed: %s", sanitize_for_log(e))
            finally:
                session.close()

        user = self._fallback.get(username)
        if user and "roles" not in user:
            user = {**user, "roles": _tier_to_roles(user.get("tier", "free"))}
        return user

    def update_tier(self, username: str, new_tier: str) -> bool:
        session = self._get_session()
        if session:
            try:
                from src.database.schema import User

                user = session.query(User).filter(User.username == username).first()
                if user:
                    user.tier = new_tier  # type: ignore[assignment]
                    session.commit()
                    return True
            except Exception as e:
                logger.error("DB update_tier failed: %s", sanitize_for_log(e))
            finally:
                session.close()

        # Sync in-memory fallback record if present
        if username in self._fallback:
            self._fallback[username]["tier"] = new_tier
            self._fallback[username]["roles"] = _tier_to_roles(new_tier)
            return True
        return False

    def update_tier_by_id(self, user_id: str, new_tier: str) -> bool:
        """Update a user's tier keyed by their stable id (UUID).

        Billing/checkout metadata carries the user *id*, not the username, so
        webhook-driven provisioning must be able to resolve by id. Returns True
        only if a matching user was found and updated.
        """
        # Skip the DB lookup entirely for non-UUID identifiers: apply_provision
        # deliberately calls this with a *username* as a fallback, and querying
        # User.id == "<username>" raises a DataError (invalid UUID) that would spam
        # the logs on every such fallback. A bad UUID here just means "try the
        # username path", not an error.
        is_uuid = True
        try:
            uuid.UUID(str(user_id))
        except (ValueError, AttributeError, TypeError):
            is_uuid = False

        session = self._get_session() if is_uuid else None
        if session:
            try:
                from src.database.schema import User

                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    user.tier = new_tier  # type: ignore[assignment]
                    session.commit()
                    return True
            except Exception as e:
                session.rollback()
                logger.error("DB update_tier_by_id failed: %s", sanitize_for_log(e))
            finally:
                session.close()

        # Fallback store is keyed by username; match on the stored id.
        for rec in self._fallback.values():
            if str(rec.get("id")) == str(user_id):
                rec["tier"] = new_tier
                rec["roles"] = _tier_to_roles(new_tier)
                return True
        return False

    @staticmethod
    def _validate_password(password: str):
        """Enforce password strength — SCAMPER-S action."""
        errors = []
        if len(password) < 8:
            errors.append("at least 8 characters")
        if not any(c.isupper() for c in password):
            errors.append("one uppercase letter")
        if not any(c.isdigit() for c in password):
            errors.append("one number")
        if errors:
            raise HTTPException(
                status_code=400, detail=f"Password must contain: {', '.join(errors)}"
            )
