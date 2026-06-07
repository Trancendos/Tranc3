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

import logging
import os
import sys
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_pinecone_to_qdrant")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
PINECONE_INDEX = os.environ.get("PINECONE_INDEX", "tranc3-memory")
# Set PINECONE_NAMESPACES to a comma-separated list to migrate specific namespaces.
# Leave empty to migrate the default namespace only.
PINECONE_NAMESPACES = [
    ns.strip() for ns in os.environ.get("PINECONE_NAMESPACES", "").split(",") if ns.strip()
] or [""]  # [""] = default namespace
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", None)
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "tranc3-memory")
BATCH_SIZE = 100

# Qdrant supports UUID strings natively — use uuid5(NAMESPACE_URL, vec_id) for deterministic,
# collision-free IDs that are stable across re-runs without integer truncation risk.
_UUID_NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL


def _point_id(vec_id: str) -> str:
    """Deterministic UUID5 point ID for a Pinecone vector ID. Collision-free and idempotent."""
    return str(uuid.uuid5(_UUID_NS, vec_id))


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
    logger.info(
        "Pinecone index '%s': %d vectors, dim=%d", PINECONE_INDEX, total_vectors, vector_dim
    )

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

    # ── Paginate Pinecone → upsert Qdrant (all namespaces) ───────────────────
    migrated = 0
    logger.info("Migrating namespaces: %s", PINECONE_NAMESPACES)

    for namespace in PINECONE_NAMESPACES:
        ns_label = repr(namespace) if namespace else "(default)"
        logger.info("Starting namespace %s", ns_label)
        pagination_token = None

        while True:
            # list_paginated returns a single ListResponse page; list() is a generator.
            list_kwargs: dict = {"limit": BATCH_SIZE}
            if namespace:
                list_kwargs["namespace"] = namespace
            if pagination_token:
                list_kwargs["pagination_token"] = pagination_token

            page = index.list_paginated(**list_kwargs)
            ids = [v.id for v in page.vectors] if page.vectors else []

            if not ids:
                break

            # Fetch full vector data for this page
            fetch_kwargs: dict = {"ids": ids}
            if namespace:
                fetch_kwargs["namespace"] = namespace
            fetch_response = index.fetch(**fetch_kwargs)

            points = []
            for vec_id, vec_data in fetch_response.vectors.items():
                points.append(
                    PointStruct(
                        # UUID5 = deterministic, collision-free, natively supported by Qdrant
                        id=_point_id(vec_id),
                        vector=vec_data.values,
                        payload={
                            **(vec_data.metadata or {}),
                            "_vector_id": vec_id,
                            "_namespace": namespace,
                        },
                    )
                )

            if points:
                qclient.upsert(collection_name=QDRANT_COLLECTION, points=points)
                migrated += len(points)
                logger.info(
                    "Namespace %s — migrated %d vectors so far (total %d)",
                    ns_label,
                    len(points),
                    migrated,
                )

            next_token = page.pagination.next if page.pagination else None
            if not next_token:
                break
            pagination_token = next_token

        logger.info("Namespace %s — done", ns_label)

    logger.info(
        "Migration complete — %d vectors upserted into Qdrant '%s'", migrated, QDRANT_COLLECTION
    )
    logger.info("You can now remove PINECONE_API_KEY and PINECONE_INDEX from your environment.")


if __name__ == "__main__":
    main()
