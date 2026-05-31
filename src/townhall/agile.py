"""The Town Hall — Agile / Kanban boards."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class KanbanColumn(str, Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


@dataclass
class KanbanCard:
    id: str
    title: str
    column: KanbanColumn
    description: str = ""
    assignee: str | None = None
    labels: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "column": self.column.value,
            "description": self.description,
            "assignee": self.assignee,
            "labels": self.labels,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class KanbanBoard:
    id: str
    name: str
    framework: str = "kanban"
    cards: dict[str, KanbanCard] = field(default_factory=dict)

    def add_card(
        self,
        title: str,
        *,
        column: KanbanColumn = KanbanColumn.BACKLOG,
        description: str = "",
        assignee: str | None = None,
    ) -> KanbanCard:
        card = KanbanCard(
            id=str(uuid.uuid4()),
            title=title,
            column=column,
            description=description,
            assignee=assignee,
        )
        self.cards[card.id] = card
        return card

    def move_card(self, card_id: str, column: KanbanColumn) -> KanbanCard | None:
        card = self.cards.get(card_id)
        if not card:
            return None
        card.column = column
        card.updated_at = time.time()
        return card

    def columns_view(self) -> dict[str, list[dict[str, Any]]]:
        view: dict[str, list[dict[str, Any]]] = {c.value: [] for c in KanbanColumn}
        for card in self.cards.values():
            view[card.column.value].append(card.to_dict())
        return view

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "framework": self.framework,
            "card_count": len(self.cards),
            "columns": self.columns_view(),
        }


class KanbanService:
    def __init__(self) -> None:
        self._boards: dict[str, KanbanBoard] = {}
        default = KanbanBoard(id="default", name="Platform Delivery")
        self._boards[default.id] = default

    def create_board(self, name: str) -> KanbanBoard:
        board = KanbanBoard(id=str(uuid.uuid4()), name=name)
        self._boards[board.id] = board
        return board

    def get_board(self, board_id: str) -> KanbanBoard | None:
        return self._boards.get(board_id)

    def list_boards(self) -> list[KanbanBoard]:
        return list(self._boards.values())


_kanban: KanbanService | None = None


def get_kanban_service() -> KanbanService:
    global _kanban
    if _kanban is None:
        _kanban = KanbanService()
    return _kanban
