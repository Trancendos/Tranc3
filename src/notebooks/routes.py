# src/notebooks/routes.py
"""HTTP routes for the Notebook Registry (the /notebooks API).

Auth model: every route requires an authenticated caller (`get_current_user`)
— there is no fully public, unauthenticated read here. Which entries a caller
sees is then filtered by `visibility`:

- `admin` role sees everything for the requested owner (`ai_private` +
  `operator` + `public`).
- Any other authenticated caller sees `operator` + `public` only — matching
  the "operator = authenticated human staff" audience from
  `docs/governance/NOTEBOOKS-JOURNALS-SCOPE.md` §3.1/§4.
- `ai_private` is deliberately never visible to a non-admin caller: this
  platform has no per-AI authenticated principal to check `owner` against
  (see registry.py's module docstring), so restricting to admins is the
  honest substitute for "only the owning AI can read this."

A fully public, no-auth `public`-tier endpoint was left out — the scope doc
frames `public` visibility as an open design question, not a decided
default, and the registry's own default for new entries is `ai_private`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from src.notebooks.registry import NotebookEntry, get_registry

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


class CreateEntryRequest(BaseModel):
    owner: str
    content: str
    visibility: str = "ai_private"
    linked_card_id: Optional[str] = None
    linked_location: Optional[str] = None


def _require_admin(current_user: dict) -> None:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to write Notebook entries")


def _serialize(entry: NotebookEntry) -> Dict[str, Any]:
    return {
        "id": entry.id,
        "owner": entry.owner,
        "created_at": entry.created_at,
        "content": entry.content,
        "visibility": entry.visibility,
        "linked_card_id": entry.linked_card_id,
        "linked_location": entry.linked_location,
    }


def _visible_to(current_user: dict, entry: NotebookEntry) -> bool:
    if current_user.get("role") == "admin":
        return True
    return entry.visibility in ("operator", "public")


@router.post("")
def create_entry(
    body: CreateEntryRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        entry = get_registry().create_entry(
            owner=body.owner,
            content=body.content,
            visibility=body.visibility,
            linked_card_id=body.linked_card_id,
            linked_location=body.linked_location,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize(entry)


@router.get("/{owner}")
def list_for_owner(
    owner: str,
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    entries = get_registry().list_for_owner(owner)
    return [_serialize(e) for e in entries if _visible_to(current_user, e)]


@router.get("/card/{card_id}")
def list_for_card(
    card_id: str,
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Task -> Notebook direction (§3.3): every entry linked to one CranBania Card."""
    entries = get_registry().list_for_card(card_id)
    return [_serialize(e) for e in entries if _visible_to(current_user, e)]
