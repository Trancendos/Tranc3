"""Utilities for assertions over FastAPI's nested router tree."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any


def iter_app_routes(routes: Iterable[Any]) -> Iterator[Any]:
    """Yield concrete routes, including endpoints held by included routers.

    FastAPI 0.141 retains included routers as nested route objects. Traversing
    their source router keeps structural assertions meaningful across both the
    old flattened and new nested representations.
    """

    for route in routes:
        included_router = getattr(route, "original_router", None)
        if included_router is not None:
            yield from iter_app_routes(included_router.routes)
        else:
            yield route
