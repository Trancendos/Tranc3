"""
The Lab — Port 8055
====================
AI code creation platform. Full TabbyML integration.

Adaptive chain: TabbyML (self-hosted) -> Ollama (code model) -> LiteLLM -> offline.

Entity: The Lab
Lead AI: The Dr. (Nikolai O'denhime)
Foundation: TabbyML
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from Dimensional.service_auth_fastapi import guard_internal_secret

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PORT = int(os.getenv("PORT", "8055"))
WORKER_NAME = "the-lab"
VERSION = "2.0.0"

_internal_secret_raw = os.getenv("INTERNAL_SECRET")
if (
    not _internal_secret_raw
    or not _internal_secret_raw.strip()
    or _internal_secret_raw.strip() == "dev-secret"
):
    raise RuntimeError(
        "INTERNAL_SECRET is not set (or still the default). "
        "This worker cannot start without a strong unique internal secret. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
INTERNAL_SECRET: str = _internal_secret_raw.strip()

TABBY_URL = os.getenv("TABBY_URL", "http://localhost:8080").rstrip("/")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
LITELLM_URL = os.getenv("LITELLM_URL", "http://localhost:4000").rstrip("/")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")

STARTED_AT = datetime.now(timezone.utc)
START_TIME = time.time()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_http_timeout = httpx.Timeout(60.0, connect=5.0)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

# The canonical list lives in src/lab/languages.py, which also records each
# language's toolchain and the verification tier it unlocks. This worker's
# image cannot import that module — its build context holds main.py and the
# shared core, nothing else — so the ids are mirrored here and
# scripts/check_lab_languages.py fails CI if the two ever disagree.
#
# This set previously held twelve entries and was referenced exactly once, at
# its own definition. Nothing validated against it and nothing exposed it, so
# a request naming any language at all was interpolated straight into a
# prompt. It was a capability claim with no capability behind it.
ALLOWED_LANGUAGES = {
    "c",
    "cpp",
    "csharp",
    "css",
    "dockerfile",
    "elixir",
    "go",
    "haskell",
    "html",
    "java",
    "javascript",
    "json",
    "julia",
    "kotlin",
    "lua",
    "markdown",
    "perl",
    "php",
    "python",
    "r",
    "ruby",
    "rust",
    "scala",
    "shell",
    "sql",
    "swift",
    "terraform",
    "typescript",
    "yaml",
}

#: Spellings a caller is likely to use for a language the registry knows.
#: Refusing "golang" or "c++" would push callers back to the free-form string
#: this validation replaced.
LANGUAGE_ALIASES = {
    "bash": "shell",
    "c#": "csharp",
    "c++": "cpp",
    "cplusplus": "cpp",
    "cs": "csharp",
    "docker": "dockerfile",
    "ex": "elixir",
    "golang": "go",
    "hcl": "terraform",
    "hs": "haskell",
    "jl": "julia",
    "js": "javascript",
    "kt": "kotlin",
    "md": "markdown",
    "node": "javascript",
    "pl": "perl",
    "py": "python",
    "python3": "python",
    "rb": "ruby",
    "rs": "rust",
    "sh": "shell",
    "tf": "terraform",
    "ts": "typescript",
    "yml": "yaml",
    "zsh": "shell",
}


def _validate_language(language: str) -> str:
    """Resolve a language name, or refuse it.

    Refusing is the point. An unrecognised language used to be interpolated
    into the prompt unchanged, so The Lab would confidently answer for a
    language nobody had decided it supports, and the response carried no sign
    that it had happened.
    """
    canonical = LANGUAGE_ALIASES.get(language.strip().lower(), language.strip().lower())
    if canonical not in ALLOWED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported language {language!r}. The Lab supports "
                f"{len(ALLOWED_LANGUAGES)}: {', '.join(sorted(ALLOWED_LANGUAGES))}"
            ),
        )
    return canonical


class CompleteRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    language: str = "python"
    max_tokens: int = Field(512, ge=1, le=4096)
    temperature: float = Field(0.1, ge=0.0, le=2.0)


class ChatRequest(BaseModel):
    messages: list[dict[str, str]] = Field(..., min_length=1)
    language: str = "python"
    max_tokens: int = Field(1024, ge=1, le=4096)


class ExplainRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=8000)
    language: str = "python"


class ReviewRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=8000)
    language: str = "python"
    focus: list[str] = Field(default_factory=lambda: ["security", "quality", "performance"])


class GenerateRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=2000)
    language: str = "python"
    style: str = "clean"  # clean, verbose, minimal


class RunRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=10000)
    language: str = "python"
    timeout_seconds: int = Field(10, ge=1, le=30)
    stdin: str = ""


# ---------------------------------------------------------------------------
# Fallback helpers
# ---------------------------------------------------------------------------


async def _tabby_complete(prompt: str, language: str, max_tokens: int) -> Optional[str]:
    payload = {
        "prompt": prompt,
        "language": language,
        "segments": None,
    }
    try:
        async with httpx.AsyncClient(timeout=_http_timeout) as client:
            resp = await client.post(f"{TABBY_URL}/v1/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            return choices[0]["text"] if choices else None
    except Exception as exc:
        logger.debug("TabbyML completion failed: %s", exc)
        return None


async def _tabby_chat(messages: list[dict[str, str]], max_tokens: int) -> Optional[str]:
    payload = {"messages": messages, "max_tokens": max_tokens}
    try:
        async with httpx.AsyncClient(timeout=_http_timeout) as client:
            resp = await client.post(f"{TABBY_URL}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.debug("TabbyML chat failed: %s", exc)
        return None


async def _ollama_generate(prompt: str, model: str = "codellama") -> Optional[str]:
    payload = {"model": model, "prompt": prompt, "stream": False}
    try:
        async with httpx.AsyncClient(timeout=_http_timeout) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json().get("response")
    except Exception as exc:
        logger.debug("Ollama generate failed: %s", exc)
        return None


async def _litellm_chat(messages: list[dict[str, str]], max_tokens: int = 1024) -> Optional[str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if LITELLM_MASTER_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_MASTER_KEY}"
    payload = {"model": "ollama/codellama", "messages": messages, "max_tokens": max_tokens}
    try:
        async with httpx.AsyncClient(timeout=_http_timeout) as client:
            resp = await client.post(
                f"{LITELLM_URL}/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.debug("LiteLLM chat failed: %s", exc)
        return None


def _offline_stub(task: str, language: str, code_or_desc: str) -> str:
    return f"# [{task}] — Offline stub\n# Language: {language}\n# Input: {code_or_desc[:80]}...\n# All AI backends unavailable. Please check TabbyML/Ollama/LiteLLM.\n"


def _require_internal_auth(x_internal_secret: str = Header(default="")) -> None:
    # Delegated to Dimensional.service_auth, which this worker now reaches
    # through the `sharedcore` named build context. It compares with
    # compare_digest and refuses when the secret is unset.
    guard_internal_secret(
        x_internal_secret, INTERNAL_SECRET, mismatch_status=403, detail="Forbidden"
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="The Lab", description="AI code creation platform — TabbyML bridge", version=VERSION
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
        ).split(",")
        if o.strip() and o.strip() != "*"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "service": WORKER_NAME,
        "status": "ok",
        "version": VERSION,
        "uptime": time.time() - START_TIME,
    }


@app.get("/status")
async def status() -> dict[str, Any]:
    tabby_ok = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
            r = await client.get(f"{TABBY_URL}/v1/health")
            tabby_ok = r.status_code == 200
    except Exception as exc:
        logger.debug("Tabby status check failed: %s", exc)
    return {
        "entity": "The Lab",
        "lead_ai": "The Dr. (Nikolai O'denhime)",
        "version": VERSION,
        "tabby_reachable": tabby_ok,
        "tabby_url": TABBY_URL,
        "uptime": time.time() - START_TIME,
    }


@app.post("/lab/complete", dependencies=[Depends(_require_internal_auth)])
async def lab_complete(req: CompleteRequest) -> dict[str, Any]:
    """Code completion via TabbyML -> Ollama -> LiteLLM -> offline."""
    req.language = _validate_language(req.language)
    result = await _tabby_complete(req.prompt, req.language, req.max_tokens)
    if result:
        return {"completion": result, "source": "tabby", "language": req.language}

    # Ollama fallback
    result = await _ollama_generate(f"Complete this {req.language} code:\n{req.prompt}")
    if result:
        return {"completion": result, "source": "ollama", "language": req.language}

    # LiteLLM fallback
    messages = [
        {"role": "system", "content": f"You are a {req.language} code assistant."},
        {"role": "user", "content": f"Complete this code:\n{req.prompt}"},
    ]
    result = await _litellm_chat(messages, max_tokens=req.max_tokens)
    if result:
        return {"completion": result, "source": "litellm", "language": req.language}

    return {"completion": _offline_stub("complete", req.language, req.prompt), "source": "offline"}


def _with_language(messages: list[dict[str, str]], language: str) -> list[dict[str, str]]:
    """Put the validated language in front of the conversation.

    A caller's own system message wins — it is more specific than anything
    this worker can say — so one is only prepended when there is none.
    """
    if any(m.get("role") == "system" for m in messages):
        return messages
    return [{"role": "system", "content": f"You are a {language} code assistant."}, *messages]


@app.post("/lab/chat", dependencies=[Depends(_require_internal_auth)])
async def lab_chat(req: ChatRequest) -> dict[str, Any]:
    """Code chat via TabbyML -> Ollama -> LiteLLM -> offline.

    The language is validated and then actually used. It was validated and
    dropped: a request naming Rust was refused if Rust were unsupported, and
    otherwise answered by a model that had never been told it was Rust, in a
    response body that did not say what it had answered in. Every other
    handler here puts the language in the prompt; this one is no different.
    """
    req.language = _validate_language(req.language)
    messages = _with_language(req.messages, req.language)

    result = await _tabby_chat(messages, req.max_tokens)
    if result:
        return {"response": result, "source": "tabby", "language": req.language}

    last = req.messages[-1].get("content", "") if req.messages else ""
    result = await _ollama_generate(f"About this {req.language} code:\n{last}")
    if result:
        return {"response": result, "source": "ollama", "language": req.language}

    result = await _litellm_chat(messages, max_tokens=req.max_tokens)
    if result:
        return {"response": result, "source": "litellm", "language": req.language}

    return {
        "response": _offline_stub("chat", req.language, str(req.messages)),
        "source": "offline",
        "language": req.language,
    }


@app.post("/lab/explain", dependencies=[Depends(_require_internal_auth)])
async def lab_explain(req: ExplainRequest) -> dict[str, Any]:
    """Explain code via AI chain."""
    req.language = _validate_language(req.language)
    prompt = f"Explain this {req.language} code clearly and concisely:\n\n```{req.language}\n{req.code}\n```"
    messages = [
        {"role": "system", "content": "You are an expert code reviewer."},
        {"role": "user", "content": prompt},
    ]
    result = await _tabby_chat(messages, max_tokens=1024)
    if result:
        return {"explanation": result, "source": "tabby"}

    result = await _ollama_generate(prompt)
    if result:
        return {"explanation": result, "source": "ollama"}

    result = await _litellm_chat(messages)
    if result:
        return {"explanation": result, "source": "litellm"}

    return {"explanation": _offline_stub("explain", req.language, req.code), "source": "offline"}


@app.post("/lab/review", dependencies=[Depends(_require_internal_auth)])
async def lab_review(req: ReviewRequest) -> dict[str, Any]:
    """Code review — security, quality, performance."""
    req.language = _validate_language(req.language)
    focus_str = ", ".join(req.focus)
    prompt = (
        f"Review this {req.language} code focusing on: {focus_str}.\n"
        f"Format your response as: ISSUES, SUGGESTIONS, VERDICT.\n\n"
        f"```{req.language}\n{req.code}\n```"
    )
    messages = [
        {
            "role": "system",
            "content": "You are a senior code reviewer specialising in security and quality.",
        },
        {"role": "user", "content": prompt},
    ]
    result = await _tabby_chat(messages, max_tokens=2048)
    if result:
        return {"review": result, "focus": req.focus, "source": "tabby"}

    result = await _ollama_generate(prompt)
    if result:
        return {"review": result, "focus": req.focus, "source": "ollama"}

    result = await _litellm_chat(messages, max_tokens=2048)
    if result:
        return {"review": result, "focus": req.focus, "source": "litellm"}

    return {
        "review": _offline_stub("review", req.language, req.code),
        "focus": req.focus,
        "source": "offline",
    }


@app.post("/lab/generate", dependencies=[Depends(_require_internal_auth)])
async def lab_generate(req: GenerateRequest) -> dict[str, Any]:
    """Generate code from description."""
    req.language = _validate_language(req.language)
    prompt = (
        f"Write {req.style} {req.language} code that does the following:\n{req.description}\n\n"
        f"Return only the code, no explanation."
    )
    messages = [
        {"role": "system", "content": f"You are an expert {req.language} developer."},
        {"role": "user", "content": prompt},
    ]
    result = await _tabby_chat(messages, max_tokens=2048)
    if result:
        return {"code": result, "language": req.language, "source": "tabby"}

    result = await _ollama_generate(prompt)
    if result:
        return {"code": result, "language": req.language, "source": "ollama"}

    result = await _litellm_chat(messages, max_tokens=2048)
    if result:
        return {"code": result, "language": req.language, "source": "litellm"}

    return {
        "code": _offline_stub("generate", req.language, req.description),
        "language": req.language,
        "source": "offline",
    }


@app.get("/lab/languages")
async def lab_languages() -> dict[str, Any]:
    """The languages The Lab accepts, and the spellings it resolves.

    Unauthenticated on purpose: this is the same information a 400 already
    returns, and making a caller guess at a set they will be refused for
    getting wrong is not a security boundary.
    """
    return {
        "languages": sorted(ALLOWED_LANGUAGES),
        "total": len(ALLOWED_LANGUAGES),
        "aliases": dict(sorted(LANGUAGE_ALIASES.items())),
        "verification": (
            "Acceptance is not verification. src/lab/languages.py records the "
            "toolchain each language needs and scripts/lab_capability_report.py "
            "reports which of it this image actually contains."
        ),
    }


@app.get("/lab/models", dependencies=[Depends(_require_internal_auth)])
async def lab_models() -> dict[str, Any]:
    """List TabbyML models."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            resp = await client.get(f"{TABBY_URL}/v1/models")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("TabbyML models unavailable: %s", exc)
        return {
            "models": [
                {"id": "TabbyML/StarCoder-1B", "provider": "tabby"},
                {"id": "TabbyML/CodeLlama-7B", "provider": "tabby"},
                {"id": "codellama", "provider": "ollama"},
            ],
            "source": "offline",
        }


