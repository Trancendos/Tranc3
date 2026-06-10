"""
FFmpeg Video Processing Worker — TateKing service.
Port 8052.

Provides non-blocking video transcoding, thumbnail extraction,
and compression via asyncio subprocesses.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from Dimensional.path_validation import PathTraversalError, existing_file_path_str

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ffmpeg-worker")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="FFmpeg Worker",
    description="TateKing — Video processing worker (transcode, thumbnail, compress)",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Job:
    __slots__ = ("job_id", "status", "output_path", "error")

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.status: JobStatus = JobStatus.PENDING
        self.output_path: Optional[str] = None
        self.error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "output_path": self.output_path,
            "error": self.error,
        }


# Global job registry — key: job_id → Job
_jobs: Dict[str, Job] = {}

# Working directory for processed files
WORKDIR = Path(os.environ.get("FFMPEG_WORKDIR", "/app/workdir"))
WORKDIR.mkdir(parents=True, exist_ok=True)

# Allowed root for input media (paths must resolve under this directory)
MEDIA_ROOT = Path(os.environ.get("FFMPEG_MEDIA_ROOT", str(WORKDIR / "media")))
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ffmpeg_available() -> bool:
    """Return True if ffmpeg binary is found in PATH."""
    return shutil.which("ffmpeg") is not None


def _ffmpeg_version() -> str:
    """Return ffmpeg version string, or 'not found' if missing."""
    if not _ffmpeg_available():
        return "not found"
    try:
        result = os.popen("ffmpeg -version 2>&1").read()  # noqa: S605
        for line in result.splitlines():
            if line.startswith("ffmpeg version"):
                return line.split()[2]
    except Exception:
        pass
    return "unknown"


def _validated_input_path_str(input_path: str) -> str:
    """Return validated filesystem path string for input media under MEDIA_ROOT."""
    try:
        return existing_file_path_str(input_path, MEDIA_ROOT)
    except PathTraversalError as exc:
        raise HTTPException(status_code=400, detail="Invalid input path") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Input file not found") from exc


def _quality_to_crf(quality: str) -> str:
    """Map named quality to ffmpeg CRF value."""
    return {"high": "18", "medium": "23", "low": "30"}.get(quality, "23")


async def _run_ffmpeg(*args: str) -> tuple[int, str, str]:
    """Run ffmpeg with the given arguments asynchronously.

    Returns (returncode, stdout, stderr).
    """
    cmd = ["ffmpeg", "-y", *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class TranscodeRequest(BaseModel):
    input_path: str = Field(..., description="Absolute path to the input video file")
    output_format: str = Field(
        "mp4",
        pattern="^(mp4|webm|gif)$",
        description="Target container format: mp4, webm, or gif",
    )
    quality: str = Field(
        "medium",
        pattern="^(high|medium|low)$",
        description="Encoding quality: high, medium, or low",
    )


class ThumbnailRequest(BaseModel):
    input_path: str = Field(..., description="Absolute path to the input video file")
    timestamp_seconds: float = Field(5.0, ge=0, description="Timestamp for thumbnail extraction")


class CompressRequest(BaseModel):
    input_path: str = Field(..., description="Absolute path to the input video file")
    target_mb: float = Field(10.0, gt=0, description="Target output size in megabytes")


# ---------------------------------------------------------------------------
# Background task runner
# ---------------------------------------------------------------------------


async def _run_job(job_id: str, coro) -> None:  # noqa: ANN001
    """Execute a coroutine for a job, updating status on completion."""
    job = _jobs[job_id]
    job.status = JobStatus.PROCESSING
    try:
        output_path = await coro
        job.output_path = str(output_path)
        job.status = JobStatus.DONE
        log.info("job %s done → %s", job_id, output_path)
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.FAILED
        job.error = str(exc)
        log.error("job %s failed: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Core processing coroutines
# ---------------------------------------------------------------------------


async def _transcode(input_path: str, output_format: str, quality: str) -> Path:
    crf = _quality_to_crf(quality)
    out_name = f"{uuid.uuid4().hex}.{output_format}"
    out_path = WORKDIR / out_name

    if output_format == "gif":
        # Two-pass GIF: generate palette then render
        palette_path = WORKDIR / f"{uuid.uuid4().hex}_palette.png"
        rc, _, stderr = await _run_ffmpeg(
            "-i",
            input_path,  # codeql[py/path-injection] – validated under MEDIA_ROOT via existing_file_path_str
            "-vf",
            "fps=10,scale=320:-1:flags=lanczos,palettegen",
            str(palette_path),
        )
        if rc != 0:
            raise RuntimeError(f"Palette generation failed: {stderr[-500:]}")
        rc, _, stderr = await _run_ffmpeg(
            "-i",
            input_path,  # codeql[py/path-injection] – validated under MEDIA_ROOT via existing_file_path_str
            "-i",
            str(palette_path),
            "-lavfi",
            "fps=10,scale=320:-1:flags=lanczos[x];[x][1:v]paletteuse",
            str(out_path),
        )
        try:
            palette_path.unlink(missing_ok=True)
        except OSError:
            pass
    elif output_format == "webm":
        rc, _, stderr = await _run_ffmpeg(
            "-i",
            input_path,  # codeql[py/path-injection] – validated under MEDIA_ROOT via existing_file_path_str
            "-c:v",
            "libvpx-vp9",
            "-crf",
            crf,
            "-b:v",
            "0",
            "-c:a",
            "libopus",
            str(out_path),
        )
    else:
        # mp4
        rc, _, stderr = await _run_ffmpeg(
            "-i",
            input_path,  # codeql[py/path-injection] – validated under MEDIA_ROOT via existing_file_path_str
            "-c:v",
            "libx264",
            "-crf",
            crf,
            "-preset",
            "medium",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(out_path),
        )

    if rc != 0:
        raise RuntimeError(f"Transcode failed: {stderr[-500:]}")
    return out_path


async def _thumbnail(input_path: str, timestamp_seconds: float) -> Path:
    out_path = WORKDIR / f"{uuid.uuid4().hex}_thumb.jpg"
    rc, _, stderr = await _run_ffmpeg(
        "-ss",
        str(timestamp_seconds),
        "-i",
        input_path,  # codeql[py/path-injection] – validated under MEDIA_ROOT via existing_file_path_str
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out_path),
    )
    if rc != 0:
        raise RuntimeError(f"Thumbnail extraction failed: {stderr[-500:]}")
    return out_path


async def _compress(input_path: str, target_mb: float) -> Path:
    """Compress to approximate target size using two-pass encoding."""
    out_path = WORKDIR / f"{uuid.uuid4().hex}_compressed.mp4"

    # Probe duration to compute target bitrate
    probe_proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        input_path,  # codeql[py/path-injection] – validated under MEDIA_ROOT via existing_file_path_str
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    probe_out, _ = await probe_proc.communicate()
    try:
        duration = float(probe_out.decode().strip())
    except (ValueError, AttributeError):
        duration = 0.0

    if duration > 0:
        # target_mb → bits; subtract ~128 kbps audio allowance
        target_bits = target_mb * 8 * 1024 * 1024
        video_bitrate = max(int(target_bits / duration) - 128_000, 64_000)
        bitrate_str = f"{video_bitrate}"
    else:
        # Fallback: compress with CRF 28
        bitrate_str = None

    log_prefix = str(WORKDIR / uuid.uuid4().hex)

    if bitrate_str:
        # Pass 1
        rc, _, _ = await _run_ffmpeg(
            "-i",
            input_path,  # codeql[py/path-injection] – validated under MEDIA_ROOT via existing_file_path_str
            "-c:v",
            "libx264",
            "-b:v",
            bitrate_str,
            "-pass",
            "1",
            "-passlogfile",
            log_prefix,
            "-an",
            "-f",
            "null",
            "/dev/null",
        )
        if rc == 0:
            # Pass 2
            rc, _, stderr = await _run_ffmpeg(
                "-i",
                input_path,  # codeql[py/path-injection] – validated under MEDIA_ROOT via existing_file_path_str
                "-c:v",
                "libx264",
                "-b:v",
                bitrate_str,
                "-pass",
                "2",
                "-passlogfile",
                log_prefix,
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(out_path),
            )
        else:
            stderr = "two-pass encode pass 1 failed"
    else:
        rc, _, stderr = await _run_ffmpeg(
            "-i",
            input_path,  # codeql[py/path-injection] – validated under MEDIA_ROOT via existing_file_path_str
            "-c:v",
            "libx264",
            "-crf",
            "28",
            "-preset",
            "medium",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(out_path),
        )

    # Clean up two-pass log files if they exist
    for suffix in ("-0.log", "-0.log.mbtree"):
        try:
            Path(f"{log_prefix}{suffix}").unlink(missing_ok=True)
        except OSError:
            pass

    if rc != 0:
        raise RuntimeError(f"Compression failed: {stderr[-500:]}")
    return out_path


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    """Returns ffmpeg availability and version."""
    available = _ffmpeg_available()
    return {
        "service": "ffmpeg-worker",
        "available": available,
        "ffmpeg_version": _ffmpeg_version(),
    }


@app.post("/transcode", status_code=202)
async def transcode(req: TranscodeRequest) -> dict:
    """Queue a video transcoding job.

    Returns a job_id immediately; poll GET /jobs/{job_id} for status.
    """
    if not _ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg not found in PATH")

    input_path = _validated_input_path_str(req.input_path)
    job_id = str(uuid.uuid4())
    _jobs[job_id] = Job(job_id)
    asyncio.create_task(
        _run_job(job_id, _transcode(input_path, req.output_format, req.quality)),
    )
    return {"job_id": job_id, "status": JobStatus.PENDING}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    """Return status and output path for a job."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job.to_dict()


@app.post("/thumbnail", status_code=202)
async def thumbnail(req: ThumbnailRequest) -> dict:
    """Extract a single thumbnail frame from a video."""
    if not _ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg not found in PATH")

    input_path = _validated_input_path_str(req.input_path)
    job_id = str(uuid.uuid4())
    _jobs[job_id] = Job(job_id)
    asyncio.create_task(
        _run_job(job_id, _thumbnail(input_path, req.timestamp_seconds)),
    )
    return {"job_id": job_id, "status": JobStatus.PENDING}


@app.post("/compress", status_code=202)
async def compress(req: CompressRequest) -> dict:
    """Compress a video to approximately the target file size."""
    if not _ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg not found in PATH")

    input_path = _validated_input_path_str(req.input_path)
    job_id = str(uuid.uuid4())
    _jobs[job_id] = Job(job_id)
    asyncio.create_task(
        _run_job(job_id, _compress(input_path, req.target_mb)),
    )
    return {"job_id": job_id, "status": JobStatus.PENDING}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8052)
