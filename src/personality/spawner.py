# src/personality/spawner.py
# Generates a new Tranc3 repository scaffold for a specific personality instance.
# Each spawned repo is a self-contained Tranc3 derivative pre-configured with
# one dominant personality, its domain skills, and its system-prompt identity.
#
# Security: All user-supplied path components (output_dir, repo_name) are
# validated through Dimensionals.path_validation to prevent path traversal.

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from Dimensionals.path_validation import PathTraversalError, safe_join, sanitize_filename

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

# Emitted into generated scaffold only (uvicorn/Docker bind-all in containers).
_GEN_SCAFFOLD_BIND_HOST = "0.0.0.0"  # nosec B104


def _contained_in_roots(path: Path) -> bool:
    """Lexical containment against the allowed roots. No filesystem access."""
    return any(path.is_relative_to(root) for root in _ALLOWED_OUTPUT_ROOTS)


def _resolve_without_leaving(root: Path, candidate: Path, hop_limit: int = 40) -> Path:
    """Resolve *candidate* under *root*, refusing any symlink that points out.

    SEC-015, third pass. The walk restarts whenever it expands a link, and that
    restart is the whole correctness argument.

    The second pass expanded a link, checked the expanded *string* for
    containment, and then carried on with the next component — never walking the
    target's own components. So an intermediate symlink inside the target escaped
    unexamined. Reported by cubic, and reproduced before being accepted:

        <root>/mid -> /etc
        <root>/hop -> <root>/mid/passwd

        _resolve_output_base("<root>/hop")  ->  ACCEPTED
        that path really is                ->  /etc/passwd

    ``<root>/mid/passwd`` is lexically under the root, so the containment check
    passed on a string whose second component was a door out. Expanding a link
    now re-seeds the pending component list with the target's parts ahead of
    whatever is left, so every component of every target is itself walked and
    checked. ``mid`` is then examined in its own right, readlink returns
    ``/etc``, and the walk refuses.

    ``os.readlink`` reads a target without following it, and ``os.lstat`` does
    not follow a final symlink, so nothing outside a root is ever stat-ed. A path
    that does not exist yet has nothing left to follow, which is the ordinary
    case for a spawn target. ``hop_limit`` bounds total expansions, so a cycle
    raises instead of hanging.

    **What this does not do**, stated rather than implied: it resolves by name,
    so a sufficiently determined local attacker who can already write inside an
    allowed root could swap a component between this walk and the later
    ``safe_join``/``mkdir`` — a TOCTOU race cubic also raised. Closing that means
    holding directory descriptors with ``O_NOFOLLOW`` through every scaffold
    write, which is a redesign of how this module writes files rather than a
    change to how it validates. The precondition is write access inside
    ``Path.cwd()``, ``/tmp`` or ``$HOME`` — an attacker who has that already has
    better options against this process than racing a scaffold generator.
    Recorded in SEC-015 as a known limit.
    """
    resolved = root
    pending = list(candidate.relative_to(root).parts)
    hops = 0

    while pending:
        part = pending.pop(0)
        nxt = resolved / part
        try:
            info = os.lstat(nxt)
        except OSError:
            resolved = nxt  # does not exist — nothing to follow
            continue
        if not stat.S_ISLNK(info.st_mode):
            resolved = nxt
            continue

        hops += 1
        if hops > hop_limit:
            raise PathTraversalError(f"symlink chain too long at {part!r}")

        target = os.readlink(nxt)
        expanded = Path(os.path.normpath(os.path.join(str(resolved), target)))
        if not _contained_in_roots(expanded):
            raise PathTraversalError(
                f"symlink {part!r} points outside every allowed root",
            )

        # Restart from the root that contains the target, walking ITS components
        # too. Checking only the expanded string is what let an intermediate
        # symlink through.
        new_root = next(r for r in _ALLOWED_OUTPUT_ROOTS if expanded.is_relative_to(r))
        resolved = new_root
        pending = list(expanded.relative_to(new_root).parts) + pending

    return resolved


def _resolve_output_base(output_dir: str) -> Path:
    """Resolve and validate the output directory against allowed roots.

    Two containment checks, in this order, and the order is the point:

    1. **Lexical.** ``output_dir`` is joined onto the cwd and normalised with
       ``os.path.normpath`` — pure string work, no syscall — and checked against
       the allowed roots. Nothing outside a root is handed to the filesystem, so
       this function is not an existence oracle for paths the caller was never
       allowed to name.
    2. **Symlink-aware, without following anything out.**
       :func:`_resolve_without_leaving` walks the remaining components, reading
       each link's target with ``os.readlink`` rather than following it, and
       refuses the first one that leaves the roots. A symlink *inside* an allowed
       root pointing out of it is caught — the case the lexical check cannot see,
       and the case that made the original one-shot ``resolve()`` probe outside
       the roots before rejecting.

    Previously the order was inverted: ``Path(output_dir).resolve()`` ran on raw
    input before any check, and a second branch called ``parent.exists()`` on it
    too. Those two filesystem touches are what CodeQL flagged as py/path-injection
    at what were then lines 54 and 68 — not the write, which ``safe_join``
    already guarded.

    The second branch was also dead. It returned ``candidate`` when
    ``candidate.parent`` was under a root, but ``candidate`` is resolved, so it
    has no ``..`` left and sits strictly below its parent: any parent under a
    root puts the candidate under that same root, and the first loop would
    already have returned. The one path where ``candidate == candidate.parent``
    is ``/``, whose parent is ``/`` and is under no root. Measured across
    ``./spawned``, ``/tmp/x/y``, ``/etc/cron.d/evil``, ``/``, ``/etc``, ``..``,
    ``/tmp``, ``/root/.ssh`` and ``/usr/lib/python3/x``: the second loop returned
    for nothing the first loop had rejected.

    One deliberate narrowing: a symlink *into* an allowed root from outside it
    (``/opt/link -> /tmp/x``) was accepted before and is refused now. Step 1
    judges the name the caller supplied, and that name is outside every root.

    Args:
        output_dir: User-supplied output directory string.

    Returns:
        Validated base Path for output, with contained symlinks expanded.

    Raises:
        PathTraversalError: If the path escapes all allowed roots, lexically or
            through a symlink.
    """
    # Step 1 — lexical. No filesystem access on attacker-controlled input.
    lexical = Path(os.path.normpath(os.path.join(os.getcwd(), output_dir)))
    if not _contained_in_roots(lexical):
        raise PathTraversalError(
            f"Output directory {output_dir!r} is not under any allowed root. "
            f"Allowed roots: {[str(r) for r in _ALLOWED_OUTPUT_ROOTS]}",
        )

    # Step 2 — walk it without following any link out of the roots.
    containing_root = next(r for r in _ALLOWED_OUTPUT_ROOTS if lexical.is_relative_to(r))
    candidate = _resolve_without_leaving(containing_root, lexical)

    # Post-condition. The walk should make this unreachable; it is here because
    # "each step was checked" and "the result is contained" are different claims.
    if not _contained_in_roots(candidate):
        raise PathTraversalError(
            f"Output directory {output_dir!r} resolves outside every allowed root. "
            f"Allowed roots: {[str(r) for r in _ALLOWED_OUTPUT_ROOTS]}",
        )

    return candidate


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
                uvicorn.run("api_personality:app", host="{_GEN_SCAFFOLD_BIND_HOST}",
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
                "python-dotenv==1.0.1\npyyaml==6.0.1\n"
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
            CMD ["uvicorn", "api_personality:app", "--host", "{_GEN_SCAFFOLD_BIND_HOST}", "--port", "8000"]
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
