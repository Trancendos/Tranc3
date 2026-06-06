"""Encrypted user settings store.

Each secret is encrypted with Fernet (AES-128-CBC + HMAC-SHA256) before
being written to the database.  The Fernet key is derived from the platform
SECRET_KEY via HKDF so it is never persisted — losing SECRET_KEY means losing
the ability to decrypt stored settings (intentional).

Usage
-----
    store = get_settings_store()
    store.set("alice", "GROQ_API_KEY", "gsk_…")
    value = store.get("alice", "GROQ_API_KEY")   # decrypted plaintext
    store.delete("alice", "GROQ_API_KEY")
    status = store.list_keys("alice")            # {key: "set"|"unset"} for ALLOWED_KEYS
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import Dict, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.database.schema import Base, UserSetting

logger = logging.getLogger(__name__)

# Keys the settings page is allowed to store.  Expand here to add more.
ALLOWED_KEYS: set[str] = {
    "GROQ_API_KEY",
    "GOOGLE_GEMINI_API_KEY",
    "GITHUB_TOKEN",
    "CEREBRAS_API_KEY",
    "SAMBANOVA_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "DEEPSEEK_API_KEY",
    "OLLAMA_URL",
    "SECRET_KEY",
    "JWT_SECRET",
    "DATABASE_URL",
    "REDIS_URL",
}

_HKDF_SALT = b"tranc3-user-settings-v1"
_HKDF_INFO = b"encrypted-user-settings"


def _derive_fernet_key(master_secret: str) -> bytes:
    """Derive a 32-byte Fernet-compatible key from *master_secret* via HKDF."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    )
    raw = hkdf.derive(master_secret.encode())
    return base64.urlsafe_b64encode(raw)


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    secret = os.environ.get("SECRET_KEY", "")
    if not secret:
        raise RuntimeError("SECRET_KEY is not set — cannot initialise settings encryption")
    return Fernet(_derive_fernet_key(secret))


class UserSettingsStore:
    """Thread-safe encrypted settings store backed by SQLite (or any SQLAlchemy URL)."""

    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self._engine = create_engine(database_url, connect_args=connect_args)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)

    def _session(self) -> Session:
        return self._Session()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set(self, username: str, key: str, value: str) -> None:
        """Encrypt *value* and upsert it for *username*/*key*."""
        if key not in ALLOWED_KEYS:
            raise ValueError(f"Key '{key}' is not in the allowed settings list")
        f = _get_fernet()
        ciphertext = f.encrypt(value.encode()).decode()
        with self._session() as sess:
            existing = sess.query(UserSetting).filter_by(username=username, key=key).first()
            if existing:
                existing.encrypted_value = ciphertext
                existing.updated_at = datetime.utcnow()
            else:
                sess.add(UserSetting(username=username, key=key, encrypted_value=ciphertext))
            sess.commit()

    def get(self, username: str, key: str) -> Optional[str]:
        """Return the decrypted value for *username*/*key*, or None if not set."""
        with self._session() as sess:
            row = sess.query(UserSetting).filter_by(username=username, key=key).first()
            if not row:
                return None
            try:
                f = _get_fernet()
                return f.decrypt(row.encrypted_value.encode()).decode()
            except InvalidToken:
                logger.error("Failed to decrypt setting %s for %s — token invalid", key, username)
                return None

    def delete(self, username: str, key: str) -> bool:
        """Remove *key* for *username*.  Returns True if a row was deleted."""
        with self._session() as sess:
            deleted = sess.query(UserSetting).filter_by(username=username, key=key).delete()
            sess.commit()
            return bool(deleted)

    def list_keys(self, username: str) -> Dict[str, str]:
        """Return {key: "set"|"unset"} for every key in ALLOWED_KEYS."""
        with self._session() as sess:
            rows = sess.query(UserSetting.key).filter_by(username=username).all()
        stored = {r.key for r in rows}
        return {k: ("set" if k in stored else "unset") for k in sorted(ALLOWED_KEYS)}

    def get_all_for_process(self, username: str) -> Dict[str, str]:
        """Decrypt and return all stored settings as a plain dict.

        Intended for server-side injection into os.environ — NOT for API responses.
        """
        with self._session() as sess:
            rows = sess.query(UserSetting).filter_by(username=username).all()
        f = _get_fernet()
        result: Dict[str, str] = {}
        for row in rows:
            try:
                result[row.key] = f.decrypt(row.encrypted_value.encode()).decode()
            except InvalidToken:
                logger.warning("Skipping undecryptable setting %s for %s", row.key, username)
        return result

    def health_check(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Module-level singleton — lazily initialised on first call
# ---------------------------------------------------------------------------

_store: Optional[UserSettingsStore] = None


def get_settings_store() -> UserSettingsStore:
    global _store
    if _store is None:
        db_url = os.environ.get(
            "SETTINGS_DB_URL",
            os.environ.get("DATABASE_URL", "sqlite:///./tranc3_settings.db"),
        )
        _store = UserSettingsStore(db_url)
    return _store
