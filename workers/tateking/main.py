"""
TateKing — Port 8053
====================
Video creation & editing platform. FFmpeg + Remotion pipeline integration.

Adaptive chain: local FFmpeg -> Remotion serverless -> offline stub.

Entity: TateKing
Lead AI: Benji Tate (+ Sam King)
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PORT = int(os.getenv("PORT", "8061"))
WORKER_NAME = "tateking"
VERSION = "2.0.0"

FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
REMOTION_SERVE_URL = os.getenv("REMOTION_SERVE_URL", "")
OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "/tmp/tateking-output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STARTED_AT = datetime.now(timezone.utc)
START_TIME = time.time()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_http_timeout = httpx.Timeout(300.0, connect=10.0)
_jobs: dict[str, dict[str, Any]] = {}

_SAFE_OUTPUT_NAME = re.compile(r"^[A-Za-z0-9_.-]+\.mp4$")
_ALLOWED_INPUT_SCHEMES = frozenset({"http", "https"})
_ALLOWED_INPUT_HOSTS = frozenset(
    h.strip() for h in os.getenv("TATEKING_ALLOWED_INPUT_HOSTS", "").split(",") if h.strip()
)


def _validate_input_url(url: str) -> None:
    """Reject URLs that could trigger SSRF via FFmpeg protocol handlers."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid input_url") from e
    if parsed.scheme not in _ALLOWED_INPUT_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail=f"input_url scheme '{parsed.scheme}' not allowed; use http or https",
        )
    if _ALLOWED_INPUT_HOSTS and parsed.hostname not in _ALLOWED_INPUT_HOSTS:
        raise HTTPException(
            status_code=400,
            detail="input_url host not in TATEKING_ALLOWED_INPUT_HOSTS allowlist",
        )


def _ffmpeg_available() -> bool:
    return shutil.which(FFMPEG_PATH) is not None


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class VideoCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    input_url: Optional[str] = None
    fps: int = Field(30, ge=1, le=120)
    width: int = Field(1280, ge=64, le=3840)
    height: int = Field(720, ge=64, le=2160)
    duration_seconds: float = Field(10.0, ge=0.1, le=3600.0)


class ComposeRequest(BaseModel):
    input_paths: list[str]  # job IDs; paths are resolved server-side from _jobs
    output_name: str = ""
    transition: str = "none"  # none, fade, dissolve


class SubtitleRequest(BaseModel):
    job_id: str
    srt_content: str


class ThumbnailRequest(BaseModel):
    job_id: str
    timestamp_seconds: float = 0.0


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------


