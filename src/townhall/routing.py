"""The Town Hall — governed routing of backlog items to Locations.

Why this exists
---------------
`docs/governance/ACTION-BACKLOG.md` sweeps 51 registers into one list. 170 of
its 201 items name no Location, so nobody is accountable for them and none of
them links to design material. The obvious fix — assign each one to a
Location by judgement and write the answer into the generator — would have
put a routing decision nobody made, nobody approved and nobody can appeal
into a file that reads as derived fact.

Routing is a decision, so it goes through the body that makes decisions. The
Town Hall records it here: who decided, which Location, on what written
reason, against which design material, at what time. The backlog generator
reads the decisions; it does not make them. An item with no decision stays
`_unrouted_`, and the count of those is a queue the Town Hall owes an answer
to rather than a number hidden by a plausible guess.

What makes it a decision record and not a lookup table
------------------------------------------------------
**A Location must exist.** Routing to a name that is not one of the 43 in
`src/entities/platform.py` is refused. A backlog routed to a Location nobody
runs is the CMDB defect again, one level up.

**Design material must exist.** The Location's solution pack — its
architecture, its compose-derived routing, its user journey and acceptance
criteria — is resolved at decision time and stored on the record. A Location
with no pack is refused, because routing work to a place with no design is
what "unrouted" already means.

**A reason and an authority are mandatory.** Both are validated non-empty.
A decision with no author is indistinguishable from a guess six months later,
which is exactly when somebody asks how an item ended up where it did.

**Nothing is overwritten.** Re-routing supersedes; both rows stay in
`routing_history`, so the sequence of decisions about one item is readable.

**The Observatory is told.** Every decision emits a platform event. The
SQLite row is the record and the event is the notification, the same
contract `src/townhall/plm.py` and `src/townhall/itsm.py` state.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from Dimensional.sanitize import sanitize_for_log
from src.entities.platform import PLATFORM_ENTITIES
from src.event_bus.types import PlatformEventType
from src.validation.validators import validate_non_empty, validate_safe_string

logger = logging.getLogger("tranc3.townhall.routing")

DEFAULT_DB_PATH = Path("data/townhall_routing.db")

REPO = Path(__file__).resolve().parent.parent.parent
PACKS = REPO / "docs" / "solution-packs"

#: Where the Town Hall's routing decisions are exported for CI to read. The
#: backlog generator runs in a checkout with no service and no database, so
#: the decisions have to be reviewable as a file in the repository — that is
#: also what makes a routing decision show up in a diff.
EXPORT = REPO / "config" / "estate" / "backlog_routing.yaml"


class RoutingRefused(ValueError):
    """A routing decision that the Town Hall will not record.

    Raised rather than returned. A refusal a caller may ignore is a warning,
    and a warning is how the estate accumulated controls that report and do
    not act.
    """


def pack_slug(location: str) -> str:
    """A Location name as its solution-pack filename.

    Deliberately the same expression as `_pack_slug` in
    `scripts/build_action_backlog.py`: the registry decides a Location has
    design material and the backlog links to it, so the two must agree about
    which file that is or the backlog links into the void.
    """
    return re.sub(r"[^a-z0-9]+", "-", location.lower()).strip("-")


def design_pack(location: str) -> Optional[str]:
    """The Location's solution pack, relative to the repository root."""
    pack = PACKS / f"{pack_slug(location)}.md"
    return str(pack.relative_to(REPO)) if pack.is_file() else None


@dataclass
class RoutingDecision:
    """One item, routed to one Location, by one named authority."""

    item_key: str
    location: str
    reason: str
    authority: str
    design_pack: str
    id: str = field(default_factory=lambda: f"RTG-{uuid.uuid4().hex[:10].upper()}")
    decided_at: float = field(default_factory=time.time)
    supersedes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "item_key": self.item_key,
            "location": self.location,
            "reason": self.reason,
            "authority": self.authority,
            "design_pack": self.design_pack,
            "decided_at": self.decided_at,
            "supersedes": self.supersedes,
        }


def _emit(event_type: PlatformEventType, data: dict[str, Any]) -> None:
    """Announce a decision that has already been committed."""
    try:
        from src.event_bus import get_event_bus  # noqa: PLC0415

        get_event_bus().emit_async(
            event_type=event_type.value, data=data, source="townhall.routing"
        )
    except Exception as exc:  # noqa: BLE001 - a notification must not fail the write
        logger.debug("routing: emit %s: %s", event_type.value, sanitize_for_log(exc))


