# src/apimarket/routes.py
# API Marketplace — HTTP routes for the Trancendos API connector hub.

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Path, Query
from fastapi.responses import JSONResponse

from src.apimarket.marketplace import AuthType, ConnectorStatus, get_marketplace

router = APIRouter(prefix="/apimarket", tags=["api-marketplace"])


@router.get("/status")
async def apimarket_status() -> Dict[str, Any]:
    return get_marketplace().stats()


@router.get("/connectors")
async def list_connectors(
    tag: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
) -> Response:
    ss = None
    if status:
        try:
            ss = ConnectorStatus(status)
        except ValueError:
            return JSONResponse({"error": "Unknown status"}, status_code=400)
    return [c.to_dict() for c in get_marketplace().list_connectors(tag=tag, status=ss)]


@router.get("/connectors/{connector_id}")
async def get_connector(connector_id: str = Path(...)) -> Response:
    connector = get_marketplace().get_connector(connector_id)
    if not connector:
        # Try by slug
        connector = get_marketplace().find_by_slug(connector_id)
    if not connector:
        return JSONResponse({"error": "Connector not found"}, status_code=404)
    return {**connector.to_dict(), "endpoints": [e.to_dict() for e in connector.endpoints]}


@router.post("/connectors")
async def register_connector(body: Dict[str, Any] = Body(...)) -> Response:
    name = body.get("name")
    slug = body.get("slug")
    base_url = body.get("base_url")
    if not all([name, slug, base_url]):
        return JSONResponse({"error": "name, slug, base_url are required"}, status_code=400)
    raw_auth = body.get("auth_type", "none")
    try:
        auth_type = AuthType(raw_auth)
    except ValueError:
        valid = [a.value for a in AuthType]
        return JSONResponse({"error": f"Unknown auth_type. Valid: {valid}"}, status_code=400)
    connector = get_marketplace().register(
        name=name,  # type: ignore[arg-type]
        slug=slug,  # type: ignore[arg-type]
        base_url=base_url,  # type: ignore[arg-type]
        auth_type=auth_type,
        description=body.get("description", ""),
        tags=body.get("tags"),
        rate_limit_per_min=body.get("rate_limit_per_min", 60),
    )
    return connector.to_dict()


@router.post("/connectors/{connector_id}/endpoints")
async def add_endpoint(
    connector_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Response:
    method = body.get("method", "GET")
    path = body.get("path")
    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)
    ep = get_marketplace().add_endpoint(
        connector_id, method=method, path=path, description=body.get("description", "")
    )
    if ep is None:
        return JSONResponse({"error": "Connector not found"}, status_code=404)
    return ep.to_dict()