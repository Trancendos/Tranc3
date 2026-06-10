# src/personality/spawner.py
# Generates a new Tranc3 repository scaffold for a specific personality instance.
# Each spawned repo is a self-contained Tranc3 derivative pre-configured with
# one dominant personality, its domain skills, and its system-prompt identity.
#
# Security: All user-supplied path components (output_dir, repo_name) are
# validated through Dimensional.path_validation to prevent path traversal.

from __future__ import annotations

import json
import logging
import shutil
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from Dimensional.path_validation import PathTraversalError, safe_join, sanitize_filename, validate_path

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parents[2]  # /home/user/Tranc3
_PROFILES_DIR = Path(__file__).parent / "profiles"

# Allowed output directory roots — spawn targets must land under one of these.
# In production, restrict this to a dedicated sandbox directory.
_ALLOWED_OUTPUT_ROOTS = [
    Path.cwd().resolve(),  # current working directory
    Path("/tmp").resolve(),  # nosec B108 — system temp, validated by safe_join below
    Path.home().resolve(),  # user home
]


def _resolve_output_base(output_dir: str) -> Path:
    """Resolve and validate the output directory against allowed roots.

    The output_dir must resolve to a path under one of the allowed roots.
    This prevents an attacker from specifying arbitrary filesystem locations.

    Args:
        output_dir: User-supplied output directory string.

    Returns:
        Resolved, validated base Path for output.

    Raises:
        PathTraversalError: If the path escapes all allowed roots.
        FileNotFoundError: If the parent of the path does not exist.
    """
    for allowed_root in _ALLOWED_OUTPUT_ROOTS:
        try:
            return validate_path(output_dir, allowed_root, allow_create=True)
        except PathTraversalError:
            continue

    raise PathTraversalError(
        f"Output directory {output_dir} is not under any allowed root. "
        f"Allowed root count: {len(_ALLOWED_OUTPUT_ROOTS)}",
    )


