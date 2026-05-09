# src/database/deps.py
# FastAPI dependencies for database sessions.
# Provides a get_db() dependency that yields a SQLAlchemy session
# and properly closes it after the request.

from __future__ import annotations

import logging
from typing import Generator, Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Global reference — set during app lifespan
_db_manager = None


def set_db_manager(manager) -> None:
    """Set the global DatabaseManager instance (called during lifespan)."""
    global _db_manager
    _db_manager = manager
    logger.info("Database dependency configured")


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session.
    Automatically commits on success, rolls back on error, and always closes.
    """
    if _db_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Set DATABASE_URL environment variable.",
        )

    session = _db_manager.get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session_optional() -> Optional[Session]:
    """
    Non-dependency version — returns a session or None if DB unavailable.
    Use for background tasks where FastAPI dependency injection isn't available.
    """
    if _db_manager is None:
        return None
    try:
        return _db_manager.get_session()
    except Exception as e:
        logger.error("Failed to get DB session: %s", e)
        return None
