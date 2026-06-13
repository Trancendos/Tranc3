#!/usr/bin/env python3
"""
scripts/generate_env.py — Automated .env generator for Tranc3.

Generates a ready-to-run .env for local development:
  - All cryptographic secrets auto-generated (never CHANGE_ME left behind)
  - Detects running services (PostgreSQL, Redis/Valkey, Qdrant, Ollama)
  - Falls back to zero-dependency local alternatives (SQLite, in-memory cache)
  - Idempotent: re-running preserves existing secrets, only fills blanks
  - Validates output and prints a health summary

Usage:
  python scripts/generate_env.py              # interactive (default)
  python scripts/generate_env.py --force      # overwrite existing .env
  python scripts/generate_env.py --check      # validate .env only, no writes
  python scripts/generate_env.py --prod       # production mode (stricter, no SQLite)
"""

from __future__ import annotations

import argparse
import secrets
import socket
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# ── ANSI colour helpers ────────────────────────────────────────────────────────
_RESET = "\033[0m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"


def ok(msg: str) -> None:
    print(f"  {_GREEN}✓{_RESET}  {msg}")


def warn(msg: str) -> None:
    print(f"  {_YELLOW}⚠{_RESET}  {msg}")


def err(msg: str) -> None:
    print(f"  {_RED}✗{_RESET}  {msg}")


def info(msg: str) -> None:
    print(f"  {_CYAN}→{_RESET}  {msg}")


def section(title: str) -> None:
    print(f"\n{_BOLD}{title}{_RESET}")
    print("─" * 60)


# ── Secret generation ─────────────────────────────────────────────────────────

def gen_secret(n_bytes: int = 32) -> str:
    return secrets.token_hex(n_bytes)


def gen_secret_16() -> str:
    return secrets.token_hex(16)  # exactly 32 chars hex


# ── Service detection ─────────────────────────────────────────────────────────

def port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_postgres() -> str | None:
    """Return a working PostgreSQL URL or None."""
    candidates = [
        "postgresql://tranc3:tranc3dev@localhost:5432/tranc3",
        "postgresql://postgres:postgres@localhost:5432/postgres",
        "postgresql://postgres:tranc3dev@localhost:5432/tranc3",
    ]
    if port_open("localhost", 5432):
        # Port is open — try psycopg2 connect
        try:
            import psycopg2  # noqa: PLC0415

            for url in candidates:
                try:
                    conn = psycopg2.connect(url, connect_timeout=2)
                    conn.close()
                    return url
                except Exception:
                    continue
        except ImportError:
            # psycopg2 not available — assume it works if port is open
            return candidates[0]
    return None


def detect_redis() -> str | None:
    if port_open("localhost", 6379):
        return "redis://localhost:6379/0"
    return None


def detect_qdrant() -> str | None:
    if port_open("localhost", 6333):
        return "http://localhost:6333"
    return None


def detect_ollama() -> str | None:
    if port_open("localhost", 11434):
        return "http://localhost:11434"
    return None


def detect_nats() -> str | None:
    if port_open("localhost", 4222):
        return "nats://localhost:4222"
    return None


def detect_vault() -> str | None:
    if port_open("localhost", 8200):
        return "http://localhost:8200"
    return None


# ── Existing .env parser ───────────────────────────────────────────────────────

