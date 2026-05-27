"""Vector Plan Cache — TranceX Phase 8

Semantic similarity-based NRC query plan cache using ChromaDB and LanceDB.
Stores vector embeddings of NRC queries alongside their optimized plans,
enabling instant reuse of previously computed genetic/quantum plans.

All dependencies are 0-cost (free/open-source).
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CacheBackend(Enum):
    """Vector store backend."""

    CHROMADB = "chromadb"
    LANCEDB = "lancedb"
    MEMORY = "memory"


class PlanStatus(Enum):
    """Status of a cached plan."""

    OPTIMAL = "optimal"
    SUBOPTIMAL = "suboptimal"
    STALE = "stale"
    DEPRECATED = "deprecated"
    EVOLVING = "evolving"


@dataclass
class NRCQueryEmbedding:
    """Vector embedding of an NRC query for semantic search."""

    query_id: str
    nrc_dsl: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    schema_hash: str = ""
    relation_fingerprint: str = ""

    def __post_init__(self):
        if not self.schema_hash:
            self.schema_hash = hashlib.sha3_256(self.nrc_dsl.encode()).hexdigest()[:16]
        if not self.relation_fingerprint:
            # Extract relation names from DSL for quick fingerprinting
            relations = sorted({w for w in self.nrc_dsl.split() if w.isidentifier()})
            self.relation_fingerprint = hashlib.sha3_256(":".join(relations).encode()).hexdigest()[
                :12
            ]


@dataclass
class CachedPlan:
    """An optimized NRC query plan stored in the vector cache."""

    plan_id: str
    query_id: str
    query_embedding: NRCQueryEmbedding
    plan_data: Dict[str, Any]
    fitness: Dict[str, float]
    status: PlanStatus = PlanStatus.OPTIMAL
    hit_count: int = 0
    last_used: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    generation: int = 0
    optimization_time_ms: float = 0.0
    backend: str = "genetic"
    tags: List[str] = field(default_factory=list)


@dataclass
class CacheSearchResult:
    """Result from a vector similarity search in the plan cache."""

    cached_plan: CachedPlan
    similarity_score: float
    distance: float
    exact_match: bool = False


class SimpleTextEncoder:
    """Simple text-to-vector encoder for NRC queries.

    Uses TF-IDF-like hashing for lightweight embedding without
    requiring heavyweight ML models. Falls back gracefully when
    sentence-transformers is unavailable.
    """

    EMBEDDING_DIM = 128

    def encode(self, text: str) -> List[float]:
        """Encode text into a fixed-dimension vector using feature hashing."""
        embedding = [0.0] * self.EMBEDDING_DIM

        # Tokenize and hash
        tokens = text.lower().split()
        ngrams = tokens[:]
        for i in range(len(tokens) - 1):
            ngrams.append(f"{tokens[i]}_{tokens[i + 1]}")
        for i in range(len(tokens) - 2):
            ngrams.append(f"{tokens[i]}_{tokens[i + 1]}_{tokens[i + 2]}")

        for token in ngrams:
            # Feature hashing
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            idx = h % self.EMBEDDING_DIM
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            embedding[idx] += sign

        # L2 normalize
        norm = sum(x * x for x in embedding) ** 0.5
        if norm > 0:
            embedding = [x / norm for x in embedding]

        return embedding

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """Encode a batch of texts."""
        return [self.encode(t) for t in texts]


class InMemoryVectorStore:
    """In-memory vector store for plan embeddings.

    Supports cosine similarity search with configurable top-k.
    Used as the default backend when ChromaDB/LanceDB are unavailable.
    """

    def __init__(self, dimension: int = 128):
        self.dimension = dimension
        self._vectors: Dict[str, List[float]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def add(
        self, ids: List[str], vectors: List[List[float]], metadatas: List[Dict[str, Any]]
    ) -> None:
        """Add vectors to the store."""
        for id_, vec, meta in zip(ids, vectors, metadatas):
            self._vectors[id_] = vec
            self._metadata[id_] = meta

    def query(
        self, query_vector: List[float], top_k: int = 10
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Query for similar vectors using cosine similarity."""
        results = []
        for id_, vec in self._vectors.items():
            sim = self._cosine_similarity(query_vector, vec)
            results.append((id_, sim, self._metadata.get(id_, {})))

        results.sort(key=lambda x: -x[1])
        return results[:top_k]

    def delete(self, ids: List[str]) -> None:
        """Delete vectors by ID."""
        for id_ in ids:
            self._vectors.pop(id_, None)
            self._metadata.pop(id_, None)

    def count(self) -> int:
        """Return number of stored vectors."""
        return len(self._vectors)

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


