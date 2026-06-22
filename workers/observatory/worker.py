"""Observatory worker entry point."""

from main import app  # noqa: F401 — imported for uvicorn

if __name__ == "__main__":
    import uvicorn

    import config

    uvicorn.run("main:app", host="0.0.0.0", port=config.WORKER_PORT, reload=False)
