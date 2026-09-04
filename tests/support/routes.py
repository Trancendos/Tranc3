"""Read an application's real mounted path surface.

Why this exists
---------------
FastAPI 0.141 changed `include_router`: instead of copying each sub-route
into `app.routes`, it appends a single lazy `_IncludedRouter` marker and
resolves the real routes at request time. Routing is unaffected — the
endpoints answer exactly as before — but `{r.path for r in app.routes}` stops
seeing anything a router contributed.

Three tests asserted mounts that way and started failing on an application
that was working: `/exchange/inventory` answers 200 while
`app.routes` reports the empty set. The tests were reading a FastAPI
internal, and the internal moved.

`mounted_paths` reads the OpenAPI schema instead — the public, supported
description of what the application serves — with a walk of the route objects
as a fallback for the routes OpenAPI omits (WebSockets and mounts).
"""

from __future__ import annotations

from typing import Any


def mounted_routes(app: Any) -> list[Any]:
    """Every route object the application serves, included routers walked.

    The same 0.141 change that hid included paths also hides the route
    *objects* — their dependants, their endpoints. A scan over `app.routes`
    still runs and still reports, and now looks at only the handful of routes
    declared directly on the app: a control that inspects nothing while
    appearing to inspect everything. `_IncludedRouter` keeps the router it
    stands for on `original_router`, so the real objects are one hop away.
    """
    found: list[Any] = []
    seen: set[int] = set()

    def walk(routes: Any) -> None:
        for route in routes or []:
            if id(route) in seen:
                continue
            seen.add(id(route))
            original = getattr(route, "original_router", None)
            if original is not None:
                walk(getattr(original, "routes", []))
                continue
            found.append(route)
            nested = getattr(route, "routes", None)
            if nested and not hasattr(route, "endpoint"):
                walk(nested)

    walk(getattr(app, "routes", []))
    return found


def mounted_paths(app: Any) -> set[str]:
    """Every path the application actually serves."""
    paths: set[str] = set(app.openapi().get("paths", {}))
    # WebSocket routes and Mounts carry no OpenAPI entry, so add what the
    # route objects still expose directly.
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", None)
        if isinstance(path, str) and path:
            paths.add(path)
    return paths
