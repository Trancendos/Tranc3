"""IceBox delivery invariants: auth imports and durable quarantine state.

Static checks are intentionally dependency-free so they can run before
containers are built. They do not replace a live container smoke test.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "workers" / "ice-box-service" / "Dockerfile"
COMPOSE = ROOT / "docker-compose.production.yml"


def _icebox_service(compose: str) -> str:
    start = compose.index("\n  ice-box-service:\n")
    tail = compose[start + 1:]
    return tail.split("\n  # ──", 1)[0]


def test_icebox_image_includes_canonical_auth_module_chain():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    for relative in (
        "Dimensionals/__init__.py",
        "Dimensionals/service_auth_fastapi.py",
        "Dimensionals/service_auth.py",
    ):
        assert (ROOT / relative).is_file(), relative
        assert f"COPY {relative} {relative}" in dockerfile, relative


def test_icebox_quarantine_db_survives_container_replacement():
    compose = COMPOSE.read_text(encoding="utf-8")
    service = _icebox_service(compose)
    assert "ice-box-quarantine:/app/workers/ice-box-service/data" in service
    assert "ICE_BOX_QUARANTINE_DB=/app/workers/ice-box-service/data/ice_box_quarantine.db" in service
    volumes_section = compose.rsplit("\nvolumes:\n", 1)[1].split("\nnetworks:\n", 1)[0]
    assert "\n  ice-box-quarantine:\n" in volumes_section