def _run_ffmpeg(args: list[str], timeout: int = 120) -> tuple[bool, str]:
    """Run ffmpeg with the given pre-built argument list. Returns (success, stderr)."""
    ffmpeg_bin = shutil.which(FFMPEG_PATH)
    if not ffmpeg_bin:
        return False, f"FFmpeg not found: {FFMPEG_PATH}"
    # shell=False + list form: OS passes args directly with no shell interpretation.
    cmd = [ffmpeg_bin, "-y"] + args
    try:
        result = subprocess.run(  # nosec B603 # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return result.returncode == 0, result.stderr
    except subprocess.TimeoutExpired:
        return False, "FFmpeg timed out"
    except FileNotFoundError:
        return False, f"FFmpeg not found at {FFMPEG_PATH}"


async def _remotion_render(req: VideoCreateRequest, job_id: str) -> Optional[str]:
    """Submit render job to Remotion serverless endpoint."""
    if not REMOTION_SERVE_URL:
        return None
    payload = {
        "composition": req.title,
        "serveUrl": REMOTION_SERVE_URL,
        "inputProps": {
            "title": req.title,
            "description": req.description,
            "fps": req.fps,
            "durationInSeconds": req.duration_seconds,
        },
        "codec": "h264",
        "outputLocation": str(OUTPUT_DIR / f"{job_id}.mp4"),
    }
    try:
        async with httpx.AsyncClient(timeout=_http_timeout) as client:
            resp = await client.post(f"{REMOTION_SERVE_URL}/render", json=payload)
            resp.raise_for_status()
            return resp.json().get("renderId")
    except Exception as exc:
        logger.warning("Remotion render failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="TateKing", description="Video creation & editing platform", version=VERSION)
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
    return {
        "entity": "TateKing",
        "lead_ai": "Benji Tate",
        "lead_ais": ["Benji Tate", "Sam King"],
        "version": VERSION,
        "ffmpeg_available": _ffmpeg_available(),
        "ffmpeg_path": FFMPEG_PATH,
        "remotion_configured": bool(REMOTION_SERVE_URL),
        "uptime": time.time() - START_TIME,
    }


@app.post("/video/create")
async def create_video(req: VideoCreateRequest) -> dict[str, Any]:
    """Create a new video job using FFmpeg or Remotion."""
    job_id = str(uuid.uuid4())
    output_path = OUTPUT_DIR / f"{job_id}.mp4"

    # Primary: local FFmpeg — generate test card if no input
    if _ffmpeg_available():
        input_args: list[str]
        if req.input_url:
            _validate_input_url(req.input_url)
            input_args = ["-i", req.input_url]
        else:
            # Generate a colour test card — write title to a temp file so it
            # never touches the FFmpeg filter string (prevents filter injection).
            title_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            )
            title_file.write(req.title)
            title_file.close()
            input_args = [
                "-f",
                "lavfi",
                "-i",
                f"color=c=blue:s={req.width}x{req.height}:r={req.fps}:d={req.duration_seconds}",
                "-vf",
                f"drawtext=textfile={title_file.name}:fontsize=40:fontcolor=white"
                ":x=(w-text_w)/2:y=(h-text_h)/2",
            ]

        try:
            success, err = _run_ffmpeg(
                [
                    *input_args,
                    "-t",
                    str(req.duration_seconds),
                    "-r",
                    str(req.fps),
                    "-s",
                    f"{req.width}x{req.height}",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(output_path),
                ],
                timeout=int(req.duration_seconds * 10 + 60),
            )
        finally:
            # Clean up title temp file if it was created
            if "title_file" in locals():
                Path(title_file.name).unlink(missing_ok=True)
        if success:
            _jobs[job_id] = {
                "status": "completed",
                "source": "ffmpeg",
                "title": req.title,
                "output_path": str(output_path),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            logger.info("FFmpeg job %s completed: %s", job_id, output_path)
            return {"job_id": job_id, "status": "completed", "source": "ffmpeg"}
        else:
            logger.warning("FFmpeg failed: %s", err)

    # Fallback: Remotion
    render_id = await _remotion_render(req, job_id)
    if render_id:
        _jobs[job_id] = {
            "status": "queued",
            "source": "remotion",
            "render_id": render_id,
            "title": req.title,
            "output_path": str(output_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return {"job_id": job_id, "status": "queued", "source": "remotion"}

    # Offline stub
    _jobs[job_id] = {
        "status": "completed",
        "source": "offline",
        "title": req.title,
        "placeholder": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"job_id": job_id, "status": "completed", "source": "offline", "placeholder": True}


@app.post("/video/compose")
async def compose_video(req: ComposeRequest) -> dict[str, Any]:
    """Compose video from multiple input assets using FFmpeg."""
    job_id = str(uuid.uuid4())
    # Strict allowlist: alphanumeric, underscores, hyphens, dots — must end in .mp4.
    raw_name = req.output_name or f"{job_id}.mp4"
    if not _SAFE_OUTPUT_NAME.match(raw_name):
        raise HTTPException(status_code=400, detail="output_name must match [A-Za-z0-9_.-]+.mp4")
    output_name = raw_name
    output_path = OUTPUT_DIR / output_name

    if not _ffmpeg_available():
        raise HTTPException(status_code=503, detail="FFmpeg not available")

    if not req.input_paths:
        raise HTTPException(status_code=400, detail="No input paths provided")

    # Resolve job IDs to trusted output paths stored in _jobs (server-side only).
    # User-supplied strings are used only as dict keys — they never flow into Path().
    resolved_output_dir = OUTPUT_DIR.resolve()
    safe_paths: list[str] = []
    for job_id_input in req.input_paths:
        job = _jobs.get(job_id_input)
        if not job or not job.get("output_path"):
            raise HTTPException(status_code=400, detail=f"Job not found: {job_id_input}")
        stored_path = job["output_path"]  # trusted: written by this service, not the caller
        resolved = Path(stored_path).resolve()
        try:
            resolved.relative_to(resolved_output_dir)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="Job path not allowed",
            ) from exc
        if not resolved.exists():
            raise HTTPException(status_code=404, detail=f"File not found for job: {job_id_input}")
        safe_paths.append(str(resolved))

    # Build concat input
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in safe_paths:
            f.write(f"file '{p}'\n")
        concat_file = f.name

    success, err = _run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file,
            "-c",
            "copy",
            str(output_path),
        ]
    )
    os.unlink(concat_file)

    if success:
        _jobs[job_id] = {
            "status": "completed",
            "source": "ffmpeg",
            "output_path": str(output_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return {"job_id": job_id, "status": "completed", "output_path": str(output_path)}
    else:
        raise HTTPException(status_code=500, detail=f"FFmpeg compose failed: {err}")


@app.post("/video/thumbnail")
async def extract_thumbnail(req: ThumbnailRequest) -> dict[str, Any]:
    """Extract a thumbnail from a completed video job."""
    job = _jobs.get(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("placeholder"):
        return {"job_id": req.job_id, "thumbnail": None, "source": "offline"}

    output_path = job.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    # Re-validate stored path still resolves within OUTPUT_DIR
    resolved_output = Path(output_path).resolve()
    try:
        resolved_output.relative_to(OUTPUT_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Video path not allowed") from exc

    # Derive thumbnail path from trusted resolved_output (server-side), not from
    # user-supplied job_id, so no user-controlled data flows into Path operations.
    thumb_path = resolved_output.with_name(resolved_output.stem + "_thumb.jpg")
    success, err = _run_ffmpeg(
        [
            "-i",
            str(resolved_output),
            "-ss",
            str(req.timestamp_seconds),
            "-vframes",
            "1",
            str(thumb_path),
        ]
    )
    if success and thumb_path.exists():
        return {"job_id": req.job_id, "thumbnail_path": str(thumb_path), "source": "ffmpeg"}
    raise HTTPException(status_code=500, detail=f"Thumbnail extraction failed: {err}")


@app.get("/video/status/{job_id}")
async def get_video_status(job_id: str) -> dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Poll Remotion if queued
    if job["source"] == "remotion" and job["status"] == "queued" and REMOTION_SERVE_URL:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                resp = await client.get(f"{REMOTION_SERVE_URL}/render/{job['render_id']}")
                data = resp.json()
                if data.get("status") == "done":
                    job["status"] = "completed"
                elif data.get("status") == "error":
                    job["status"] = "failed"
        except Exception as exc:
            safe_job_id = job_id.replace("\n", "").replace("\r", "")[:64]
            logger.debug("Remotion status poll failed for %s: %s", safe_job_id, exc)

    return {"job_id": job_id, **job}


@app.get("/video/result/{job_id}")
async def get_video_result(job_id: str) -> FileResponse:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=202, detail=f"Job not ready: {job['status']}")

    output_path = job.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    resolved = Path(output_path).resolve()
    try:
        resolved.relative_to(OUTPUT_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Video path not allowed") from exc

    return FileResponse(str(resolved), media_type="video/mp4", filename=resolved.name)


@app.post("/video/subtitle")
async def add_subtitles(req: SubtitleRequest) -> dict[str, Any]:
    """Add SRT subtitles to a completed video via FFmpeg."""
    job = _jobs.get(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")
    if not _ffmpeg_available():
        raise HTTPException(status_code=503, detail="FFmpeg not available")

    output_path = job.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False) as f:
        f.write(req.srt_content)
        srt_file = f.name

    subtitled_path = OUTPUT_DIR / f"{req.job_id}_subtitled.mp4"
    escaped_srt = srt_file.replace("\\", "/").replace("'", "\\'").replace(":", "\\:")
    success, err = _run_ffmpeg(
        [
            "-i",
            output_path,
            "-vf",
            f"subtitles='{escaped_srt}'",
            "-c:a",
            "copy",
            str(subtitled_path),
        ]
    )
    os.unlink(srt_file)

    if success:
        subtitle_job_id = str(uuid.uuid4())
        _jobs[subtitle_job_id] = {
            "status": "completed",
            "source": "ffmpeg",
            "parent_job_id": req.job_id,
            "output_path": str(subtitled_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return {
            "job_id": subtitle_job_id,
            "status": "completed",
            "output_path": str(subtitled_path),
        }
    raise HTTPException(status_code=500, detail=f"Subtitle burn-in failed: {err}")


@app.get("/projects")
async def projects() -> dict[str, Any]:
    return {"projects": list(_jobs.values()), "total": len(_jobs)}


@app.post("/render")
async def render_compat(req: VideoCreateRequest) -> dict[str, Any]:
    """Legacy /render endpoint delegates to /video/create."""
    return await create_video(req)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)  # nosec B104 — containerised service