class PersonalitySpawner:
    """
    Reads a personality profile JSON and writes a new repo scaffold at the
    given output path.  The scaffold includes:
      - tranc3_config.yaml   tailored to the personality
      - src/personality/active_profile.json
      - .env.example         with personality-specific notes
      - api_personality.py   a minimal FastAPI app wired to the personality
      - README.md            with identity, purpose, and quickstart

    Security: All path construction uses safe_join() to prevent traversal.
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, Dict] = self._load_all_profiles()

    # ─── Public API ──────────────────────────────────────────────────

    def spawn(
        self,
        personality_id: str,
        repo_name: str,
        output_dir: str = "./spawned",
    ) -> Dict[str, Any]:
        profile = self._profiles.get(personality_id)
        if not profile:
            available = list(self._profiles.keys())
            raise ValueError(f"Unknown personality '{personality_id}'. Available: {available}")

        # Validate and sanitize repo_name — prevents directory traversal
        safe_repo_name = sanitize_filename(repo_name)

        # Validate output_dir is under an allowed root
        output_base = _resolve_output_base(output_dir)

        # Safely construct the target path under the validated output base
        target = safe_join(output_base, safe_repo_name)
        if target.exists():
            raise FileExistsError(f"Target directory already exists: {target}")

        target.mkdir(parents=True, exist_ok=False)
        logger.info("Spawning personality '%s' into %s", personality_id, target)

        files_written = []
        files_written += self._write_config(target, profile)
        files_written += self._write_active_profile(target, profile)
        files_written += self._write_env_example(target, profile)
        files_written += self._write_api(target, profile, safe_repo_name)
        files_written += self._write_readme(target, profile, safe_repo_name)
        files_written += self._write_requirements(target)
        files_written += self._write_docker(target, profile, safe_repo_name)

        return {
            "personality": personality_id,
            "code_name": profile.get("code_name", personality_id),
            "repo_name": safe_repo_name,
            "output_path": str(target.resolve()),
            "files_written": files_written,
            "spawned_at": datetime.utcnow().isoformat(),
            "instructions": (
                f"cd {target}\n"
                f"cp .env.example .env  # fill in secrets\n"
                f"pip install -r requirements.txt\n"
                f"uvicorn api_personality:app --reload"
            ),
        }

    def list_personalities(self) -> list:
        return [
            {
                "id": pid,
                "code_name": p.get("code_name", pid),
                "domain": p.get("domain", "general"),
                "description": p.get("description", ""),
            }
            for pid, p in self._profiles.items()
        ]

    # ─── File writers ────────────────────────────────────────────────

    def _write_config(self, target: Path, profile: Dict) -> list:
        code_name = profile.get("code_name", profile["id"])
        domain = profile.get("domain", "general")
        behavior = profile.get("behavior", {})
        config = {
            "personality": {
                "active": profile["id"],
                "code_name": code_name,
                "domain": domain,
                "system_prompt_prefix": profile.get("system_prompt_prefix", ""),
            },
            "model": {
                "temperature": behavior.get("temperature", 0.7),
                "top_p": behavior.get("top_p", 0.9),
                "max_tokens": behavior.get("max_tokens", 512),
            },
            "skills": {
                "priority_domains": profile.get("skill_domains", []),
                "restricted_domains": profile.get("restricted_domains", []),
            },
            "mcp": {
                "tools_priority": profile.get("mcp_tools_priority", []),
            },
            "environment": "development",
        }
        # Safe path construction: target is already validated
        path = safe_join(target, "tranc3_config.yaml")
        import yaml  # type: ignore

        with open(path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        return [str(path)]

    def _write_active_profile(self, target: Path, profile: Dict) -> list:
        # Safe path construction under validated target
        profile_dir = safe_join(target, "src", "personality")
        profile_dir.mkdir(parents=True, exist_ok=True)
        path = safe_join(target, "src", "personality", "active_profile.json")
        with open(path, "w") as f:
            json.dump(profile, f, indent=2)
        return [str(path)]

    def _write_env_example(self, target: Path, profile: Dict) -> list:
        code_name = profile.get("code_name", "Tranc3")
        domain = profile.get("domain", "general")
        content = textwrap.dedent(f"""\
            # .env for {code_name} ({domain})
            # Copy to .env and fill in values. NEVER commit .env to git.

            ENVIRONMENT=development
            DEBUG=false
            PORT=8000

            # Auth (set in production)
            TRANC3_API_KEY=
            JWT_SECRET=
            REQUIRE_AUTH=false

            # CORS (comma-separated origins; use * only for dev)
            CORS_ORIGINS=*

            # Database (Supabase free tier)
            DATABASE_URL=
            SUPABASE_URL=
            SUPABASE_ANON_KEY=

            # Cache (Upstash Redis free tier)
            REDIS_URL=

            # Tranc3 local model (train with: python train.py --model-size small)
            TRANC3_MODEL_PATH=./models/tranc3-v1/tranc3-final.pt
            TRANC3_TOKENIZER_PATH=./models/tokenizer

            # Rate limiting
            RATE_LIMIT_PER_WINDOW=120
            RATE_WINDOW_SECONDS=60
        """)
        path = safe_join(target, ".env.example")
        path.write_text(content)
        return [str(path)]

    def _write_api(self, target: Path, profile: Dict, repo_name: str) -> list:
        code_name = profile.get("code_name", "Tranc3")
        personality_id = profile["id"]
        system_prompt = profile.get("system_prompt_prefix", f"You are {code_name}.")
        content = textwrap.dedent(f"""\
            # api_personality.py — {code_name}
            # Auto-generated by PersonalitySpawner from tranc3-base
            # Domain: {profile.get("domain", "general")}

            import os, time, json
            from contextlib import asynccontextmanager
            from typing import Any, Dict, Optional
            from fastapi import FastAPI, Depends, HTTPException, Request
            from fastapi.middleware.cors import CORSMiddleware
            from pydantic import BaseModel, Field

            _ENV = os.getenv("ENVIRONMENT", "development")
            _ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", os.getenv("ALLOWED_ORIGINS", "*")).split(",")

            ACTIVE_PERSONALITY = "{personality_id}"
            CODE_NAME = "{code_name}"
            SYSTEM_PROMPT_PREFIX = (
                "{system_prompt}"
            )


            class ChatRequest(BaseModel):
                message: str = Field(..., min_length=1, max_length=8192)
                context: Dict[str, Any] = {{}}


            @asynccontextmanager
            async def lifespan(app: FastAPI):
                from src.core.startup_validator import validate_startup
                validate_startup()
                # Import and initialise only what's needed for this personality
                try:
                    from src.main_enhanced import enhanced
                    await enhanced.initialize()
                    app.state.enhanced = enhanced
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Enhanced init partial: %s", e)
                    app.state.enhanced = None
                yield


            app = FastAPI(
                title=f"TRANC3 — {{CODE_NAME}}",
                description=SYSTEM_PROMPT_PREFIX,
                version="1.0.0",
                lifespan=lifespan,
                docs_url="/docs" if _ENV != "production" else None,
            )

            app.add_middleware(
                CORSMiddleware,
                allow_origins=_ALLOWED_ORIGINS,
                allow_credentials=True,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Authorization", "X-API-Key", "Content-Type"],
            )


            @app.get("/")
            async def root():
                return {{
                    "identity": CODE_NAME,
                    "personality": ACTIVE_PERSONALITY,
                    "domain": "{profile.get("domain", "general")}",
                    "status": "operational",
                    "ts": time.time(),
                }}


            @app.get("/health")
            async def health(request: Request):
                enhanced = request.app.state.enhanced
                if enhanced:
                    return await enhanced.get_system_health()
                return {{"status": "degraded", "reason": "enhanced not initialised"}}


            @app.post("/chat")
            async def chat(req: ChatRequest, request: Request):
                enhanced = request.app.state.enhanced
                if not enhanced:
                    raise HTTPException(503, "System not ready")
                context = dict(req.context)
                context["personality"] = ACTIVE_PERSONALITY
                context["system_prompt_prefix"] = SYSTEM_PROMPT_PREFIX
                return await enhanced.think(req.message, context)


            @app.get("/personality")
            async def personality_info():
                from src.personality.matrix import EnhancedPersonalityMatrix
                matrix = EnhancedPersonalityMatrix({{}})
                return {{
                    "code_name": CODE_NAME,
                    "personality_id": ACTIVE_PERSONALITY,
                    "description": matrix.get_personality_description(ACTIVE_PERSONALITY),
                    "vector": matrix.get_personality_vector(ACTIVE_PERSONALITY).tolist(),
                }}


            if __name__ == "__main__":
                import uvicorn
                uvicorn.run("api_personality:app", host="0.0.0.0",
                            port=int(os.getenv("PORT", "8000")),
                            reload=os.getenv("DEBUG", "false").lower() == "true")
        """)
        path = safe_join(target, "api_personality.py")
        path.write_text(content)
        return [str(path)]

    def _write_readme(self, target: Path, profile: Dict, repo_name: str) -> list:
        code_name = profile.get("code_name", repo_name)
        domain = profile.get("domain", "general")
        description = profile.get("description", "")
        skills = profile.get("skill_domains", [])
        system_prompt = profile.get("system_prompt_prefix", "")
        content = textwrap.dedent(f"""\
            # {code_name}

            > {description}

            **Domain:** {domain}
            **Base:** Tranc3 v3.0.0
            **Spawned:** {datetime.utcnow().strftime("%Y-%m-%d")}

            ## Identity

            {system_prompt}

            ## Skill Domains

            {chr(10).join(f"- `{s}`" for s in skills)}

            ## Quickstart

            ```bash
            cp .env.example .env
            # Edit .env and set required values (see comments)
            pip install -r requirements.txt
            uvicorn api_personality:app --reload
            ```

            ## Key Endpoints

            | Method | Path | Description |
            |--------|------|-------------|
            | GET | `/` | Identity and status |
            | GET | `/health` | System health |
            | POST | `/chat` | Chat with {code_name} |
            | GET | `/personality` | Personality vector |
            | GET | `/docs` | Swagger UI (dev only) |

            ## Spawning More Instances

            This repo was generated from the `tranc3-base` template. To spawn
            additional personality instances, run:

            ```bash
            python scripts/spawn_personality.py --personality <id> --repo-name <name>
            ```

            Available personalities: `dorris-fontaine`, `cornelius-macintyre`,
            `the-guardian`, `vesper-nightingale`, `atlas-meridian`.
        """)
        path = safe_join(target, "README.md")
        path.write_text(content)
        return [str(path)]

    def _write_requirements(self, target: Path) -> list:
        base_reqs = _BASE_DIR / "requirements.txt"
        path = safe_join(target, "requirements.txt")
        if base_reqs.exists():
            shutil.copy(base_reqs, path)
        else:
            path.write_text(
                "fastapi==0.111.0\nuvicorn[standard]==0.29.0\npydantic==2.7.1\n"
                "python-dotenv==1.0.1\npyyaml==6.0.1\n",
            )
        return [str(path)]

    def _write_docker(self, target: Path, profile: Dict, repo_name: str) -> list:
        code_name = profile.get("code_name", repo_name)
        content = textwrap.dedent(f"""\
            FROM python:3.11-slim
            LABEL maintainer="Trancendos" description="{code_name}"
            WORKDIR /app
            COPY requirements.txt .
            RUN pip install --no-cache-dir -r requirements.txt
            COPY . .
            ENV ENVIRONMENT=production
            EXPOSE 8000
            CMD ["uvicorn", "api_personality:app", "--host", "0.0.0.0", "--port", "8000"]
        """)
        path = safe_join(target, "Dockerfile")
        path.write_text(content)
        return [str(path)]

    # ─── Internal ────────────────────────────────────────────────────

    def _load_all_profiles(self) -> Dict[str, Dict]:
        profiles: Dict[str, Dict] = {}
        if not _PROFILES_DIR.exists():
            return profiles
        for f in _PROFILES_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                pid = data.get("id", f.stem)
                profiles[pid] = data
            except Exception as e:
                logger.warning("Failed to load personality profile %s: %s", f, e)
        return profiles
