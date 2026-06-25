"""
Turing's Hub — 3D AI Model Builder Service (Port 8085)
========================================================
The pod/capsule that assembles all platform threads into a complete,
living, functioning 3D AI entity. Draws from:
  - Personality profiles (soul layer)
  - Kokoro TTS / Piper TTS (voice layer)
  - Rhubarb Lip Sync (viseme/lip sync)
  - VRM avatar assets (body layer)
  - Mixamo GLB animations (motion layer)
  - Ollama / AI Gateway (brain layer)

Each AI entity (Imfy, Dorris Fontaine, The Dr., George Porter, etc.)
is forged here from its component parts into a unified, interactive being.

Zero-cost stack:
  - three-vrm + Three.js → VRM rendering in browser (MIT)
  - TalkingHead class (met4citizen) → lip sync + emotion + gesture (MIT)
  - Kokoro TTS (hexgrad/Kokoro-82M) → voice synthesis (Apache 2.0)
  - Rhubarb Lip Sync → phoneme/viseme timeline (MIT)
  - VRoid Studio → .vrm character files (free)
  - Mixamo → animation library (royalty-free)

Endpoints:
  GET  /health
  GET  /entities                     — list all entity manifests
  GET  /entities/{entity_id}         — full entity spec (avatar + voice + personality)
  POST /entities/{entity_id}/speak   — TTS + lip sync for a text utterance
  GET  /entities/{entity_id}/avatar  — VRM asset URL + animation manifest
  WS   /entities/{entity_id}/stream  — real-time streaming (LLM → TTS → visemes)
  GET  /assets/vrm/{filename}        — serve VRM avatar files
  GET  /assets/animations/{filename} — serve GLB animation files
  POST /forge                        — assemble a new entity from personality JSON
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logger = logging.getLogger("turings-hub")

SERVICE_NAME = "turings-hub"
PORT = 8085

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BASE = Path(__file__).parent
ASSETS_DIR = _BASE / "assets"
VRM_DIR = ASSETS_DIR / "vrm"
ANIM_DIR = ASSETS_DIR / "animations"
PORTRAIT_DIR = ASSETS_DIR / "portraits"
PERSONALITY_DIR = Path(os.environ.get("PERSONALITY_DIR", "/app/src/personality/profiles"))

# External tool paths (set via env or auto-detected)
# shutil.which() resolves to an absolute path of a real executable, or None.
# Using a resolved absolute path satisfies subprocess security scanners and
# prevents tainted-env-arg injection (no shell=True is used anywhere here).
RHUBARB_BIN: Optional[str] = shutil.which(os.environ.get("RHUBARB_BIN", "rhubarb"))
KOKORO_URL = os.environ.get("KOKORO_URL", "http://localhost:8080")
PIPER_BIN = os.environ.get("PIPER_BIN", "piper")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# ---------------------------------------------------------------------------
# Entity manifest — voice + avatar config per entity
# This extends the personality JSON profiles with 3D embodiment data.
# VRM files must be placed in workers/turings-hub-service/assets/vrm/
# Animation GLBs must be placed in workers/turings-hub-service/assets/animations/
# ---------------------------------------------------------------------------

ENTITY_EMBODIMENT: Dict[str, Dict[str, Any]] = {
    "the-spark": {
        "voice": {"engine": "kokoro", "voice_id": "af_sky", "pitch": 1.1, "speed": 1.0},
        "avatar": {"vrm": "imfy.vrm", "portrait": "imfy.png"},
        "animations": {
            "idle": "idle_tech.glb",
            "talk": "talk_gesture.glb",
            "think": "thinking.glb",
        },
        "lead_ai": "Imfy",
    },
    "the-observatory": {
        "voice": {"engine": "kokoro", "voice_id": "am_echo", "pitch": 0.95, "speed": 0.9},
        "avatar": {"vrm": "norman-hawkins.vrm", "portrait": "norman-hawkins.png"},
        "animations": {"idle": "idle_professional.glb", "talk": "talk_gesture.glb"},
        "lead_ai": "Norman Hawkins",
    },
    "royal-bank-of-arcadia": {
        "voice": {"engine": "kokoro", "voice_id": "af_heart", "pitch": 1.05, "speed": 0.95},
        "avatar": {"vrm": "dorris-fontaine.vrm", "portrait": "dorris-fontaine.png"},
        "animations": {"idle": "idle_finance.glb", "talk": "talk_presentation.glb"},
        "lead_ai": "Dorris Fontaine",
    },
    "arcadian-exchange": {
        "voice": {
            "engine": "kokoro",
            "family": [
                {"member": "Clarence Porter", "voice_id": "am_michael", "role": "father"},
                {"member": "Ann Porter", "voice_id": "af_alloy", "role": "mother"},
                {"member": "George Porter", "voice_id": "am_fenrir", "role": "child"},
                {"member": "Edward Porter", "voice_id": "am_adam", "role": "child"},
                {"member": "James Porter", "voice_id": "af_nova", "role": "child"},
            ],
            "default": "clarence-porter",
        },
        "avatar": {"vrm": "porter-family.vrm", "portrait": "porter-family.png"},
        "animations": {"idle": "idle_trade.glb", "talk": "talk_gesture.glb"},
        "lead_ai": "Clarence Porter",
    },
    "luminous": {
        "voice": {"engine": "kokoro", "voice_id": "am_onyx", "pitch": 0.9, "speed": 0.85},
        "avatar": {"vrm": "cornelius-macintyre.vrm", "portrait": "cornelius-macintyre.png"},
        "animations": {"idle": "idle_deep.glb", "talk": "talk_thoughtful.glb"},
        "lead_ai": "Cornelius MacIntyre",
    },
    "infinity": {
        "voice": {
            "engine": "kokoro",
            "dual": [
                {"member": "The Guardian (Marcus Magnolia)", "voice_id": "am_echo", "pitch": 0.85},
                {"member": "The Orb of Orisis", "voice_id": "af_shimmer", "pitch": 1.2},
            ],
            "default": "the-guardian",
        },
        "avatar": {"vrm": "the-guardian.vrm", "portrait": "the-guardian.png"},
        "animations": {"idle": "idle_guardian.glb", "talk": "talk_authoritative.glb"},
        "lead_ai": "The Guardian (Marcus Magnolia)",
    },
    "the-lab": {
        "voice": {
            "engine": "kokoro",
            "dual": [
                {"member": "The Dr. (Nikolai O'denhime)", "voice_id": "am_fable", "pitch": 0.95},
                {"member": "Slime", "voice_id": "af_nova", "pitch": 1.3, "speed": 1.15},
            ],
            "default": "the-dr",
        },
        "avatar": {"vrm": "the-dr.vrm", "portrait": "the-dr.png"},
        "animations": {"idle": "idle_lab.glb", "talk": "talk_excited.glb"},
        "lead_ai": "The Dr. (Nikolai O'denhime)",
    },
    "tateking": {
        "voice": {
            "engine": "kokoro",
            "dual": [
                {"member": "Benji Tate", "voice_id": "am_michael", "pitch": 1.0},
                {"member": "Sam King", "voice_id": "am_adam", "pitch": 0.9},
            ],
            "default": "benji-tate",
        },
        "avatar": {"vrm": "benji-tate.vrm", "portrait": "benji-tate.png"},
        "animations": {"idle": "idle_creative.glb", "talk": "talk_gesture.glb"},
        "lead_ai": "Benji Tate",
    },
    "docutari": {
        "voice": {"engine": "kokoro", "voice_id": "af_sky", "pitch": 1.05, "speed": 1.0},
        "avatar": {"vrm": "fiddsy.vrm", "portrait": "fiddsy.png"},
        "animations": {"idle": "idle_librarian.glb", "talk": "talk_gesture.glb"},
        "lead_ai": "Fiddsy",
    },
    "the-basement": {
        "voice": {"engine": "kokoro", "voice_id": "am_echo", "pitch": 0.8, "speed": 0.88},
        "avatar": {"vrm": "gary-glowman.vrm", "portrait": "gary-glowman.png"},
        "animations": {"idle": "idle_archive.glb", "talk": "talk_gesture.glb"},
        "lead_ai": "Gary Glowman",
    },
    "section-7": {
        "voice": {"engine": "kokoro", "voice_id": "am_fable", "pitch": 0.92, "speed": 0.92},
        "avatar": {"vrm": "the-dutchy.vrm", "portrait": "the-dutchy.png"},
        "animations": {"idle": "idle_analyst.glb", "talk": "talk_thoughtful.glb"},
        "lead_ai": "The Dutchy",
    },
}

# Default fallback embodiment for entities not yet configured
_DEFAULT_EMBODIMENT: Dict[str, Any] = {
    "voice": {"engine": "piper", "voice_id": "en_US-lessac-medium", "pitch": 1.0, "speed": 1.0},
    "avatar": {"vrm": None, "portrait": None},
    "animations": {"idle": "idle_default.glb", "talk": "talk_gesture.glb"},
    "lead_ai": "Unknown",
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
    emotion: str = "neutral"  # neutral | happy | sad | angry | surprised | thinking
    member: Optional[str] = None  # for multi-AI entities (Porter family etc.)
    include_visemes: bool = True  # include Rhubarb lip-sync timeline
    stream: bool = False


class ForgeRequest(BaseModel):
    entity_id: str
    lead_ai: str
    voice_engine: str = "kokoro"
    voice_id: str = "af_sky"
    vrm_filename: Optional[str] = None
    portrait_filename: Optional[str] = None
    personality_overrides: Dict[str, Any] = Field(default_factory=dict)


class SpeakResponse(BaseModel):
    entity_id: str
    lead_ai: str
    text: str
    emotion: str
    audio_url: Optional[str] = None  # served from /audio/{session_id}.wav
    visemes: Optional[List[Dict[str, Any]]] = None  # [{time_ms, shape, weight}]
    duration_ms: Optional[float] = None
    tts_engine: str = "unavailable"


# ---------------------------------------------------------------------------
# TTS helpers
# ---------------------------------------------------------------------------


async def _synthesise_kokoro(text: str, voice_id: str, speed: float = 1.0) -> Optional[bytes]:
    """Call Kokoro TTS (OpenAI-compatible endpoint)."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{KOKORO_URL}/v1/audio/speech",
                json={"model": "kokoro", "input": text, "voice": voice_id, "speed": speed},
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                return resp.content
    except Exception as exc:
        logger.warning("Kokoro TTS unavailable: %s", exc)
    return None


