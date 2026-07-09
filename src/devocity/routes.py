# src/devocity/routes.py
# DevOcity — HTTP routes for the Trancendos developer centre.

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from fastapi.responses import JSONResponse

from auth import get_current_user
from src.devocity.portal import ApiKeyScope, DeveloperAccount, get_devocity

router = APIRouter(prefix="/devocity", tags=["devocity"])


def _caller_id(current_user: dict) -> Any:
    """Real JWT payloads (src/auth/tokens.py) carry the caller's identity under
    the standard "sub" claim, not "id" — accept either so ownership checks
    don't 500 for genuine callers with real tokens."""
    return current_user.get("id") or current_user.get("sub")


def _require_account_owner(account: DeveloperAccount, current_user: dict) -> None:
    """Mirrors api.py's gdpr_erase() ownership check: users may act on their own
    developer account; admins may act on any account.

    The "enterprise" override this originally mirrored from gdpr_erase()
    checked `tier == "enterprise"`, but real tokens carry `tier` as a numeric
    int (never that string) — checking `role == "admin"` instead uses a
    claim real tokens actually carry."""
    if account.user_id != _caller_id(current_user) and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Can only access your own developer account")


def _get_owned_account(account_id: str, current_user: dict) -> DeveloperAccount:
    account = get_devocity().get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    _require_account_owner(account, current_user)
    return account


@router.get("/status")
async def devocity_status() -> Dict[str, Any]:
    return get_devocity().stats()


@router.get("/guides")
async def list_guides() -> list:
    return get_devocity().guides()


@router.post("/accounts")
async def create_account(
    body: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    user_id = body.get("user_id")
    display_name = body.get("display_name", "Developer")
    if not user_id:
        return JSONResponse({"error": "user_id is required"}, status_code=400)
    if user_id != _caller_id(current_user) and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Can only create your own developer account")
    account = get_devocity().create_account(user_id=user_id, display_name=display_name)
    return account.to_dict()


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        account = _get_owned_account(account_id, current_user)
    except HTTPException as exc:
        if exc.status_code == 404:
            return JSONResponse({"error": "Account not found"}, status_code=404)
        raise
    return account.to_dict()


@router.post("/accounts/{account_id}/keys")
async def issue_api_key(
    account_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        _get_owned_account(account_id, current_user)
    except HTTPException as exc:
        if exc.status_code == 404:
            return JSONResponse({"error": "Account not found"}, status_code=404)
        raise
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
    return {
        **api_key.to_dict(),
        "key": plain,
        "warning": "Store this key securely — it will not be shown again.",
    }


@router.get("/accounts/{account_id}/keys")
async def list_keys(
    account_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> list:
    try:
        account = _get_owned_account(account_id, current_user)
    except HTTPException as exc:
        if exc.status_code == 404:
            return JSONResponse({"error": "Account not found"}, status_code=404)
        raise
    return [k.to_dict() for k in account.api_keys if not k.revoked]


@router.delete("/accounts/{account_id}/keys/{key_id}")
async def revoke_key(
    account_id: str = Path(...),
    key_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        _get_owned_account(account_id, current_user)
    except HTTPException as exc:
        if exc.status_code == 404:
            return JSONResponse({"error": "Account or key not found"}, status_code=404)
        raise
    ok = get_devocity().revoke_api_key(account_id, key_id)
    if not ok:
        return JSONResponse({"error": "Account or key not found"}, status_code=404)
    return {"revoked": key_id}


@router.post("/accounts/{account_id}/webhooks")
async def register_webhook(
    account_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        _get_owned_account(account_id, current_user)
    except HTTPException as exc:
        if exc.status_code == 404:
            return JSONResponse({"error": "Account not found"}, status_code=404)
        raise
    url = body.get("url")
    events = body.get("events", [])
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)
    webhook = get_devocity().register_webhook(account_id, url=url, events=events)
    if webhook is None:
        return JSONResponse({"error": "Account not found"}, status_code=404)
    return webhook.to_dict()


@router.get("/accounts/{account_id}/webhooks")
async def list_webhooks(
    account_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> list:
    try:
        account = _get_owned_account(account_id, current_user)
    except HTTPException as exc:
        if exc.status_code == 404:
            return JSONResponse({"error": "Account not found"}, status_code=404)
        raise
    return [w.to_dict() for w in account.webhooks if w.active]
