# src/devocity/routes.py
# DevOcity — HTTP routes for the Trancendos developer centre.

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Path
from fastapi.responses import JSONResponse, Response

from src.devocity.portal import ApiKeyScope, get_devocity

router = APIRouter(prefix="/devocity", tags=["devocity"])


@router.get("/status")
async def devocity_status() -> Dict[str, Any]:
    return get_devocity().stats()


@router.get("/guides")
async def list_guides() -> list:
    return get_devocity().guides()


@router.post("/accounts")
async def create_account(body: Dict[str, Any] = Body(...)) -> Response:
    user_id = body.get("user_id")
    display_name = body.get("display_name", "Developer")
    if not user_id:
        return JSONResponse({"error": "user_id is required"}, status_code=400)
    account = get_devocity().create_account(user_id=user_id, display_name=display_name)
    return account.to_dict()  # type: ignore[return-value]


@router.get("/accounts/{account_id}")
async def get_account(account_id: str = Path(...)) -> Response:
    account = get_devocity().get_account(account_id)
    if not account:
        return JSONResponse({"error": "Account not found"}, status_code=404)
    return account.to_dict()  # type: ignore[return-value]


@router.post("/accounts/{account_id}/keys")
async def issue_api_key(
    account_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Response:
    name = body.get("name", "default")
    raw_scopes = body.get("scopes", ["read"])
    try:
        scopes = [ApiKeyScope(s) for s in raw_scopes]
    except ValueError:
        valid = [s.value for s in ApiKeyScope]
        return JSONResponse({"error": f"Invalid scope. Valid: {valid}"}, status_code=400)
    result = get_devocity().issue_api_key(account_id, name=name, scopes=scopes)
    if result is None:
        return JSONResponse({"error": "Account not found"}, status_code=404)
    plain, api_key = result
    return {  # type: ignore[return-value]
        **api_key.to_dict(),
        "key": plain,
        "warning": "Store this key securely — it will not be shown again.",
    }


@router.get("/accounts/{account_id}/keys")
async def list_keys(account_id: str = Path(...)) -> Response:
    account = get_devocity().get_account(account_id)
    if not account:
        return JSONResponse({"error": "Account not found"}, status_code=404)
    return [k.to_dict() for k in account.api_keys if not k.revoked]  # type: ignore[return-value]


@router.delete("/accounts/{account_id}/keys/{key_id}")
async def revoke_key(account_id: str = Path(...), key_id: str = Path(...)) -> Response:
    ok = get_devocity().revoke_api_key(account_id, key_id)
    if not ok:
        return JSONResponse({"error": "Account or key not found"}, status_code=404)
    return {"revoked": key_id}  # type: ignore[return-value]


@router.post("/accounts/{account_id}/webhooks")
async def register_webhook(
    account_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Response:
    url = body.get("url")
    events = body.get("events", [])
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)
    webhook = get_devocity().register_webhook(account_id, url=url, events=events)
    if webhook is None:
        return JSONResponse({"error": "Account not found"}, status_code=404)
    return webhook.to_dict()  # type: ignore[return-value]


@router.get("/accounts/{account_id}/webhooks")
async def list_webhooks(account_id: str = Path(...)) -> Response:
    account = get_devocity().get_account(account_id)
    if not account:
        return JSONResponse({"error": "Account not found"}, status_code=404)
    return [w.to_dict() for w in account.webhooks if w.active]  # type: ignore[return-value]