_BLOCKED_IMPORTS = frozenset(
    [
        "os",
        "subprocess",
        "shutil",
        "socket",
        "ctypes",
        "importlib",
        "multiprocessing",
        "signal",
        "pty",
        "resource",
        "fcntl",
        "mmap",
        "pwd",
        "grp",
        "termios",
    ]
)


def _validate_code(code: str) -> None:
    """Reject code that imports high-risk stdlib modules."""
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"Syntax error: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _BLOCKED_IMPORTS:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Import of '{top}' is not allowed in sandboxed execution.",
                    )
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in _BLOCKED_IMPORTS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Import from '{top}' is not allowed in sandboxed execution.",
                )


@app.post("/lab/run", dependencies=[Depends(_require_internal_auth)])
async def lab_run(req: RunRequest) -> dict[str, Any]:
    """Code execution endpoint — disabled pending proper container sandboxing.

    AST import blocking is insufficient: __import__('os'), builtins, and
    importlib bypass it trivially, allowing arbitrary RCE. This endpoint will
    be re-enabled once the service runs inside a gVisor/nsjail sandbox.
    """
    raise HTTPException(
        status_code=501,
        detail="Code execution is disabled pending container-level sandboxing. Use a dedicated sandbox service.",
    )


@app.get("/workspaces", dependencies=[Depends(_require_internal_auth)])
async def workspaces() -> dict[str, Any]:
    return {"workspaces": [], "total": 0, "message": "Workspace management coming soon."}


@app.post("/execute", dependencies=[Depends(_require_internal_auth)])
async def execute_compat(req: RunRequest) -> dict[str, Any]:
    """Legacy /execute endpoint delegates to /lab/run."""
    return await lab_run(req)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)  # nosec B104 — containerised service