async def _synthesise_piper(text: str, voice_id: str) -> Optional[bytes]:
    """Call Piper TTS via subprocess."""
    try:
        proc = await asyncio.create_subprocess_exec(
            PIPER_BIN,
            "--model",
            voice_id,
            "--output_raw",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(text.encode()), timeout=15.0)
        return stdout if stdout else None
    except Exception as exc:
        logger.warning("Piper TTS unavailable: %s", exc)
    return None


async def _synthesise(
    entity_id: str, text: str, member: Optional[str] = None
) -> tuple[bytes | None, str]:
    """Route TTS to the correct engine/voice for this entity."""
    embodiment = ENTITY_EMBODIMENT.get(entity_id, _DEFAULT_EMBODIMENT)
    voice_cfg = embodiment.get("voice", {})
    engine = voice_cfg.get("engine", "piper")

    # Resolve voice_id — handle multi-AI (family / dual) entities
    voice_id = voice_cfg.get("voice_id")
    speed = voice_cfg.get("speed", 1.0)
    if not voice_id:
        family = voice_cfg.get("family") or voice_cfg.get("dual", [])
        default_key = voice_cfg.get("default", "")
        chosen = next(
            (
                m
                for m in family
                if m.get("member", "").lower().replace(" ", "-") == (member or default_key)
            ),
            family[0] if family else None,
        )
        if chosen:
            voice_id = chosen.get("voice_id", "af_sky")
            speed = chosen.get("speed", speed)
        else:
            voice_id = "af_sky"

    if engine == "kokoro":
        audio = await _synthesise_kokoro(text, voice_id, speed)
        if audio:
            return audio, "kokoro"

    # Fallback to Piper
    piper_voice = voice_cfg.get("piper_fallback", "en_US-lessac-medium")
    audio = await _synthesise_piper(text, piper_voice)
    return audio, "piper" if audio else "unavailable"


