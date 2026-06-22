"""
The Lab — Port 8055
====================
AI code creation platform. Full TabbyML integration.

Adaptive chain: TabbyML (self-hosted) -> Ollama (code model) -> LiteLLM -> offline.

Entity: The Lab
Lead AI: The Dr. & Slime
Foundation: TabbyML
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PORT = int(os.getenv("PORT", "8055"))
WORKER_NAME = "the-lab"
VERSION = "2.0.0"

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

ALLOWED_LANGUAGES = {
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "java",
    "c",
    "cpp",
    "shell",
    "sql",
    "markdown",
    "json",
}


class CompleteRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    language: str = "python"
    max_tokens: int = Field(512, ge=1, le=4096)
    temperature: float = Field(0.1, ge=0.0, le=2.0)


class ChatRequest(BaseModel):
    messages: list[dict[str, str]]
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


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="The Lab", description="AI code creation platform — TabbyML bridge", version=VERSION
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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
    except Exception:
        pass
    return {
        "entity": "The Lab",
        "lead_ai": "The Dr. & Slime",
        "version": VERSION,
        "tabby_reachable": tabby_ok,
        "tabby_url": TABBY_URL,
        "uptime": time.time() - START_TIME,
    }


@app.post("/lab/complete")
async def lab_complete(req: CompleteRequest) -> dict[str, Any]:
    """Code completion via TabbyML -> Ollama -> LiteLLM -> offline."""
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


@app.post("/lab/chat")
async def lab_chat(req: ChatRequest) -> dict[str, Any]:
    """Code chat via TabbyML -> Ollama -> LiteLLM -> offline."""
    result = await _tabby_chat(req.messages, req.max_tokens)
    if result:
        return {"response": result, "source": "tabby"}

    result = await _ollama_generate(req.messages[-1].get("content", ""))
    if result:
        return {"response": result, "source": "ollama"}

    result = await _litellm_chat(req.messages, max_tokens=req.max_tokens)
    if result:
        return {"response": result, "source": "litellm"}

    return {"response": _offline_stub("chat", req.language, str(req.messages)), "source": "offline"}


@app.post("/lab/explain")
async def lab_explain(req: ExplainRequest) -> dict[str, Any]:
    """Explain code via AI chain."""
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


@app.post("/lab/review")
async def lab_review(req: ReviewRequest) -> dict[str, Any]:
    """Code review — security, quality, performance."""
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


@app.post("/lab/generate")
async def lab_generate(req: GenerateRequest) -> dict[str, Any]:
    """Generate code from description."""
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


@app.get("/lab/models")
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


@app.post("/lab/run")
async def lab_run(req: RunRequest) -> dict[str, Any]:
    """Execute code in a sandboxed subprocess (Python only for safety)."""
    if req.language not in ("python",):
        raise HTTPException(
            status_code=400, detail=f"Sandboxed execution not supported for {req.language}"
        )

    _validate_code(req.code)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(req.code)
        code_file = f.name

    try:
        # nosec S603 — intentional sandboxed execution; dangerous imports blocked above
        result = subprocess.run(  # noqa: S603
            [sys.executable, code_file],
            input=req.stdin,
            capture_output=True,
            text=True,
            timeout=req.timeout_seconds,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "language": req.language,
            "executed": True,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Execution timed out", "exit_code": -1, "executed": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Execution failed: {exc}") from exc
    finally:
        os.unlink(code_file)


@app.get("/workspaces")
async def workspaces() -> dict[str, Any]:
    return {"workspaces": [], "total": 0, "message": "Workspace management coming soon."}


@app.post("/execute")
async def execute_compat(req: RunRequest) -> dict[str, Any]:
    """Legacy /execute endpoint delegates to /lab/run."""
    return await lab_run(req)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
