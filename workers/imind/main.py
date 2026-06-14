"""I-Mind — Port 8061.

Sensitivity to emotion engine.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

try:
    from textblob import TextBlob

    _TEXTBLOB_AVAILABLE = True
except ImportError:
    _TEXTBLOB_AVAILABLE = False

app = FastAPI(title="I-Mind", version="1.0.0")

PORT = int(os.getenv("PORT", "8061"))
START_TIME = time.time()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"service": "imind", "status": "ok", "uptime": time.time() - START_TIME})


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "I-Mind",
            "lead_ai": "Elouise",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
            "textblob_available": _TEXTBLOB_AVAILABLE,
        }
    )


@app.post("/analyse")
async def analyse(body: dict) -> JSONResponse:
    text = body.get("text", "")
    if not text:
        return JSONResponse({"error": "text field required"}, status_code=422)
    if _TEXTBLOB_AVAILABLE:
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity
    else:
        polarity = 0.0
        subjectivity = 0.0
    return JSONResponse(
        {
            "text": text,
            "sentiment": {
                "polarity": polarity,
                "subjectivity": subjectivity,
                "label": "positive"
                if polarity > 0
                else ("negative" if polarity < 0 else "neutral"),
            },
            "engine": "textblob" if _TEXTBLOB_AVAILABLE else "stub",
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
