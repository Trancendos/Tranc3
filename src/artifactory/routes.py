# src/artifactory/routes.py
# The Artifactory — HTTP routes for OCI artefact repository.

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Path, Query
from fastapi.responses import JSONResponse

from src.artifactory.registry import ArtifactType, get_artifactory

router = APIRouter(prefix="/artifactory", tags=["the-artifactory"])


@router.get("/status")
async def artifactory_status() -> Dict[str, Any]:
    return get_artifactory().stats()


@router.get("/artifacts")
async def list_artifacts(
    type: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
) -> list:
    atype = None
    if type:
        try:
            atype = ArtifactType(type)
        except ValueError:
            valid = [t.value for t in ArtifactType]
            return JSONResponse({"error": f"Unknown type. Valid: {valid}"}, status_code=400)
    return [
        a.to_dict()
        for a in get_artifactory().list_artifacts(artifact_type=atype, namespace=namespace)
    ]


@router.post("/artifacts")
async def create_artifact(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    name = body.get("name")
    raw_type = body.get("type", "generic")
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=400)
    try:
        atype = ArtifactType(raw_type)
    except ValueError:
        valid = [t.value for t in ArtifactType]
        return JSONResponse({"error": f"Unknown type. Valid: {valid}"}, status_code=400)
    artifact = get_artifactory().create_artifact(
        name=name,
        artifact_type=atype,
        namespace=body.get("namespace", "trancendos"),
        description=body.get("description", ""),
        ttl_days=body.get("ttl_days"),
    )
    return artifact.to_dict()


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str = Path(...)) -> Dict[str, Any]:
    artifact = get_artifactory().get_artifact(artifact_id)
    if not artifact:
        return JSONResponse({"error": "Artifact not found"}, status_code=404)
    return {**artifact.to_dict(), "versions": [v.to_dict() for v in artifact.versions]}


@router.post("/artifacts/{artifact_id}/versions")
async def push_version(
    artifact_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    version = body.get("version")
    if not version:
        return JSONResponse({"error": "version is required"}, status_code=400)
    ver = get_artifactory().push_version(
        artifact_id=artifact_id,
        version=version,
        digest=body.get("digest", ""),
        size_bytes=body.get("size_bytes", 0),
        tags=body.get("tags"),
        metadata=body.get("metadata"),
    )
    if ver is None:
        return JSONResponse({"error": "Artifact not found or deleted"}, status_code=404)
    return ver.to_dict()


@router.delete("/artifacts/{artifact_id}")
async def delete_artifact(artifact_id: str = Path(...)) -> Dict[str, Any]:
    ok = get_artifactory().delete_artifact(artifact_id)
    if not ok:
        return JSONResponse({"error": "Artifact not found"}, status_code=404)
    return {"deleted": artifact_id}


@router.post("/retention/apply")
async def apply_retention() -> Dict[str, Any]:
    removed = get_artifactory().apply_retention()
    return {"versions_removed": removed}