class ChromaDBPlanStore:
    """ChromaDB-backed vector store for plan embeddings.

    ChromaDB is 0-cost (Apache-2.0). Falls back to in-memory store
    if ChromaDB is not installed.
    """

    def __init__(
        self, collection_name: str = "trancex_nrc_plans", persist_dir: Optional[str] = None
    ):
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self._client = None
        self._collection = None
        self._fallback = InMemoryVectorStore()
        self._use_chromadb = False

        try:
            import chromadb

            if persist_dir:
                self._client = chromadb.PersistentClient(path=persist_dir)
            else:
                self._client = chromadb.Client()
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._use_chromadb = True
            logger.info(f"ChromaDB plan store initialized: {collection_name}")
        except ImportError:
            logger.info("ChromaDB not available, using in-memory vector store")

    def add(
        self, ids: List[str], vectors: List[List[float]], metadatas: List[Dict[str, Any]]
    ) -> None:
        """Add vectors to the store."""
        if self._use_chromadb and self._collection:
            self._collection.add(ids=ids, embeddings=vectors, metadatas=metadatas)
        else:
            self._fallback.add(ids, vectors, metadatas)

    def query(
        self, query_vector: List[float], top_k: int = 10
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Query for similar vectors."""
        if self._use_chromadb and self._collection:
            results = self._collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                include=["metadatas", "distances"],
            )
            formatted = []
            if results and results["ids"] and results["ids"][0]:
                for i, id_ in enumerate(results["ids"][0]):
                    distance = results["distances"][0][i] if results["distances"] else 0.0
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    similarity = 1.0 - distance
                    formatted.append((id_, similarity, meta))
            return formatted
        return self._fallback.query(query_vector, top_k)

    def delete(self, ids: List[str]) -> None:
        """Delete vectors by ID."""
        if self._use_chromadb and self._collection:
            self._collection.delete(ids=ids)
        else:
            self._fallback.delete(ids)

    def count(self) -> int:
        """Return number of stored vectors."""
        if self._use_chromadb and self._collection:
            return self._collection.count()
        return self._fallback.count()


class LanceDBPlanStore:
    """LanceDB-backed vector store for plan embeddings.

    LanceDB is 0-cost (Apache-2.0). Falls back to in-memory store
    if LanceDB is not installed. Provides better performance for
    large-scale plan similarity search.
    """

    def __init__(self, table_name: str = "trancex_nrc_plans", uri: Optional[str] = None):
        self.table_name = table_name
        self.uri = uri or "/tmp/trancex_lancedb"
        self._db = None
        self._table = None
        self._fallback = InMemoryVectorStore()
        self._use_lancedb = False

        try:
            import lancedb

            self._db = lancedb.connect(self.uri)
            self._use_lancedb = True
            logger.info(f"LanceDB plan store initialized: {table_name}")
        except ImportError:
            logger.info("LanceDB not available, using in-memory vector store")

    def add(
        self, ids: List[str], vectors: List[List[float]], metadatas: List[Dict[str, Any]]
    ) -> None:
        """Add vectors to the store."""
        if self._use_lancedb and self._db:
            data = []
            for id_, vec, meta in zip(ids, vectors, metadatas):
                row = {"id": id_, "vector": vec}
                row.update(meta)
                data.append(row)
            try:
                if self._table is None:
                    self._table = self._db.create_table(self.table_name, data)
                else:
                    self._table.add(data)
            except Exception as e:
                logger.warning(f"LanceDB add failed: {e}")
                self._fallback.add(ids, vectors, metadatas)
        else:
            self._fallback.add(ids, vectors, metadatas)

    def query(
        self, query_vector: List[float], top_k: int = 10
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Query for similar vectors."""
        if self._use_lancedb and self._table is not None:
            try:
                results = self._table.search(query_vector).limit(top_k).to_pandas()
                formatted = []
                for _, row in results.iterrows():
                    sim = 1.0 - float(row.get("_distance", 1.0))
                    meta = {k: v for k, v in row.items() if k not in ("vector", "_distance")}
                    formatted.append((str(row.get("id", "")), sim, meta))
                return formatted
            except Exception as e:
                logger.warning(f"LanceDB query failed: {e}")
        return self._fallback.query(query_vector, top_k)

    def count(self) -> int:
        """Return number of stored vectors."""
        if self._use_lancedb and self._table is not None:
            try:
                return len(self._table)
            except Exception:  # noqa: S110
                pass  # graceful degradation
        return self._fallback.count()


class VectorPlanCache:
    """Central vector plan cache for the TranceX ecosystem.

    Stores and retrieves optimized NRC query plans using semantic similarity.
    Supports multiple backends (ChromaDB, LanceDB, in-memory) and
    provides plan lifecycle management with staleness detection.
    """

    def __init__(
        self,
        backend: CacheBackend = CacheBackend.CHROMADB,
        similarity_threshold: float = 0.85,
        staleness_threshold_hours: float = 72.0,
        max_cache_size: int = 10000,
        encoder: Optional[SimpleTextEncoder] = None,
    ):
        self.similarity_threshold = similarity_threshold
        self.staleness_threshold_hours = staleness_threshold_hours
        self.max_cache_size = max_cache_size
        self.encoder = encoder or SimpleTextEncoder()

        # Initialize vector store
        if backend == CacheBackend.LANCEDB:
            self._store = LanceDBPlanStore()
        elif backend == CacheBackend.CHROMADB:
            self._store = ChromaDBPlanStore()
        else:
            self._store = InMemoryVectorStore()

        self._plans: Dict[str, CachedPlan] = {}
        self._query_to_plan: Dict[str, str] = {}  # schema_hash -> plan_id
        self._hit_count = 0
        self._miss_count = 0

    def add_plan(self, plan: CachedPlan) -> str:
        """Add an optimized plan to the cache."""
        # Encode the query
        embedding = self.encoder.encode(plan.query_embedding.nrc_dsl)
        plan.query_embedding.embedding = embedding

        # Store in vector store
        self._store.add(
            ids=[plan.plan_id],
            vectors=[embedding],
            metadatas=[
                {
                    "query_id": plan.query_id,
                    "schema_hash": plan.query_embedding.schema_hash,
                    "status": plan.status.value,
                    "generation": plan.generation,
                    "backend": plan.backend,
                }
            ],
        )

        # Store in local index
        self._plans[plan.plan_id] = plan
        self._query_to_plan[plan.query_embedding.schema_hash] = plan.plan_id

        # Evict if over capacity
        if len(self._plans) > self.max_cache_size:
            self._evict_stale_plans()

        logger.info(f"Cached plan {plan.plan_id} for query {plan.query_id}")
        return plan.plan_id

    def search_similar(self, nrc_dsl: str, top_k: int = 5) -> List[CacheSearchResult]:
        """Search for similar plans using vector similarity."""
        query_embedding = self.encoder.encode(nrc_dsl)

        # Check for exact match first
        schema_hash = hashlib.sha3_256(nrc_dsl.encode()).hexdigest()[:16]
        if schema_hash in self._query_to_plan:
            plan_id = self._query_to_plan[schema_hash]
            if plan_id in self._plans:
                plan = self._plans[plan_id]
                plan.hit_count += 1
                plan.last_used = time.time()
                self._hit_count += 1
                return [
                    CacheSearchResult(
                        cached_plan=plan,
                        similarity_score=1.0,
                        distance=0.0,
                        exact_match=True,
                    )
                ]

        # Vector similarity search
        results = self._store.query(query_embedding, top_k=top_k)
        search_results = []

        for plan_id, similarity, meta in results:
            plan = self._plans.get(plan_id)
            if plan:
                # Check staleness
                age_hours = (time.time() - plan.created_at) / 3600
                if age_hours > self.staleness_threshold_hours:
                    plan.status = PlanStatus.STALE

                plan.hit_count += 1
                plan.last_used = time.time()

                exact = plan.query_embedding.schema_hash == schema_hash
                if exact:
                    self._hit_count += 1
                else:
                    self._miss_count += 1

                search_results.append(
                    CacheSearchResult(
                        cached_plan=plan,
                        similarity_score=similarity,
                        distance=1.0 - similarity,
                        exact_match=exact,
                    )
                )

        if not search_results:
            self._miss_count += 1

        # Filter by similarity threshold
        return [r for r in search_results if r.similarity_score >= self.similarity_threshold]

    def get_plan(self, plan_id: str) -> Optional[CachedPlan]:
        """Get a cached plan by ID."""
        return self._plans.get(plan_id)

    def invalidate_plan(self, plan_id: str) -> None:
        """Mark a plan as deprecated."""
        if plan_id in self._plans:
            self._plans[plan_id].status = PlanStatus.DEPRECATED

    def update_plan_status(self, plan_id: str, status: PlanStatus) -> None:
        """Update the status of a cached plan."""
        if plan_id in self._plans:
            self._plans[plan_id].status = status

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        status_counts = {}
        for plan in self._plans.values():
            status_counts[plan.status.value] = status_counts.get(plan.status.value, 0) + 1

        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0.0

        return {
            "total_plans": len(self._plans),
            "status_distribution": status_counts,
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": hit_rate,
            "vector_store_count": self._store.count(),
            "similarity_threshold": self.similarity_threshold,
        }

    def _evict_stale_plans(self) -> int:
        """Evict stale/deprecated plans to free cache capacity."""
        to_evict = []
        for plan_id, plan in self._plans.items():
            if plan.status in (PlanStatus.STALE, PlanStatus.DEPRECATED):
                to_evict.append(plan_id)

        for plan_id in to_evict:
            del self._plans[plan_id]
            self._store.delete([plan_id])

        # If still over capacity, evict oldest low-hit plans
        if len(self._plans) > self.max_cache_size * 0.9:
            sorted_plans = sorted(self._plans.items(), key=lambda x: x[1].last_used)
            while len(self._plans) > self.max_cache_size * 0.8:
                plan_id, _ = sorted_plans.pop(0)
                del self._plans[plan_id]
                self._store.delete([plan_id])

        logger.info(f"Evicted {len(to_evict)} stale plans from cache")
        return len(to_evict)
