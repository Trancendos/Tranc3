"""Imaginarium — Port 8064.

Omni-creative masterpiece wizard (orchestrates Studio, TateKing, TranceFlow, Photo).
"""

from __future__ import annotations

import os
import time

from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse

from Dimensional.service_auth_fastapi import guard_internal_secret

app = FastAPI(title="Imaginarium", version="1.0.0")

PORT = int(os.getenv("PORT", "8064"))
START_TIME = time.time()

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


def _require_internal_auth(x_internal_secret: str = Header(default="")) -> None:
    # Delegated to Dimensional.service_auth, which this worker now reaches
    # through the `sharedcore` named build context. It compares with
    # compare_digest and refuses when the secret is unset.
    guard_internal_secret(
        x_internal_secret, INTERNAL_SECRET, mismatch_status=403, detail="Forbidden"
    )


CAPABILITIES = [
    {"name": "The Studio", "slug": "the-studio", "port": 8050, "role": "Central creativity hub"},
    {"name": "TateKing", "slug": "tateking", "port": 8053, "role": "Video creation & editing"},
    {"name": "TranceFlow", "slug": "tranceflow", "port": 8052, "role": "3D modeling & games"},
    {
        "name": "Sashas Photo Studio",
        "slug": "sashas-photo-studio",
        "port": 8051,
        "role": "Photo & image generation",
    },
    {"name": "Warp Radio", "slug": "warp-radio", "port": 8057, "role": "Music & audio streaming"},
]


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {"service": "imaginarium", "status": "ok", "uptime": time.time() - START_TIME}
    )


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "Imaginarium",
            "lead_ai": "Voxx",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
        }
    )


@app.post("/orchestrate", dependencies=[Depends(_require_internal_auth)])
async def orchestrate() -> JSONResponse:
    return JSONResponse(
        {"orchestrated": False, "message": "Orchestration not yet ready."}, status_code=202
    )


@app.get("/capabilities")
async def capabilities() -> JSONResponse:
    return JSONResponse({"capabilities": CAPABILITIES, "total": len(CAPABILITIES)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)  # nosec B104 — containerised service
