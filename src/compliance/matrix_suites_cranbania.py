# src/compliance/matrix_suites_cranbania.py
# Matrix Suites — CranBania review-card sync (Magna Carta Stage 7.4)
#
# docs/governance/MATRIX-SUITES.md §6 promises: "the staged integration (§7.4) maps each
# suite to a CranBania board lane with a workshop template per review cadence, so a suite
# review is a card with an SLA, not a calendar hope."
#
# CranBania's board (workers/cranbania/lib/types.ts) has no "lane" concept — only 5 fixed
# columns (backlog/planning/in_progress/review/done) shared by every card type; adding a
# swim-lane dimension would mean changing CranBania's own schema for a Tranc3-side reporting
# need. Instead, each suite's review card carries tags=["matrix-suite", <suite_id>] — the
# same "cross-cutting grouping without a schema change" role a lane would play, filterable
# in the CranBania UI/API exactly like a lane would be. This mirrors Stage 7.5's own
# decision (src/roles/suite_stewardship.py) to cross-reference existing infrastructure
# rather than bolt on a parallel structure for something that isn't actually a new entity.
#
# This module only ensures the *card* exists with a real slaDueAt — it does not duplicate
# overdue detection. emit_overdue_events() (src/compliance/matrix_suites.py, Stage 7.2)
# already emits governance.suite.<name>.review.overdue directly from the registry's
# next_review date, independent of CranBania; that stays the source of truth for "is this
# suite overdue". CranBania's own SLA breach webhooks then give the *card* holder the same
# escalation mechanics an incident gets, on the human-facing board — a second, complementary
# signal, not a re-implementation of the first.

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, timezone
from datetime import datetime as _datetime
from typing import Any, Dict, List, Optional

import httpx

from Dimensional.sanitize import sanitize_for_log
from src.compliance.matrix_suites import SuiteHealth, list_suite_health

logger = logging.getLogger("tranc3.compliance.matrix_suites_cranbania")

_DEFAULT_CRANBANIA_URL = "http://cranbania:8071"
_SUITE_TAG = "matrix-suite"
_CARD_TYPE = "change"  # DEFAULT_SLA_HOURS-eligible in CranBania; we always set our own anyway
_OPEN_COLUMNS = {"backlog", "planning", "in_progress", "review"}  # everything but "done"


def _cranbania_url() -> str:
    return os.getenv("CRANBANIA_URL", _DEFAULT_CRANBANIA_URL).rstrip("/")


def _cranbania_api_key() -> str:
    return os.getenv("CRANBANIA_API_KEY", "")


@dataclass
class SuiteCardSyncResult:
    suite_id: str
    action: str  # "created" | "skipped_open_card_exists" | "skipped_no_next_review" | "error"
    card_id: Optional[str] = None
    detail: str = ""


@dataclass
class SyncSummary:
    results: List[SuiteCardSyncResult] = field(default_factory=list)

    @property
    def created(self) -> int:
        return sum(1 for r in self.results if r.action == "created")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.action.startswith("skipped"))

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.action == "error")


def _has_open_suite_card(cards: List[Dict[str, Any]], suite_id: str) -> bool:
    for card in cards:
        tags = card.get("tags")
        if not isinstance(tags, list):
            continue
        if _SUITE_TAG in tags and suite_id in tags and card.get("columnId") in _OPEN_COLUMNS:
            return True
    return False


def _sla_response_hours(health: SuiteHealth, today: Optional[date] = None) -> int:
    """Hours from now until health.next_review, for CranBania's slaResponseHours.

    Clamped to >= 1: CranBania's create-card schema requires a positive
    number (z.number().positive()), and an overdue suite's real delta is
    negative or zero — exactly the case most needing a visible card, so it
    must not be silently rejected by the API instead of created.
    """
    today = today or _datetime.now(timezone.utc).date()
    due = date.fromisoformat(health.next_review)
    delta_hours = (due - today).days * 24
    return max(1, delta_hours)


def _card_description(health: SuiteHealth) -> str:
    return (
        f"Matrix Suite governance review — auto-created by Stage 7.4 sync.\n\n"
        f"Suite: {health.name} ({health.suite_id})\n"
        f"Pillar: {health.pillar}\n"
        f"Steward: {health.steward_ai} ({health.steward_location})\n"
        f"Cadence: {health.review_cadence}\n"
        f"Due: {health.next_review}\n\n"
        f"Move this card to Done when the review is complete — CranBania's SLA tracking "
        f"treats that the same way it treats a resolved incident."
    )


async def sync_suite_review_cards(
    matrix_suites_path: Optional[str] = None,
    cranbania_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> SyncSummary:
    """Ensure every suite with a valid next_review has one open CranBania
    review card. Idempotent: a suite already holding an open (non-Done)
    card tagged with its suite_id is skipped, not duplicated. A suite whose
    steward marks the current card Done will get a fresh one on the next
    sync — a new cycle, not a re-notification of the old one.
    """
    base_url = (cranbania_url or _cranbania_url()).rstrip("/")
    key = api_key if api_key is not None else _cranbania_api_key()
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    summary = SyncSummary()
    healths = list_suite_health(path=matrix_suites_path)

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=15.0) as client:
        try:
            list_resp = await client.get("/api/cards")
            list_resp.raise_for_status()
            existing_cards = list_resp.json().get("cards", [])
        except httpx.HTTPError as exc:
            logger.warning(
                "Failed to list CranBania cards before sync: %s",
                sanitize_for_log(exc),  # codeql[py/log-injection]
            )
            for health in healths:
                summary.results.append(
                    SuiteCardSyncResult(
                        suite_id=health.suite_id, action="error", detail="could not list cards"
                    )
                )
            return summary

        for health in healths:
            if not health.next_review_valid:
                summary.results.append(
                    SuiteCardSyncResult(
                        suite_id=health.suite_id,
                        action="skipped_no_next_review",
                        detail="registry next_review is missing/unparseable",
                    )
                )
                continue

            if _has_open_suite_card(existing_cards, health.suite_id):
                summary.results.append(
                    SuiteCardSyncResult(suite_id=health.suite_id, action="skipped_open_card_exists")
                )
                continue

            try:
                create_resp = await client.post(
                    "/api/cards",
                    json={
                        "title": f"{health.name} review — due {health.next_review}",
                        "description": _card_description(health),
                        "cardType": _CARD_TYPE,
                        "tags": [_SUITE_TAG, health.suite_id],
                        "slaResponseHours": _sla_response_hours(health),
                        "actor": "system",
                    },
                )
                create_resp.raise_for_status()
                card = create_resp.json().get("card", {})
                summary.results.append(
                    SuiteCardSyncResult(
                        suite_id=health.suite_id, action="created", card_id=card.get("id")
                    )
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "Failed to create CranBania review card for suite %s: %s",
                    sanitize_for_log(health.suite_id),  # codeql[py/log-injection]
                    sanitize_for_log(exc),  # codeql[py/log-injection]
                )
                summary.results.append(
                    SuiteCardSyncResult(suite_id=health.suite_id, action="error", detail=str(exc))
                )

    return summary
