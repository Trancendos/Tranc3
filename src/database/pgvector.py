"""
pgvector PostgreSQL Extension — Zero-cost vector storage
=========================================================
Uses the pgvector extension to store and query embeddings directly
in PostgreSQL — no separate vector database needed.

Requires: pgvector extension in PostgreSQL + psycopg2 or asyncpg.
Install extension: CREATE EXTENSION IF NOT EXISTS vector;

Free on: Supabase (pgvector enabled by default), Neon, PlanetScale,
         or any self-hosted PostgreSQL.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from psycopg2 import sql

logger = logging.getLogger("tranc3.database.pgvector")

_TABLE = os.environ.get("PGVECTOR_TABLE", "tranc3_embeddings")
_DIM = int(os.environ.get("PGVECTOR_DIM", "384"))
_DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _table_id() -> sql.Identifier:
    return sql.Identifier(_TABLE)


def _conn():
    """Return a psycopg2 connection or None if unavailable."""
    if not _DATABASE_URL:
        return None
    try:
        import psycopg2

        conn = psycopg2.connect(_DATABASE_URL)
        conn.autocommit = True
        return conn
    except Exception as e:
        logger.debug("pgvector unavailable (%s)", e)
        return None


def bootstrap() -> bool:
    """Create table + index. Call once at startup. Returns True on success."""
    conn = _conn()
    if conn is None:
        return False
    tbl = _table_id()
    bootstrap_sql = sql.SQL(  # nosec B608 — psycopg2.sql parameterization, not string concat
        """
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE IF NOT EXISTS {table} (
            id          TEXT PRIMARY KEY,
            embedding   vector({dim}),
            payload     JSONB NOT NULL DEFAULT '{{}}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS {idx_name}
            ON {table} USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
        """
    ).format(
        table=tbl,
        dim=sql.Literal(_DIM),
        idx_name=sql.Identifier(f"{_TABLE}_embedding_idx"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute(bootstrap_sql)
        logger.info("pgvector table %s bootstrapped", _TABLE)
        return True
    except Exception as e:
        logger.warning("pgvector bootstrap failed: %s", e)
        return False
    finally:
        conn.close()


def upsert(doc_id: str, vector: list[float], payload: dict[str, Any]) -> bool:
    """Insert or update a document embedding. Returns True on success."""
    import json

    conn = _conn()
    if conn is None:
        return False
    query = sql.SQL(  # nosec B608 — psycopg2.sql parameterization, no string concat
        """
    INSERT INTO {table} (id, embedding, payload, updated_at)
    VALUES (%s, %s::vector, %s::jsonb, NOW())
    ON CONFLICT (id) DO UPDATE
        SET embedding  = EXCLUDED.embedding,
            payload    = EXCLUDED.payload,
            updated_at = NOW();
    """
    ).format(table=_table_id())
    try:
        with conn.cursor() as cur:
            cur.execute(query, (doc_id, str(vector), json.dumps(payload)))
        return True
    except Exception as e:
        logger.warning("pgvector upsert failed: %s", e)
        return False
    finally:
        conn.close()


def search(
    query_vector: list[float],
    top_k: int = 5,
    score_threshold: float = 0.6,
    filter_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Cosine similarity search using pgvector <=> operator.
    Returns list of {id, score, payload} sorted by similarity descending.
    """
    conn = _conn()
    if conn is None:
        return []

    tbl = _table_id()
    if filter_payload:
        import json

        query = sql.SQL(  # nosec B608 — psycopg2.sql parameterization, no string concat
            """
            SELECT id, 1 - (embedding <=> %s::vector) AS score, payload
            FROM {table}
            WHERE payload @> %s::jsonb
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
            """
        ).format(table=tbl)
        params: list[Any] = [
            str(query_vector),
            json.dumps(filter_payload),
            str(query_vector),
            top_k,
        ]
    else:
        query = sql.SQL(  # nosec B608 — psycopg2.sql parameterization, no string concat
            """
            SELECT id, 1 - (embedding <=> %s::vector) AS score, payload
            FROM {table}
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
            """
        ).format(table=tbl)
        params = [str(query_vector), str(query_vector), top_k]

    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        results = []
        for row_id, score, payload in rows:
            if score >= score_threshold:
                results.append({"id": row_id, "score": float(score), **payload})
        return results
    except Exception as e:
        logger.warning("pgvector search failed: %s", e)
        return []
    finally:
        conn.close()


def delete(doc_id: str) -> bool:
    """Remove a document from the vector store. Returns True on success."""
    conn = _conn()
    if conn is None:
        return False
    query = sql.SQL("DELETE FROM {table} WHERE id = %s;").format(table=_table_id())  # nosec B608
    try:
        with conn.cursor() as cur:
            cur.execute(query, (doc_id,))
        return True
    except Exception as e:
        logger.warning("pgvector delete failed: %s", e)
        return False
    finally:
        conn.close()


def count() -> int:
    """Return the number of stored embeddings."""
    conn = _conn()
    if conn is None:
        return -1
    query = sql.SQL("SELECT COUNT(*) FROM {table};").format(table=_table_id())  # nosec B608
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            result = cur.fetchone()
            return result[0] if result else 0
    except Exception as e:
        logger.debug("pgvector count failed: %s", e)
        return -1
    finally:
        conn.close()