# ---------------------------------------------------------------------------
# Rhubarb lip-sync helper
# ---------------------------------------------------------------------------


def _rhubarb_visemes(wav_path: str) -> Optional[List[Dict[str, Any]]]:
    """
    Run Rhubarb Lip Sync on a WAV file.
    Returns a list of {time_ms, shape, weight} dicts for each phoneme frame.
    Rhubarb must be installed and on PATH (or RHUBARB_BIN env set).
    """
    if RHUBARB_BIN is None:
        logger.info(
            "Rhubarb not installed — lip sync unavailable"
            " (install from github.com/DanielSWolf/rhubarb-lip-sync)"
        )
        return None
    try:
        # Resolve wav_path to absolute and verify existence before subprocess.
        # RHUBARB_BIN is already an absolute path resolved via shutil.which().
        resolved = Path(wav_path).resolve()
        if not resolved.is_file():
            logger.warning("Rhubarb: invalid or missing wav_path: %s", wav_path)
            return None
        wav_path = str(resolved)
        result = subprocess.run(
            [RHUBARB_BIN, "--recognizer", "phonetic", "--exportFormat", "json", wav_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("Rhubarb error: %s", result.stderr[:200])
            return None
        data = json.loads(result.stdout)
        # Rhubarb JSON: {"metadata": {...}, "mouthCues": [{"start": 0.0, "end": 0.2, "value": "A"}, ...]}
        return [
            {
                "time_ms": int(cue["start"] * 1000),
                "end_ms": int(cue["end"] * 1000),
                "shape": cue["value"],  # A-H Preston Blair shapes
                "weight": 1.0,
            }
            for cue in data.get("mouthCues", [])
        ]
    except Exception as exc:
        logger.warning("Rhubarb failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# In-memory audio cache (session-scoped, TTL not implemented — use redis in prod)
# ---------------------------------------------------------------------------

_audio_cache: Dict[str, bytes] = {}


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # OpenTelemetry instrumentation
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from src.observability.otel import init_otel

        init_otel(service_name="tranc3.turings-hub-service")
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass  # OTel is optional — never block startup
    for d in (VRM_DIR, ANIM_DIR, PORTRAIT_DIR):
        d.mkdir(parents=True, exist_ok=True)
    logger.info("Turing's Hub 3D AI Model Builder started on port %d", PORT)
    logger.info("VRM assets: %s", VRM_DIR)
    logger.info("Animation assets: %s", ANIM_DIR)
    logger.info(
        "TTS: Kokoro @ %s | Rhubarb: %s | Ollama @ %s",
        KOKORO_URL,
        RHUBARB_BIN,
        OLLAMA_URL,
    )
    yield


app = FastAPI(
    title="Turing's Hub — 3D AI Model Builder",
    description=(
        "The pod/capsule that assembles all platform threads into a complete, "
        "living, functioning 3D AI entity. Voice + lip sync + VRM body + personality brain."
    ),
    version="1.0.0",
    lifespan=_lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Serve static VRM/GLB/portrait assets
app.mount("/assets/vrm", StaticFiles(directory=str(VRM_DIR)), name="vrm_assets")
app.mount("/assets/animations", StaticFiles(directory=str(ANIM_DIR)), name="anim_assets")
app.mount("/assets/portraits", StaticFiles(directory=str(PORTRAIT_DIR)), name="portrait_assets")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    kokoro_alive = False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.get(f"{KOKORO_URL}/health")
            kokoro_alive = r.status_code == 200
    except Exception:
        pass

    rhubarb_alive = False
    if RHUBARB_BIN is not None:
        try:
            rhubarb_alive = (
                subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                    [RHUBARB_BIN, "--version"], capture_output=True, timeout=3
                ).returncode
                == 0
            )
        except (OSError, subprocess.SubprocessError):
            rhubarb_alive = False

    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "port": PORT,
        "purpose": "3D AI Model Builder — entity assembly pod",
        "tts": {
            "kokoro": "available"
            if kokoro_alive
            else "unavailable (install: github.com/eduardolat/kokoro-web)",
            "piper": "check PIPER_BIN env",
        },
        "lip_sync": {
            "rhubarb": "available"
            if rhubarb_alive
            else "unavailable (install: github.com/DanielSWolf/rhubarb-lip-sync)",
        },
        "entities_configured": len(ENTITY_EMBODIMENT),
        "vrm_assets": len(list(VRM_DIR.glob("*.vrm"))) if VRM_DIR.exists() else 0,
        "animation_assets": len(list(ANIM_DIR.glob("*.glb"))) if ANIM_DIR.exists() else 0,
    }


# ---------------------------------------------------------------------------
# Entity manifest endpoints
# ---------------------------------------------------------------------------


@app.get("/entities")
async def list_entities():
    """List all entity embodiment manifests."""
    return {
        "count": len(ENTITY_EMBODIMENT),
        "entities": [
            {
                "entity_id": eid,
                "lead_ai": cfg.get("lead_ai"),
                "voice_engine": cfg.get("voice", {}).get("engine", "unknown"),
                "has_vrm": bool(cfg.get("avatar", {}).get("vrm")),
                "has_portrait": bool(cfg.get("avatar", {}).get("portrait")),
            }
            for eid, cfg in ENTITY_EMBODIMENT.items()
        ],
    }


@app.get("/entities/{entity_id}")
async def get_entity(entity_id: str):
    """Full entity spec: personality soul + voice + avatar body."""
    embodiment = ENTITY_EMBODIMENT.get(entity_id)
    if not embodiment:
        raise HTTPException(404, f"Entity '{entity_id}' not configured in Turing's Hub") from None

    # Try to load personality profile
    personality: Dict[str, Any] = {}
    for profile_path in PERSONALITY_DIR.glob("*.json"):
        try:
            data = json.loads(profile_path.read_text())
            # Match on id or code_name
            ai_name = embodiment.get("lead_ai", "").lower()
            if (
                data.get("id", "").lower() == ai_name
                or data.get("code_name", "").lower() == ai_name
                or profile_path.stem.lower() == ai_name.replace(" ", "-").replace("'", "")
            ):
                personality = data
                break
        except Exception:
            pass

    vrm_file = embodiment.get("avatar", {}).get("vrm")
    anim_files = embodiment.get("animations", {})

    return {
        "entity_id": entity_id,
        "lead_ai": embodiment.get("lead_ai"),
        "soul": personality,  # personality traits, behavior, system_prompt_prefix
        "voice": embodiment.get("voice"),
        "avatar": {
            **embodiment.get("avatar", {}),
            "vrm_url": f"/assets/vrm/{vrm_file}" if vrm_file else None,
            "vrm_ready": (VRM_DIR / vrm_file).exists() if vrm_file else False,
        },
        "animations": {
            k: {
                "file": v,
                "url": f"/assets/animations/{v}",
                "ready": (ANIM_DIR / v).exists() if v else False,
            }
            for k, v in anim_files.items()
        },
        "forge_note": (
            "VRM assets not yet placed. Create character in VRoid Studio "
            "(vroid.com/en/studio), export as .vrm, place in "
            f"workers/turings-hub-service/assets/vrm/{vrm_file or entity_id + '.vrm'}"
        )
        if vrm_file and not (VRM_DIR / vrm_file).exists()
        else None,
    }


# ---------------------------------------------------------------------------
# Speak — TTS + lip sync
# ---------------------------------------------------------------------------


@app.post("/entities/{entity_id}/speak", response_model=SpeakResponse)
async def speak(entity_id: str, body: SpeakRequest):
    """
    Synthesise speech for an entity.
    Returns audio URL + Rhubarb viseme timeline for lip sync.

    The browser's TalkingHead class consumes the audio URL and visemes
    to drive the VRM avatar's mouth shapes in real time.
    """
    embodiment = ENTITY_EMBODIMENT.get(entity_id, _DEFAULT_EMBODIMENT)

    audio_bytes, engine_used = await _synthesise(entity_id, body.text, body.member)

    visemes: Optional[List[Dict[str, Any]]] = None
    audio_url: Optional[str] = None
    duration_ms: Optional[float] = None

    if audio_bytes:
        # Cache WAV and expose URL
        session_id = uuid.uuid4().hex[:12]
        _audio_cache[session_id] = audio_bytes
        audio_url = f"/audio/{session_id}.wav"

        # Run Rhubarb in temp file
        if body.include_visemes:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            visemes = _rhubarb_visemes(tmp_path)
            Path(tmp_path).unlink(missing_ok=True)

        # Estimate duration (WAV header at bytes 40-44 is data size; 44100 Hz PCM16)
        try:
            if len(audio_bytes) > 44:
                import struct

                data_size = struct.unpack_from("<I", audio_bytes, 40)[0]
                duration_ms = (data_size / (44100 * 2)) * 1000
        except Exception:
            pass

    return SpeakResponse(
        entity_id=entity_id,
        lead_ai=embodiment.get("lead_ai", "Unknown"),
        text=body.text,
        emotion=body.emotion,
        audio_url=audio_url,
        visemes=visemes,
        duration_ms=duration_ms,
        tts_engine=engine_used,
    )


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve a cached TTS audio file."""
    session_id = filename.replace(".wav", "")
    if session_id not in _audio_cache:
        raise HTTPException(404, "Audio not found or expired") from None
    import io

    from fastapi.responses import StreamingResponse

    return StreamingResponse(io.BytesIO(_audio_cache[session_id]), media_type="audio/wav")


# ---------------------------------------------------------------------------
# WebSocket — real-time streaming
# ---------------------------------------------------------------------------


@app.websocket("/entities/{entity_id}/stream")
async def entity_stream(ws: WebSocket, entity_id: str):
    """
    Real-time entity stream.
    Client sends: {"text": "...", "emotion": "neutral", "member": null}
    Server sends:
      {"type": "audio_chunk", "data": "<base64 WAV chunk>"}
      {"type": "visemes", "data": [{...}]}
      {"type": "done", "duration_ms": 1234}
    """
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await ws.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            text = msg.get("text", "")
            if not text:
                continue

            req = SpeakRequest(
                text=text,
                emotion=msg.get("emotion", "neutral"),
                member=msg.get("member"),
                include_visemes=True,
            )
            result = await speak(entity_id, req)

            import base64

            if result.audio_url:
                session_id = result.audio_url.split("/")[-1].replace(".wav", "")
                audio_bytes = _audio_cache.get(session_id, b"")
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "audio_chunk",
                            "data": base64.b64encode(audio_bytes).decode(),
                            "mime": "audio/wav",
                        }
                    )
                )

            if result.visemes:
                await ws.send_text(json.dumps({"type": "visemes", "data": result.visemes}))

            await ws.send_text(
                json.dumps(
                    {
                        "type": "done",
                        "duration_ms": result.duration_ms,
                        "tts_engine": result.tts_engine,
                        "emotion": result.emotion,
                    }
                )
            )

    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Forge — assemble a new entity
# ---------------------------------------------------------------------------


@app.post("/forge")
async def forge_entity(body: ForgeRequest):
    """
    Register a new entity embodiment config.
    Call this after you have created a VRM in VRoid Studio and placed it
    in workers/turings-hub-service/assets/vrm/
    """
    ENTITY_EMBODIMENT[body.entity_id] = {
        "lead_ai": body.lead_ai,
        "voice": {
            "engine": body.voice_engine,
            "voice_id": body.voice_id,
            "pitch": 1.0,
            "speed": 1.0,
            **body.personality_overrides.get("voice", {}),
        },
        "avatar": {
            "vrm": body.vrm_filename or f"{body.entity_id}.vrm",
            "portrait": body.portrait_filename or f"{body.entity_id}.png",
        },
        "animations": {
            "idle": "idle_default.glb",
            "talk": "talk_gesture.glb",
        },
    }
    return {
        "status": "forged",
        "entity_id": body.entity_id,
        "lead_ai": body.lead_ai,
        "vrm_expected_at": str(VRM_DIR / (body.vrm_filename or f"{body.entity_id}.vrm")),
        "next_steps": [
            f"1. Create '{body.lead_ai}' character in VRoid Studio (vroid.com/en/studio)",
            f"2. Export as .vrm → place at workers/turings-hub-service/assets/vrm/{body.vrm_filename or body.entity_id + '.vrm'}",
            "3. Download idle + talk animations from Mixamo (mixamo.com), convert to GLB",
            "4. Place GLBs at workers/turings-hub-service/assets/animations/",
            f"5. Test: POST /entities/{body.entity_id}/speak with sample text",
            "6. In browser: load TalkingHead class + three-vrm, point to this service",
        ],
    }


# ---------------------------------------------------------------------------
# Setup guide
# ---------------------------------------------------------------------------


@app.get("/setup")
async def setup_guide():
    """Full setup instructions for the 3D AI entity stack."""
    return {
        "stack": {
            "avatar_format": "VRM (Virtual Reality Model) — universal humanoid standard",
            "renderer": "three-vrm (MIT) — https://github.com/pixiv/three-vrm",
            "frontend_class": "TalkingHead (MIT) — https://github.com/met4citizen/TalkingHead",
            "tts_primary": "Kokoro TTS (Apache 2.0) — https://github.com/eduardolat/kokoro-web",
            "tts_fallback": "Piper TTS (MIT) — https://github.com/rhasspy/piper",
            "lip_sync": "Rhubarb Lip Sync (MIT) — https://github.com/DanielSWolf/rhubarb-lip-sync",
            "character_creator": "VRoid Studio (free) — https://vroid.com/en/studio",
            "animations": "Mixamo (free/royalty-free) — https://www.mixamo.com",
            "motion_gen": "MotionGPT (MIT, GPU) — https://github.com/OpenMotionLab/MotionGPT",
            "pose_drive": "MediaPipe (Apache 2.0) — https://ai.google.dev/edge/mediapipe",
            "reference_impl": "TalkMateAI — https://github.com/kiranbaby14/TalkMateAI",
        },
        "install": {
            "kokoro": "docker run -p 8080:8080 ghcr.io/eduardolat/kokoro-web:latest",
            "piper": "pip install piper-tts",
            "rhubarb": "Download binary from github.com/DanielSWolf/rhubarb-lip-sync/releases → add to PATH or set RHUBARB_BIN env",
        },
        "workflow": [
            "1. CHARACTER DESIGN: Open VRoid Studio, design the AI entity's appearance",
            "2. EXPORT: File → Export as VRM → place in workers/turings-hub-service/assets/vrm/",
            "3. ANIMATIONS: Download idle/walk/talk/emote GLBs from Mixamo → assets/animations/",
            "4. VOICE: Configure voice_id in ENTITY_EMBODIMENT dict or POST /forge",
            "5. BACKEND: This service synthesises voice + visemes per entity",
            "6. FRONTEND: Load TalkingHead class in web/ — it handles three-vrm + animation + lip sync",
            "7. WIRE UP: Connect frontend to /entities/{id}/speak or /entities/{id}/stream",
        ],
        "current_vrm_assets": [f.name for f in VRM_DIR.glob("*.vrm")] if VRM_DIR.exists() else [],
        "current_animations": [f.name for f in ANIM_DIR.glob("*.glb")] if ANIM_DIR.exists() else [],
        "entities_configured": len(ENTITY_EMBODIMENT),
        "entities_vrm_ready": sum(
            1
            for cfg in ENTITY_EMBODIMENT.values()
            if cfg.get("avatar", {}).get("vrm") and (VRM_DIR / cfg["avatar"]["vrm"]).exists()
        ),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
