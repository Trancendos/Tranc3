"""
Enhanced Skill Registry — TF-IDF + optional semantic search with intelligent routing.

Skills are pre-registered at import time and can also be loaded from a
directory of Markdown files with YAML frontmatter.  Bundles group related
skills and are activated when trigger keywords appear in the request text.
"""

import asyncio
import json
import logging
import math
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Skill:
    id: str
    name: str
    category: str
    description: str
    content: str
    tags: List[str] = field(default_factory=list)
    version: str = "1.0"
    embedding: Optional[List[float]] = None
    usage_count: int = 0
    avg_quality: float = 0.9
    last_used: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "content": self.content,
            "tags": self.tags,
            "version": self.version,
            "usage_count": self.usage_count,
            "avg_quality": self.avg_quality,
            "last_used": self.last_used,
        }


@dataclass
class SkillBundle:
    id: str
    name: str
    trigger_keywords: List[str]
    skills: List[str]          # list of skill IDs
    description: str


@dataclass
class SkillSearchResult:
    skill: Skill
    score: float
    match_reason: str


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class EnhancedSkillRegistry:
    """
    ML-powered skill registry with hybrid lexical + semantic search.

    TF-IDF-style lexical scoring is always available.  When
    sentence-transformers is installed the registry lazily initialises a
    MiniLM encoder on first semantic query and blends scores
    (0.4 × lexical + 0.6 × semantic).
    """

    def __init__(self) -> None:
        self.skills: Dict[str, Skill] = {}
        self.bundles: Dict[str, SkillBundle] = {}
        self._embedder = None            # sentence_transformers.SentenceTransformer
        self._embedder_attempted = False
        # IDF cache — rebuilt on register()
        self._idf: Dict[str, float] = {}
        self._idf_dirty = True

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, skill: Skill) -> None:
        self.skills[skill.id] = skill
        self._idf_dirty = True
        logger.debug("Registered skill '%s' (%s)", skill.id, skill.name)

    def register_bundle(self, bundle: SkillBundle) -> None:
        self.bundles[bundle.id] = bundle
        logger.debug("Registered bundle '%s'", bundle.id)

    # ------------------------------------------------------------------
    # IDF computation
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    def _build_idf(self) -> None:
        """Compute IDF weights across all registered skills."""
        N = max(len(self.skills), 1)
        doc_freq: Dict[str, int] = defaultdict(int)
        for skill in self.skills.values():
            corpus = (
                skill.name + " " + skill.description + " "
                + skill.content + " " + " ".join(skill.tags)
            )
            seen = set(self._tokenize(corpus))
            for tok in seen:
                doc_freq[tok] += 1
        self._idf = {
            tok: math.log((N + 1) / (df + 1)) + 1.0
            for tok, df in doc_freq.items()
        }
        self._idf_dirty = False

    def _tfidf_score(self, query_tokens: List[str], skill: Skill) -> float:
        """Compute a simple TF-IDF dot-product score for a query against a skill."""
        corpus = (
            skill.name + " " + skill.description + " "
            + skill.content + " " + " ".join(skill.tags)
        )
        doc_tokens = self._tokenize(corpus)
        tf: Dict[str, float] = defaultdict(float)
        for t in doc_tokens:
            tf[t] += 1.0
        n = max(len(doc_tokens), 1)
        score = 0.0
        for qt in query_tokens:
            if qt in tf:
                score += (tf[qt] / n) * self._idf.get(qt, 1.0)
        return score

    # ------------------------------------------------------------------
    # Embedder (lazy, optional)
    # ------------------------------------------------------------------

    def _try_load_embedder(self) -> None:
        if self._embedder_attempted:
            return
        self._embedder_attempted = True
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            model_name = os.getenv(
                "EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
            )
            self._embedder = SentenceTransformer(model_name)
            logger.info("Loaded sentence-transformer: %s", model_name)
        except Exception as exc:
            logger.info("sentence-transformers not available (%s) — using lexical search only.", exc)
            self._embedder = None

    def _cosine(self, a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(y * y for y in b))
        if mag_a < 1e-12 or mag_b < 1e-12:
            return 0.0
        return dot / (mag_a * mag_b)

    async def _semantic_score(
        self,
        query_vec: Optional[List[float]],
        skill: Skill,
    ) -> float:
        if query_vec is None or self._embedder is None:
            return 0.0
        if skill.embedding is None:
            # Compute and cache embedding for this skill
            loop = asyncio.get_event_loop()
            corpus = skill.name + ". " + skill.description
            vec = await loop.run_in_executor(
                None, lambda: self._embedder.encode(corpus).tolist()
            )
            skill.embedding = vec
        return self._cosine(query_vec, skill.embedding)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        top_k: int = 10,
        category: Optional[str] = None,
    ) -> List[SkillSearchResult]:
        if self._idf_dirty:
            self._build_idf()

        query_tokens = self._tokenize(query)

        # Optionally compute query embedding
        self._try_load_embedder()
        query_vec: Optional[List[float]] = None
        if self._embedder is not None:
            loop = asyncio.get_event_loop()
            query_vec = await loop.run_in_executor(
                None, lambda: self._embedder.encode(query).tolist()
            )

        candidates = [
            s for s in self.skills.values()
            if category is None or s.category == category
        ]

        results: List[SkillSearchResult] = []
        for skill in candidates:
            lex_score = self._tfidf_score(query_tokens, skill)

            if query_vec is not None:
                sem_score = await self._semantic_score(query_vec, skill)
                combined = 0.4 * lex_score + 0.6 * sem_score
                reason = f"hybrid (lex={lex_score:.3f}, sem={sem_score:.3f})"
            else:
                combined = lex_score
                reason = f"tfidf={lex_score:.3f}"

            # Boost by quality and usage popularity (log scale)
            popularity_boost = 1.0 + 0.05 * math.log1p(skill.usage_count)
            combined *= skill.avg_quality * popularity_boost

            results.append(SkillSearchResult(skill=skill, score=combined, match_reason=reason))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Bundle helpers
    # ------------------------------------------------------------------

    async def get_bundle(self, bundle_id: str) -> Optional[List[Skill]]:
        """Return the list of Skill objects in a bundle."""
        bundle = self.bundles.get(bundle_id)
        if bundle is None:
            return None
        return [self.skills[sid] for sid in bundle.skills if sid in self.skills]

    async def detect_and_load_bundle(self, text: str) -> Optional[SkillBundle]:
        """
        Return the first bundle whose trigger keywords appear in *text*.
        Performs case-insensitive substring matching.
        """
        text_lower = text.lower()
        for bundle in self.bundles.values():
            if any(kw.lower() in text_lower for kw in bundle.trigger_keywords):
                return bundle
        return None

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    def record_usage(self, skill_id: str, quality: float = 1.0) -> None:
        skill = self.skills.get(skill_id)
        if skill is None:
            return
        skill.usage_count += 1
        # EMA of quality
        alpha = 0.1
        skill.avg_quality = (1 - alpha) * skill.avg_quality + alpha * quality
        skill.last_used = time.time()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        categories: Dict[str, int] = defaultdict(int)
        for s in self.skills.values():
            categories[s.category] += 1
        return {
            "total_skills": len(self.skills),
            "total_bundles": len(self.bundles),
            "categories": dict(categories),
            "most_used": sorted(
                self.skills.values(), key=lambda s: s.usage_count, reverse=True
            )[:5][0].id if self.skills else None,
        }

    # ------------------------------------------------------------------
    # Directory loading
    # ------------------------------------------------------------------

    def load_from_directory(self, path: str) -> None:
        """Load all .md files from *path* as skills."""
        base = Path(path)
        if not base.is_dir():
            logger.warning("Skill directory not found: %s", path)
            return
        for md_file in base.glob("*.md"):
            skill = self._parse_skill_file(md_file)
            if skill is not None:
                self.register(skill)
        logger.info("Loaded skills from %s", path)

    def _parse_skill_file(self, path: Path) -> Optional[Skill]:
        """
        Parse a Markdown file with optional YAML frontmatter.

        Frontmatter format::

            ---
            id: my-skill
            name: My Skill
            category: backend
            tags: [python, api]
            version: "1.2"
            ---

            Content here …
        """
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error("Cannot read skill file %s: %s", path, exc)
            return None

        meta: Dict[str, Any] = {}
        content = raw

        if raw.startswith("---"):
            # Split out frontmatter
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                fm_text = parts[1].strip()
                content = parts[2].strip()
                # Minimal YAML-like key: value parser (no external dep)
                for line in fm_text.splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        k = k.strip()
                        v = v.strip()
                        # Handle inline lists: [a, b, c]
                        if v.startswith("[") and v.endswith("]"):
                            v = [i.strip().strip('"').strip("'") for i in v[1:-1].split(",")]
                        else:
                            v = v.strip('"').strip("'")
                        meta[k] = v

        stem = path.stem
        skill_id = meta.get("id", stem)
        name = meta.get("name", stem.replace("-", " ").title())
        category = meta.get("category", "general")
        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        version = str(meta.get("version", "1.0"))

        # Derive description from first non-empty line of content
        first_line = next(
            (ln.lstrip("#").strip() for ln in content.splitlines() if ln.strip()),
            name,
        )
        description = meta.get("description", first_line[:200])

        return Skill(
            id=skill_id,
            name=name,
            category=category,
            description=description,
            content=content,
            tags=tags if isinstance(tags, list) else [],
            version=version,
        )