def load_existing_env(path: Path) -> dict[str, str]:
    """Parse existing .env preserving all values (including comments)."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        result[key.strip()] = value.strip()
    return result


def is_placeholder(value: str) -> bool:
    """Return True if a value is clearly a placeholder that needs replacing."""
    placeholder_patterns = [
        "CHANGE_ME",
        "your-",
        "...",
        "sk_test_...",
        "whsec_...",
        "price_...",
        "eyJ...",
        "# ",
        "REQUIRED",
    ]
    return any(p in value for p in placeholder_patterns) or value == ""


# ── Core env builder ──────────────────────────────────────────────────────────

def build_env(
    existing: dict[str, str],
    prod: bool = False,
) -> dict[str, str]:
    """
    Build the complete env dict.
    Existing non-placeholder values are preserved.
    All secrets are generated if missing/placeholder.
    Service URLs are auto-detected.
    """
    env: dict[str, str] = dict(existing)

    def get_or_gen(key: str, generator: Any, *, force: bool = False) -> str:
        cur = env.get(key, "")
        if force or not cur or is_placeholder(cur):
            val = generator() if callable(generator) else generator
            env[key] = val
            return val
        return cur

    def get_or_detect(key: str, detected: str | None, fallback: str) -> str:
        cur = env.get(key, "")
        if cur and not is_placeholder(cur):
            return cur
        val = detected or fallback
        env[key] = val
        return val

    # ── Core secrets ──────────────────────────────────────────────────────────
    get_or_gen("SECRET_KEY", gen_secret)
    get_or_gen("JWT_SECRET", gen_secret)
    get_or_gen("INTERNAL_SECRET", gen_secret)
    get_or_gen("MASTER_KEY_SEED", gen_secret)
    get_or_gen("AUDIT_SIGNING_KEY", gen_secret)
    get_or_gen("CITADEL_WEBHOOK_SECRET", gen_secret)
    get_or_gen("IP_PROTECTION_KEY", gen_secret)
    get_or_gen("BACKUP_API_TOKEN", gen_secret)

    # ── CranBania / Town Hall secrets ─────────────────────────────────────────
    get_or_gen("CRANBANIA_API_KEY", gen_secret)
    get_or_gen("CRANBANIA_CRON_SECRET", gen_secret)
    get_or_gen("CRANBANIA_WEBHOOK_SECRET", gen_secret)

    # ── Infrastructure secrets ────────────────────────────────────────────────
    get_or_gen("WOODPECKER_SECRET", gen_secret)
    get_or_gen("KRAKEND_JWT_SECRET", lambda: env.get("JWT_SECRET", gen_secret()))
    get_or_gen("PENPOT_SECRET_KEY", gen_secret)

    # ── Langfuse secrets ──────────────────────────────────────────────────────
    get_or_gen("LANGFUSE_SECRET", gen_secret)
    get_or_gen("LANGFUSE_SALT", gen_secret)

    # ── Cal.com secrets ───────────────────────────────────────────────────────
    get_or_gen("CALCOM_DB_PASSWORD", gen_secret_16)
    get_or_gen("CALCOM_NEXTAUTH_SECRET", gen_secret)
    get_or_gen("CALCOM_ENCRYPTION_KEY", gen_secret_16)  # Must be exactly 32 chars

    # ── Outline secrets ───────────────────────────────────────────────────────
    get_or_gen("OUTLINE_DB_PASSWORD", gen_secret_16)
    get_or_gen("OUTLINE_SECRET_KEY", gen_secret)
    get_or_gen("OUTLINE_UTILS_SECRET", gen_secret)

    # ── SigNoz ───────────────────────────────────────────────────────────────
    get_or_gen("SIGNOZ_CLICKHOUSE_PASSWORD", gen_secret_16)

    # ── Environment settings ──────────────────────────────────────────────────
    env.setdefault("ENVIRONMENT", "production" if prod else "development")
    env.setdefault("DEBUG", "false")
    env.setdefault("PORT", "8000")
    env.setdefault("LOG_LEVEL", "INFO")

    # ── Database detection ────────────────────────────────────────────────────
    pg_url = detect_postgres()
    if prod:
        if not pg_url and not (env.get("DATABASE_URL", "") and not is_placeholder(env["DATABASE_URL"])):
            warn("PostgreSQL not detected — DATABASE_URL must be set manually for production")
        get_or_detect("DATABASE_URL", pg_url, "postgresql://tranc3:tranc3dev@localhost:5432/tranc3")
        get_or_detect("SETTINGS_DB_URL", pg_url, env.get("DATABASE_URL", ""))
    else:
        # Dev: fall back to SQLite if Postgres unavailable
        if pg_url:
            get_or_detect("DATABASE_URL", pg_url, pg_url)
            get_or_detect("SETTINGS_DB_URL", pg_url, pg_url)
        else:
            sqlite_url = "sqlite:///./data/tranc3.db"
            cur = env.get("DATABASE_URL", "")
            if not cur or is_placeholder(cur) or cur.startswith("postgresql://tranc3:tranc3dev"):
                env["DATABASE_URL"] = sqlite_url
                env["SETTINGS_DB_URL"] = sqlite_url

    # ── Redis detection ───────────────────────────────────────────────────────
    redis_url = detect_redis()
    get_or_detect("REDIS_URL", redis_url, "redis://localhost:6379/0")
    get_or_detect("VALKEY_URL", redis_url, env.get("REDIS_URL", "redis://localhost:6379/0"))

    # ── Qdrant detection ──────────────────────────────────────────────────────
    qdrant_url = detect_qdrant()
    get_or_detect("QDRANT_URL", qdrant_url, "http://localhost:6333")
    env.setdefault("QDRANT_COLLECTION", "tranc3-memory")

    # ── Ollama detection ──────────────────────────────────────────────────────
    ollama_url = detect_ollama()
    get_or_detect("OLLAMA_URL", ollama_url, "http://localhost:11434")
    env.setdefault("OLLAMA_MODEL", "llama3.2:1b")
    env.setdefault("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # ── NATS ──────────────────────────────────────────────────────────────────
    nats_url = detect_nats()
    get_or_detect("NATS_URL", nats_url, "nats://localhost:4222")
    env.setdefault("NATS_STREAM_NAME", "TRANC3")
    env.setdefault("NATS_CONSUMER_NAME", "tranc3-event-bus")

    # ── Vault ─────────────────────────────────────────────────────────────────
    vault_url = detect_vault()
    get_or_detect("VAULT_ADDR", vault_url, "http://localhost:8200")
    get_or_detect("OPENBAO_ADDR", vault_url, "http://localhost:8200")
    env.setdefault("VAULT_NAMESPACE", "")

    # ── JWT / Auth settings ───────────────────────────────────────────────────
    env.setdefault("JWT_ALGORITHM", "HS256")
    env.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    env.setdefault("JWT_EXPIRY_MINUTES", "60")
    env.setdefault("REFRESH_EXPIRY_DAYS", "7")
    env.setdefault("REQUIRE_AUTH", "true")
    env.setdefault("RATE_LIMIT_PER_MINUTE", "60")
    env.setdefault("SUPABASE_JWT_SECRET", env.get("JWT_SECRET", ""))

    # ── AI / ML settings ──────────────────────────────────────────────────────
    env.setdefault("EMBED_MODEL", "all-MiniLM-L6-v2")
    env.setdefault("EMBED_DIM", "384")
    env.setdefault("VECTOR_STORE_DIR", "./data/vector_store")
    env.setdefault("MODEL_PATH", "./models/tranc3-base")
    env.setdefault("TOKENIZER_MODEL", "bert-base-multilingual-cased")
    env.setdefault("CACHE_DIR", "./cache")
    env.setdefault("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")
    env.setdefault("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")
    env.setdefault("GROQ_MODEL", "llama-3.1-8b-instant")

    # ── Platform features ─────────────────────────────────────────────────────
    env.setdefault("PLATFORM_INFRA_MODE", "CLOUD_ONLY")
    env.setdefault("SYSTEM_MODE", "CLOUD_ONLY")
    env.setdefault("ADAPTIVE_ROTATION_ENABLED", "true")
    env.setdefault("ADAPTIVE_ROTATION_CHAIN", "zero_cost_cloud")
    env.setdefault("ADAPTIVE_CLOUD_AUTO_ROTATE", "true")
    env.setdefault("ADAPTIVE_CLOUD_AUTO_ROTATE_SECONDS", "180")
    env.setdefault("ADAPTIVE_COOLDOWN_SECONDS", "300")
    env.setdefault("PROACTIVE_ORCHESTRATOR_ENABLED", "true")
    env.setdefault("PROACTIVE_INTERVAL_SECONDS", "600")
    env.setdefault("ENABLE_QUANTUM", "true")
    env.setdefault("ENABLE_CONSCIOUSNESS", "true")
    env.setdefault("ENABLE_NEUROMORPHIC", "false")
    env.setdefault("ENABLE_SELF_EVOLUTION", "true")
    env.setdefault("ENABLE_SWARM", "false")
    env.setdefault("ENABLE_EVOLUTION", "true")
    env.setdefault("ENABLE_HOLOGRAPHIC", "false")
    env.setdefault("ENABLE_QUANTUM_OPT", "false")

    # ── Observability ─────────────────────────────────────────────────────────
    env.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    env.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    env.setdefault("HEALTH_CHECK_INTERVAL_SEC", "30")

    # ── Service URLs ──────────────────────────────────────────────────────────
    env.setdefault("FRONTEND_URL", "http://localhost:3000")
    env.setdefault("VITE_API_URL", "http://localhost:8000")
    env.setdefault("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:8071")
    env.setdefault("INFINITY_ONE_URL", "http://localhost:8043")
    env.setdefault("USERS_SERVICE_URL", "http://localhost:8006")
    env.setdefault("PAYMENTS_SERVICE_URL", "http://localhost:8013")
    env.setdefault("PRODUCTS_SERVICE_URL", "http://localhost:8011")
    env.setdefault("ORDERS_SERVICE_URL", "http://localhost:8012")
    env.setdefault("EMBED_URL", "http://localhost:8000/embed")
    env.setdefault("LANGFUSE_HOST", "http://localhost:3002")
    env.setdefault("FORGEJO_URL", "http://forgejo:3000")
    env.setdefault("CALCOM_URL", "http://localhost:3010")
    env.setdefault("CALCOM_EMAIL_FROM", "noreply@trancendos.com")
    env.setdefault("OUTLINE_URL", "http://localhost:3011")
    env.setdefault("TEMPO_URL", "http://localhost:3200")
    env.setdefault("VICTORIA_METRICS_URL", "http://localhost:8428")
    env.setdefault("DTRACK_URL", "http://localhost:8081")

    # ── Storage / worker paths ────────────────────────────────────────────────
    env.setdefault("AUTH_DATABASE_PATH", "./data/auth.db")
    env.setdefault("VOID_DATA_DIR", "./data/void")
    env.setdefault("NANO_PORT", "8001")
    env.setdefault("PRIMARY_CLUSTER", "local")
    env.setdefault("AWS_ENABLED", "false")
    env.setdefault("AZURE_ENABLED", "false")
    env.setdefault("GCP_ENABLED", "false")
    env.setdefault("BLENDER_PATH", "/usr/bin/blender")
    env.setdefault("TRIPOSR_MODEL_DIR", "/app/models/triposr")
    env.setdefault("FFMPEG_PATH", "/usr/bin/ffmpeg")
    env.setdefault("PGVECTOR_TABLE", "tranc3_embeddings")
    env.setdefault("PGVECTOR_DIM", "384")

    # ── Magna Carta / CranBania ───────────────────────────────────────────────
    mc_submodule = REPO_ROOT / "compliance" / "magna-carta" / "config" / "magna_carta_config.json"
    magna_enabled = "true" if mc_submodule.exists() else "false"
    env.setdefault("MAGNA_CARTA_ENABLED", magna_enabled)
    env.setdefault(
        "MAGNA_CARTA_CONFIG_PATH",
        "./compliance/magna-carta/config/magna_carta_config.json",
    )
    env.setdefault(
        "MAGNA_CARTA_REGISTER_PATH",
        "./compliance/magna-carta/compliance/magna_carta_register.yaml",
    )
    env.setdefault("MAGNA_CARTA_AUDIT", "true")
    env.setdefault("CRANBANIA_PORT", "8071")
    env.setdefault("CRANBANIA_DATA_DIR", "./data/cranbania")
    env.setdefault("CRANBANIA_OBSERVATORY_URL", "http://localhost:8007")
    env.setdefault("CRANBANIA_FORGEJO_URL", "http://forgejo:3000")

    return env


# ── Env file writer ───────────────────────────────────────────────────────────

_SECTION_ORDER = [
    # (header comment, key prefixes)
    ("# ── Core", ["SECRET_KEY", "ENVIRONMENT", "DEBUG", "PORT", "LOG_LEVEL"]),
    ("# ── Database", ["DATABASE_URL", "SETTINGS_DB_URL", "SUPABASE"]),
    ("# ── Cache / Queue", ["REDIS_URL", "VALKEY_URL", "NATS_"]),
    ("# ── Vector DB", ["QDRANT_", "PGVECTOR_"]),
    ("# ── AI / ML", ["OLLAMA_", "OPENROUTER_", "HF_", "GROQ_", "GOOGLE_", "CEREBRAS_",
                       "SAMBANOVA_", "DEEPSEEK_", "EMBED_", "MODEL_", "TOKENIZER_", "CACHE_DIR",
                       "VECTOR_STORE_DIR", "LANGFUSE_"]),
    ("# ── JWT / Auth", ["JWT_", "ACCESS_TOKEN_", "REFRESH_EXPIRY_", "REQUIRE_AUTH",
                          "RATE_LIMIT_", "SUPABASE_JWT_"]),
    ("# ── Platform Features", ["PLATFORM_", "SYSTEM_MODE", "ADAPTIVE_", "PROACTIVE_",
                                  "ENABLE_", "HEALTH_CHECK_"]),
    ("# ── Payments", ["STRIPE_"]),
    ("# ── Observability", ["OTEL_", "TEMPO_", "VICTORIA_", "DTRACK_"]),
    ("# ── Security / Vault", ["INTERNAL_SECRET", "MASTER_KEY_SEED", "AUDIT_SIGNING_",
                                 "IP_PROTECTION_", "BACKUP_API_", "CITADEL_",
                                 "VAULT_", "OPENBAO_"]),
    ("# ── Service URLs", ["FRONTEND_URL", "VITE_", "CORS_", "INFINITY_ONE_", "USERS_SERVICE_",
                             "PAYMENTS_SERVICE_", "PRODUCTS_SERVICE_", "ORDERS_SERVICE_",
                             "EMBED_URL"]),
    ("# ── Workers / Storage", ["AUTH_DATABASE_", "VOID_DATA_", "NANO_PORT", "PRIMARY_CLUSTER",
                                   "AWS_ENABLED", "AZURE_ENABLED", "GCP_ENABLED",
                                   "BLENDER_PATH", "TRIPOSR_", "FFMPEG_PATH"]),
    ("# ── CI/CD / Infrastructure", ["FORGEJO_", "WOODPECKER_", "KRAKEND_", "PENPOT_",
                                       "CALCOM_", "OUTLINE_", "SIGNOZ_"]),
    ("# ── Magna Carta / Town Hall (CranBania)", ["MAGNA_CARTA_", "CRANBANIA_"]),
    ("# ── External API Keys (optional — leave blank if not using)", [
        "OPENROUTER_API_KEY", "HF_API_KEY", "GROQ_API_KEY",
        "GOOGLE_GEMINI_API_KEY", "CEREBRAS_API_KEY", "SAMBANOVA_API_KEY",
        "DEEPSEEK_API_KEY", "DTRACK_API_KEY", "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY", "WOODPECKER_FORGEJO_CLIENT",
        "WOODPECKER_FORGEJO_SECRET", "WOODPECKER_AGENT_TOKEN",
        "VAULT_TOKEN", "VAULT_NAMESPACE",
    ]),
]


def render_env(env: dict[str, str]) -> str:
    """Render env dict to .env file content, grouped by section."""
    written: set[str] = set()
    lines: list[str] = [
        "# TRANC3 .env — auto-generated by scripts/generate_env.py",
        "# Re-run to refresh: python scripts/generate_env.py",
        "# NEVER commit this file to git",
        "",
    ]

    for section_header, prefixes in _SECTION_ORDER:
        section_keys = [
            k for k in env
            if any(k.startswith(p) or k == p for p in prefixes)
            and k not in written
        ]
        if not section_keys:
            continue
        lines.append(section_header)
        for k in section_keys:
            lines.append(f"{k}={env[k]}")
            written.add(k)
        lines.append("")

    # Anything not yet written goes in a catch-all section
    remainder = [k for k in env if k not in written]
    if remainder:
        lines.append("# ── Miscellaneous")
        for k in remainder:
            lines.append(f"{k}={env[k]}")
        lines.append("")

    return "\n".join(lines)


# ── Validation ────────────────────────────────────────────────────────────────

_REQUIRED_SECRETS = [
    "SECRET_KEY",
    "JWT_SECRET",
    "INTERNAL_SECRET",
    "MASTER_KEY_SEED",
]

_REQUIRED_URLS = [
    "DATABASE_URL",
    "REDIS_URL",
    "QDRANT_URL",
]


def validate_env(env: dict[str, str]) -> list[str]:
    """Return list of validation errors."""
    errors: list[str] = []

    for key in _REQUIRED_SECRETS:
        val = env.get(key, "")
        if not val or is_placeholder(val):
            errors.append(f"{key} is missing or placeholder")
        elif len(val) < 32:
            errors.append(f"{key} is too short (< 32 chars) — security risk")

    for key in _REQUIRED_URLS:
        val = env.get(key, "")
        if not val or is_placeholder(val):
            errors.append(f"{key} is missing or placeholder")

    mc_enabled = env.get("MAGNA_CARTA_ENABLED", "false").lower() == "true"
    mc_cfg = env.get("MAGNA_CARTA_CONFIG_PATH", "")
    if mc_enabled and mc_cfg:
        cfg_path = REPO_ROOT / mc_cfg.lstrip("./")
        if not cfg_path.exists():
            errors.append(
                f"MAGNA_CARTA_ENABLED=true but config not found at {mc_cfg} "
                f"— run scripts/setup_external_repos.sh first"
            )

    return errors


# ── Data directory setup ──────────────────────────────────────────────────────

def ensure_data_dirs() -> None:
    dirs = [
        REPO_ROOT / "data",
        REPO_ROOT / "data" / "void",
        REPO_ROOT / "data" / "cranbania",
        REPO_ROOT / "data" / "vector_store",
        REPO_ROOT / "cache",
        REPO_ROOT / "models",
        REPO_ROOT / "logs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="Overwrite existing .env without prompting")
    parser.add_argument("--check", action="store_true", help="Validate .env only, no writes")
    parser.add_argument("--prod", action="store_true", help="Production mode (stricter validation, no SQLite fallback)")
    parser.add_argument("--quiet", action="store_true", help="Suppress informational output")
    args = parser.parse_args()

    print(f"\n{_BOLD}{_CYAN}Tranc3 Environment Setup{_RESET}")
    print("=" * 60)

    # ── Check-only mode ───────────────────────────────────────────────────────
    if args.check:
        section("Validating .env")
        if not ENV_FILE.exists():
            err(".env does not exist — run: python scripts/generate_env.py")
            return 1
        existing = load_existing_env(ENV_FILE)
        errors = validate_env(existing)
        if errors:
            for e in errors:
                err(e)
            return 1
        ok(f".env is valid ({len(existing)} variables)")
        return 0

    # ── Detect services ───────────────────────────────────────────────────────
    section("Detecting local services")
    pg = detect_postgres()
    redis = detect_redis()
    qdrant = detect_qdrant()
    ollama = detect_ollama()
    nats = detect_nats()
    vault = detect_vault()

    ok(f"PostgreSQL: {'found at ' + pg if pg else 'not running → SQLite fallback'}") if not args.quiet else None
    ok(f"Redis/Valkey: {'found at ' + redis if redis else 'not running → in-memory fallback'}") if not args.quiet else None
    ok(f"Qdrant: {'found at ' + qdrant if qdrant else 'not running → in-memory fallback'}") if not args.quiet else None
    info(f"Ollama: {'found at ' + ollama if ollama else 'not running (optional — zero-cost LLM)'}") if not args.quiet else None
    info(f"NATS: {'found at ' + nats if nats else 'not running (optional)'}") if not args.quiet else None
    info(f"Vault: {'found at ' + vault if vault else 'not running (optional)'}") if not args.quiet else None

    # ── Load or create ────────────────────────────────────────────────────────
    section("Generating secrets and configuration")
    existing = load_existing_env(ENV_FILE)
    _ = not ENV_FILE.exists()  # reserved for future "new file" detection

    if ENV_FILE.exists() and not args.force:
        info(f"Found existing .env ({len(existing)} variables) — preserving secrets, filling blanks")
    elif ENV_FILE.exists() and args.force:
        warn("--force: overwriting existing .env (secrets will be regenerated)")
        existing = {}

    env = build_env(existing, prod=args.prod)

    # ── Ensure data dirs ──────────────────────────────────────────────────────
    ensure_data_dirs()
    ok("Created data/, cache/, models/, logs/ directories")

    # ── Write ─────────────────────────────────────────────────────────────────
    content = render_env(env)
    ENV_FILE.write_text(content, encoding="utf-8")
    ENV_FILE.chmod(0o600)  # owner read/write only
    ok(f"Written .env ({len(env)} variables, mode 600)")

    # ── Validate ──────────────────────────────────────────────────────────────
    section("Validation")
    errors = validate_env(env)
    if errors:
        for e in errors:
            warn(e)
    else:
        ok("All required secrets and URLs are set")

    # ── Summary ───────────────────────────────────────────────────────────────
    section("Summary")
    db = env.get("DATABASE_URL", "")
    if db.startswith("sqlite"):
        info("Database: SQLite (local dev) — run 'make migrate' to apply schema")
    else:
        ok(f"Database: PostgreSQL at {db.split('@')[-1] if '@' in db else db}")

    redis_val = env.get("REDIS_URL", "")
    ok(f"Cache: {redis_val}") if redis else warn("Cache: Redis not running — some features may degrade")

    qdrant_val = env.get("QDRANT_URL", "")
    ok(f"Vector DB: {qdrant_val}") if qdrant else warn("Vector DB: Qdrant not running — vector search will use in-memory fallback")

    mc = env.get("MAGNA_CARTA_ENABLED", "false")
    mc_path = REPO_ROOT / "compliance" / "magna-carta"
    if mc_path.exists():
        ok(f"Magna Carta: {'ENABLED' if mc == 'true' else 'available (set MAGNA_CARTA_ENABLED=true to activate)'}")
    else:
        warn("Magna Carta: submodule not cloned — run scripts/setup_external_repos.sh")

    print(f"\n{_GREEN}{_BOLD}✓ .env ready.{_RESET}")
    print("\nNext steps:")
    print("  make migrate       — apply database schema")
    print("  make dev-api       — start FastAPI backend on :8000")
    print("  make compliance-check — run compliance report")
    if not pg:
        print("\n  Note: PostgreSQL not detected. SQLite is used for local dev.")
        print("  For production, set DATABASE_URL to a real PostgreSQL instance.")

    # Audit key reminder
    import pathlib as _pl
    _key_file = _pl.Path("logs/audit/.audit_signing_key")
    if env.get("AUDIT_SIGNING_KEY") and not is_placeholder(env.get("AUDIT_SIGNING_KEY", "")):
        ok("AUDIT_SIGNING_KEY written to .env — add to Forgejo secrets for CI verification")
    elif _key_file.exists():
        warn(
            f"AUDIT_SIGNING_KEY was generated from existing key file {_key_file}. "
            "Copy the value from .env into Forgejo → Settings → Secrets → AUDIT_SIGNING_KEY"
        )

    return 0 if not errors else 0  # warnings don't fail the script


if __name__ == "__main__":
    sys.exit(main())
