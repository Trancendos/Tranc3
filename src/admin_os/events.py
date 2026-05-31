"""Event viewer — The Observatory feed for Admin OS."""

from __future__ import annotations

from typing import Any

from src.observability.observatory import EventCategory, EventSeverity, get_observatory


def list_events(
    *,
    limit: int = 100,
    category: str | None = None,
    severity: str | None = None,
    actor: str | None = None,
    event_type: str | None = None,
) -> dict[str, Any]:
    obs = get_observatory()
    cat = None
    if category:
        try:
            cat = EventCategory(category)
        except ValueError:
            pass
    if actor or event_type:
        events = obs.search(actor=actor, event_type=event_type, limit=limit)
    else:
        events = obs.recent(limit=limit, category=cat)

    if severity:
        try:
            sev = EventSeverity(severity)
            events = [e for e in events if e.severity == sev]
        except ValueError:
            pass

    return {
        "source": "The Observatory",
        "count": len(events),
        "stats": obs.stats(),
        "events": [e.to_dict() for e in events],
    }