# ---------------------------------------------------------------------------
# Pre-registered built-in skills (20 total)
# ---------------------------------------------------------------------------

def _bootstrap_registry(reg: EnhancedSkillRegistry) -> None:
    _SKILLS = [
        # compliance
        Skill(
            id="gdpr-compliance-check",
            name="GDPR Compliance Check",
            category="compliance",
            description="Verify GDPR compliance for data-handling code and APIs.",
            content=(
                "Check for: data minimisation, consent records, right-to-erasure, "
                "breach notification, DPA registration, lawful basis documentation."
            ),
            tags=["gdpr", "compliance", "privacy", "eu", "data-protection"],
        ),
        Skill(
            id="license-scanner",
            name="Open Source License Scanner",
            category="compliance",
            description="Detect and report open-source license conflicts in dependencies.",
            content=(
                "Parse package manifests (requirements.txt, package.json, go.mod). "
                "Flag GPL, AGPL, LGPL in commercial contexts.  "
                "Generate SBOM in SPDX format."
            ),
            tags=["license", "oss", "compliance", "sbom", "spdx"],
        ),
        # backend
        Skill(
            id="fastapi-crud-generator",
            name="FastAPI CRUD Generator",
            category="backend",
            description="Generate production-ready FastAPI CRUD endpoints from Pydantic models.",
            content=(
                "Generates: router with GET/POST/PUT/DELETE, Pydantic request/response schemas, "
                "SQLAlchemy repository layer, pytest fixtures, OpenAPI docstrings."
            ),
            tags=["fastapi", "crud", "python", "rest", "api"],
        ),
        Skill(
            id="async-db-pool",
            name="Async Database Connection Pool",
            category="backend",
            description="Configure asyncpg / aiomysql connection pools with health checks.",
            content=(
                "Best practices: pool_min_size=5, pool_max_size=20, "
                "command_timeout=10, max_inactive_connection_lifetime=300. "
                "Include heartbeat pings and automatic reconnection logic."
            ),
            tags=["database", "async", "postgres", "mysql", "pool"],
        ),
        # ai-orchestration
        Skill(
            id="llm-prompt-chaining",
            name="LLM Prompt Chaining",
            category="ai-orchestration",
            description="Design multi-step prompt chains with memory and branching.",
            content=(
                "Patterns: sequential chains, branching on classification output, "
                "RAG augmentation, tool-use loops, self-critique refinement cycles."
            ),
            tags=["llm", "prompting", "chain", "rag", "ai"],
        ),
        Skill(
            id="vector-search-pipeline",
            name="Vector Search Pipeline",
            category="ai-orchestration",
            description="Build semantic search with Qdrant + sentence-transformers.",
            content=(
                "Steps: embed documents with MiniLM-L6, upsert to Qdrant collection, "
                "query with payload filters, re-rank with cross-encoder.  "
                "Handle batching, retries, and incremental updates."
            ),
            tags=["vector", "search", "qdrant", "embeddings", "semantic"],
        ),
        # monitoring
        Skill(
            id="prometheus-metrics",
            name="Prometheus Metrics Setup",
            category="monitoring",
            description="Instrument FastAPI apps with Prometheus counters, histograms, and gauges.",
            content=(
                "Use prometheus-fastapi-instrumentator.  "
                "Expose /metrics.  Custom metrics: request latency histogram, "
                "error rate counter, active connections gauge, business KPI summaries."
            ),
            tags=["prometheus", "metrics", "monitoring", "fastapi", "observability"],
        ),
        Skill(
            id="structured-logging",
            name="Structured Logging with structlog",
            category="monitoring",
            description="Configure structlog for production JSON logging with trace IDs.",
            content=(
                "Processors: add_log_level, add_timestamp, JSONRenderer.  "
                "Bind request_id, user_id, service_name to context.  "
                "Integrate with Datadog / Loki / ELK."
            ),
            tags=["logging", "structlog", "json", "observability", "tracing"],
        ),
        # frontend
        Skill(
            id="react-query-hooks",
            name="React Query Data Fetching Hooks",
            category="frontend",
            description="Type-safe React Query v5 hooks with Zod validation and optimistic updates.",
            content=(
                "Patterns: useQuery with staleTime, useMutation with onMutate rollback, "
                "infiniteQuery for pagination, queryClient.prefetchQuery for SSR."
            ),
            tags=["react", "query", "typescript", "hooks", "frontend"],
        ),
        Skill(
            id="tailwind-design-system",
            name="Tailwind CSS Design System",
            category="frontend",
            description="Build a scalable design system with Tailwind tokens and Radix primitives.",
            content=(
                "Define: color palette (oklch), spacing scale, typography, shadows. "
                "Create compound components with class-variance-authority (cva). "
                "Dark mode with data-theme attribute."
            ),
            tags=["tailwind", "css", "design-system", "radix", "frontend"],
        ),
        # security
        Skill(
            id="jwt-auth-middleware",
            name="JWT Authentication Middleware",
            category="security",
            description="Production FastAPI JWT middleware with RS256, refresh tokens, and revocation.",
            content=(
                "Components: RS256 key-pair rotation, access token (15 min), "
                "refresh token (7 day) stored in HttpOnly cookie, "
                "Redis-backed revocation list, rate-limited /auth/refresh endpoint."
            ),
            tags=["jwt", "auth", "security", "fastapi", "oauth2"],
        ),
        Skill(
            id="secrets-manager",
            name="Secrets Manager Integration",
            category="security",
            description="Fetch and rotate secrets from AWS Secrets Manager or HashiCorp Vault.",
            content=(
                "Pattern: lazy-load secrets at startup, cache with TTL=300 s, "
                "background rotation task, emergency rotation via /admin/rotate-secret. "
                "Never log secret values."
            ),
            tags=["secrets", "aws", "vault", "security", "rotation"],
        ),
        # devops
        Skill(
            id="docker-multistage-build",
            name="Docker Multi-Stage Build",
            category="devops",
            description="Optimise Python Docker images with multi-stage builds and distroless base.",
            content=(
                "Stages: builder (install deps), runner (distroless/python3.12). "
                "Use uv for fast dependency resolution.  "
                "Final image < 150 MB.  Include HEALTHCHECK and non-root USER."
            ),
            tags=["docker", "devops", "python", "containerisation", "ci"],
        ),
        Skill(
            id="github-actions-ci",
            name="GitHub Actions CI Pipeline",
            category="devops",
            description="Full CI pipeline: lint, type-check, test, security scan, build, push.",
            content=(
                "Jobs: ruff + mypy, pytest with coverage, trivy container scan, "
                "Docker build + push to GHCR, Helm chart update PR.  "
                "Concurrency groups for PR deduplication."
            ),
            tags=["github-actions", "ci", "cd", "devops", "docker"],
        ),
        # data
        Skill(
            id="pandas-etl-pipeline",
            name="Pandas ETL Pipeline",
            category="data",
            description="Build robust ETL pipelines with pandas, great_expectations, and Airflow.",
            content=(
                "Steps: extract from S3/DB, validate with GE checkpoints, "
                "transform with pandas-on-Spark, load to data warehouse. "
                "Include idempotency, backfill logic, and alerting."
            ),
            tags=["pandas", "etl", "data", "airflow", "great-expectations"],
        ),
        Skill(
            id="redis-caching-patterns",
            name="Redis Caching Patterns",
            category="data",
            description="Cache-aside, write-through, and pub/sub patterns with aioredis.",
            content=(
                "Patterns: cache-aside with dogpile prevention, write-through with TTL jitter, "
                "pub/sub for invalidation, Redis Streams for event sourcing, "
                "Bloom filter for negative caching."
            ),
            tags=["redis", "caching", "async", "patterns", "data"],
        ),
        # extra compliance / ai
        Skill(
            id="model-card-generator",
            name="ML Model Card Generator",
            category="compliance",
            description="Auto-generate model cards following Hugging Face + EU AI Act standards.",
            content=(
                "Sections: model description, intended use, limitations, "
                "bias & fairness evaluation, training data sources, "
                "carbon footprint, regulatory compliance status."
            ),
            tags=["model-card", "ml", "compliance", "ai-act", "fairness"],
        ),
        Skill(
            id="embedding-drift-detector",
            name="Embedding Drift Detector",
            category="ai-orchestration",
            description="Detect concept drift in embedding distributions using statistical tests.",
            content=(
                "Methods: MMD (Maximum Mean Discrepancy), KL-divergence on PCA-reduced embeddings, "
                "cosine similarity distribution shifts.  Alert when drift > threshold."
            ),
            tags=["embeddings", "drift", "monitoring", "statistics", "ml"],
        ),
        Skill(
            id="rate-limiter-sliding-window",
            name="Sliding Window Rate Limiter",
            category="backend",
            description="Implement a token-bucket / sliding-window rate limiter with Redis.",
            content=(
                "Algorithm: Lua script on Redis for atomic sliding-window check. "
                "Keys: per-user, per-IP, per-endpoint.  "
                "Return Retry-After header on 429.  Bypass for internal subnets."
            ),
            tags=["rate-limiting", "redis", "backend", "security", "api"],
        ),
        Skill(
            id="graphql-federation-gateway",
            name="GraphQL Federation Gateway",
            category="backend",
            description="Configure Apollo Federation gateway with subgraphs and supergraph schema.",
            content=(
                "Setup: rover supergraph compose, Apollo Router config, "
                "@key entity resolution, @external fields, subscription passthrough. "
                "Persisted queries for production."
            ),
            tags=["graphql", "federation", "apollo", "gateway", "backend"],
        ),
    ]

    for skill in _SKILLS:
        reg.register(skill)

    # Bundles
    reg.register_bundle(SkillBundle(
        id="compliance-audit",
        name="Compliance Audit Bundle",
        trigger_keywords=["gdpr", "compliance", "audit", "license", "privacy"],
        skills=["gdpr-compliance-check", "license-scanner", "model-card-generator"],
        description="Full compliance audit: GDPR, OSS licensing, ML model cards.",
    ))
    reg.register_bundle(SkillBundle(
        id="backend-api",
        name="Backend API Bundle",
        trigger_keywords=["fastapi", "api", "rest", "crud", "endpoint"],
        skills=["fastapi-crud-generator", "async-db-pool", "jwt-auth-middleware",
                "rate-limiter-sliding-window"],
        description="Complete backend API stack with auth, database, and rate limiting.",
    ))
    reg.register_bundle(SkillBundle(
        id="ai-stack",
        name="AI Orchestration Bundle",
        trigger_keywords=["embedding", "vector", "llm", "semantic", "rag"],
        skills=["vector-search-pipeline", "llm-prompt-chaining",
                "embedding-drift-detector"],
        description="AI pipeline: embeddings, vector search, LLM chaining, drift detection.",
    ))
    reg.register_bundle(SkillBundle(
        id="observability",
        name="Observability Bundle",
        trigger_keywords=["monitoring", "metrics", "logging", "tracing", "observability"],
        skills=["prometheus-metrics", "structured-logging"],
        description="Full observability stack: Prometheus metrics and structured logging.",
    ))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

registry = EnhancedSkillRegistry()
_bootstrap_registry(registry)


# ---------------------------------------------------------------------------
# Convenience async function
# ---------------------------------------------------------------------------

async def route_skill_request(query: str) -> List[SkillSearchResult]:
    """
    Search the global registry for skills matching *query*.
    Also checks for bundle activation keywords and appends bundle skills.
    """
    results = await registry.search(query, top_k=10)

    # Check if a bundle should be loaded
    bundle = await registry.detect_and_load_bundle(query)
    if bundle is not None:
        bundle_skills = await registry.get_bundle(bundle.id)
        if bundle_skills:
            existing_ids = {r.skill.id for r in results}
            for skill in bundle_skills:
                if skill.id not in existing_ids:
                    results.append(SkillSearchResult(
                        skill=skill,
                        score=0.5,
                        match_reason=f"bundle:{bundle.id}",
                    ))

    return results
