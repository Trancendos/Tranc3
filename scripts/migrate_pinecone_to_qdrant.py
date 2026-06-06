"""
migrate_pinecone_to_qdrant.py — One-shot Pinecone → Qdrant migration
=====================================================================
Reads all vectors from a Pinecone index and upserts them into the
self-hosted Qdrant collection.  Run once, then remove PINECONE_API_KEY
from your environment.

Usage
-----
    PINECONE_API_KEY=pk-... PINECONE_INDEX=tranc3-memory \\
    QDRANT_URL=http://localhost:6333 \\
    python scripts/migrate_pinecone_to_qdrant.py

Requirements
------------
    pip install pinecone qdrant-client

Progress is logged to stdout; the script is idempotent (upsert is safe
to re-run if interrupted).
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_pinecone_to_qdrant")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
PINECONE_INDEX = os.environ.get("PINECONE_INDEX", "tranc3-memory")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", None)
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "tranc3-memory")
BATCH_SIZE = 100


def _require(name: str, value: str) -> str:
    if not value:
        logger.error("Environment variable %s is required", name)
        sys.exit(1)
    return value


def main() -> None:
    _require("PINECONE_API_KEY", PINECONE_API_KEY)

    # ── Connect to Pinecone ───────────────────────────────────────────────────
    try:
        from pinecone import Pinecone
    except ImportError:
        logger.error("pinecone package not installed — run: pip install pinecone")
        sys.exit(1)

    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX)
    stats = index.describe_index_stats()
    total_vectors = stats.total_vector_count
    vector_dim = stats.dimension
    logger.info("Pinecone index '%s': %d vectors, dim=%d", PINECONE_INDEX, total_vectors, vector_dim)

    if total_vectors == 0:
        logger.info("No vectors to migrate — nothing to do")
        return

    # ── Connect to Qdrant ─────────────────────────────────────────────────────
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams
    except ImportError:
        logger.error("qdrant-client not installed — run: pip install qdrant-client")
        sys.exit(1)

    qclient = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30)
    existing = [c.name for c in qclient.get_collections().collections]
    if QDRANT_COLLECTION not in existing:
        qclient.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s'", QDRANT_COLLECTION)
    else:
        logger.info("Qdrant collection '%s' already exists — upserting into it", QDRANT_COLLECTION)

    # ── Paginate Pinecone → upsert Qdrant ─────────────────────────────────────
    migrated = 0
    pagination_token = None

    while True:
        list_kwargs: dict = {"limit": BATCH_SIZE}
        if pagination_token:
            list_kwargs["pagination_token"] = pagination_token

        page = index.list(**list_kwargs)
        ids = list(page.vectors.keys()) if hasattr(page, "vectors") else list(page)

        if not ids:
            break

        # Fetch full vector data
        fetch_response = index.fetch(ids=ids)
        points = []
        for vec_id, vec_data in fetch_response.vectors.items():
            points.append(
                PointStruct(
                    id=int(hashlib.sha256(vec_id.encode()).hexdigest()[:16], 16),
                    vector=vec_data.values,
                    payload={**(vec_data.metadata or {}), "_vector_id": vec_id},
                )
            )

        if points:
            qclient.upsert(collection_name=QDRANT_COLLECTION, points=points)
            migrated += len(points)
            logger.info("Migrated %d / %d vectors ...", migrated, total_vectors)

        pagination_token = getattr(page, "pagination", {})
        if not pagination_token or not getattr(pagination_token, "next", None):
            break
        pagination_token = pagination_token.next

    logger.info("Migration complete — %d vectors upserted into Qdrant '%s'", migrated, QDRANT_COLLECTION)
    logger.info("You can now remove PINECONE_API_KEY and PINECONE_INDEX from your environment.")


if __name__ == "__main__":
    main()