class RoutingRegistry:
    """Durable routing decisions, each refusable and none overwritten."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._lock = threading.RLock()
        if self._path.parent != Path(""):
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS routing_decisions (
                    id          TEXT PRIMARY KEY,
                    item_key    TEXT NOT NULL,
                    location    TEXT NOT NULL,
                    reason      TEXT NOT NULL,
                    authority   TEXT NOT NULL,
                    design_pack TEXT NOT NULL,
                    decided_at  REAL NOT NULL,
                    supersedes  TEXT
                );
                CREATE TABLE IF NOT EXISTS routing_history (
                    id          TEXT PRIMARY KEY,
                    item_key    TEXT NOT NULL,
                    location    TEXT NOT NULL,
                    reason      TEXT NOT NULL,
                    authority   TEXT NOT NULL,
                    design_pack TEXT NOT NULL,
                    decided_at  REAL NOT NULL,
                    supersedes  TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_routing_item
                    ON routing_decisions(item_key);
                CREATE INDEX IF NOT EXISTS idx_routing_history_item
                    ON routing_history(item_key, decided_at);
            """)
            self._conn.commit()

    # ── decisions ───────────────────────────────────────────────────────────

    def route(
        self,
        item_key: str,
        location: str,
        reason: str,
        authority: str,
    ) -> RoutingDecision:
        """Record where an item belongs, or refuse to.

        Every refusal below is a case where recording the decision would put
        a fact into the backlog that nothing backs.
        """
        item_key = validate_safe_string(validate_non_empty(item_key, "item_key"), "item_key", 400)
        location = validate_safe_string(validate_non_empty(location, "location"), "location", 200)
        reason = validate_safe_string(validate_non_empty(reason, "reason"), "reason", 2000)
        authority = validate_safe_string(
            validate_non_empty(authority, "authority"), "authority", 200
        )

        if location not in PLATFORM_ENTITIES:
            raise RoutingRefused(
                f"{location!r} is not one of the {len(PLATFORM_ENTITIES)} Locations in "
                "src/entities/platform.py. Routing to a Location nobody runs is the "
                "same defect as a CMDB record naming a container nobody starts."
            )
        pack = design_pack(location)
        if pack is None:
            raise RoutingRefused(
                f"{location!r} has no solution pack under docs/solution-packs/, so this "
                "routing would carry no architecture, journey or acceptance criteria — "
                "which is what leaving the item unrouted already says."
            )

        previous = self.decision(item_key)
        decision = RoutingDecision(
            item_key=item_key,
            location=location,
            reason=reason,
            authority=authority,
            design_pack=pack,
            supersedes=previous.id if previous else None,
        )
        row = (
            decision.id,
            decision.item_key,
            decision.location,
            decision.reason,
            decision.authority,
            decision.design_pack,
            decision.decided_at,
            decision.supersedes,
        )
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO routing_decisions "
                "(id, item_key, location, reason, authority, design_pack, decided_at, supersedes) "
                "VALUES (?,?,?,?,?,?,?,?)",
                row,
            )
            # History is append-only. The current decision is replaceable; the
            # sequence of decisions about an item is not, because "why is this
            # with Cryptex now when it was with The Lab" is the question a
            # routing register exists to answer.
            self._conn.execute(
                "INSERT INTO routing_history "
                "(id, item_key, location, reason, authority, design_pack, decided_at, supersedes) "
                "VALUES (?,?,?,?,?,?,?,?)",
                row,
            )
            self._conn.commit()
        _emit(PlatformEventType.TOWNHALL_ITEM_ROUTED, decision.to_dict())
        return decision

    def decision(self, item_key: str) -> Optional[RoutingDecision]:
        row = self._conn.execute(
            "SELECT * FROM routing_decisions WHERE item_key=?", (item_key,)
        ).fetchone()
        return self._from_row(row) if row else None

    def decisions(self) -> list[RoutingDecision]:
        rows = self._conn.execute("SELECT * FROM routing_decisions ORDER BY item_key").fetchall()
        return [self._from_row(row) for row in rows]

    def history(self, item_key: str) -> list[RoutingDecision]:
        rows = self._conn.execute(
            "SELECT * FROM routing_history WHERE item_key=? ORDER BY decided_at",
            (item_key,),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> RoutingDecision:
        return RoutingDecision(
            id=row["id"],
            item_key=row["item_key"],
            location=row["location"],
            reason=row["reason"],
            authority=row["authority"],
            design_pack=row["design_pack"],
            decided_at=row["decided_at"],
            supersedes=row["supersedes"],
        )

    # ── export ──────────────────────────────────────────────────────────────

    def export(self, path: Path | str | None = None) -> Path:
        """Write the decisions where CI, and a reviewer, can read them.

        Deterministic and sorted: a routing decision should show up in a diff
        as one added block, not as a reshuffle of the whole file.
        """
        import yaml  # noqa: PLC0415 - only needed on the export path

        path = Path(path) if path is not None else EXPORT
        payload = {
            "decisions": [
                {
                    "item_key": d.item_key,
                    "location": d.location,
                    "authority": d.authority,
                    "reason": d.reason,
                    "design_pack": d.design_pack,
                }
                for d in self.decisions()
            ]
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# The Town Hall's backlog routing decisions.\n"
            "#\n"
            "# Generated by `RoutingRegistry.export` (src/townhall/routing.py) and read\n"
            "# by scripts/build_action_backlog.py. Do not hand-edit: a routing decision\n"
            "# made by editing this file has no authority, no history and no Observatory\n"
            "# record, which is the whole of what makes it a decision rather than a guess.\n"
            "#\n"
            "# Route an item through `POST /townhall/routing/decisions`, then re-export.\n"
            + yaml.safe_dump(payload, sort_keys=True, allow_unicode=True, width=100),
            encoding="utf-8",
        )
        return path


def load_decisions(path: Path | str | None = None) -> dict[str, dict[str, str]]:
    """The exported decisions, keyed by item, for readers with no database.

    Returns an empty mapping when nothing has been routed yet — an absent
    file means no decisions, not an error, so the backlog still generates on
    a fresh checkout and simply reports everything as awaiting one.

    `EXPORT` is resolved on each call rather than bound as a default, so the
    location can be redirected — a default evaluated at import time cannot
    be, which makes the read path untestable against anything but the real
    repository file.
    """
    import yaml  # noqa: PLC0415

    path = Path(path) if path is not None else EXPORT
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {d["item_key"]: d for d in payload.get("decisions", [])}


_REGISTRY: Optional[RoutingRegistry] = None


def get_routing_registry(db_path: Path | str = DEFAULT_DB_PATH) -> RoutingRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = RoutingRegistry(db_path)
    return _REGISTRY
