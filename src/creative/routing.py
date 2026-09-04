"""Which Location answers a creative request, and what it actually delivers.

Why this exists
---------------
Ask the platform to make a game and, before this module, nothing decided
where the request went. The Spark's tool registry holds seventeen tools and
none of them is creative. Imaginarium — the omni-creative orchestrator — was
reachable only if a caller already knew its address and its project-type
vocabulary. So "the correct route" was not wrong; it did not exist.

This registry is the route table. It is deliberately *descriptive of the
estate as measured*, not of the estate as designed: every entry names the
worker, the endpoint, and what that endpoint really produces today. Three
statuses keep that honest:

``ROUTED``
    The endpoint exists and everything it depends on is a service in
    ``docker-compose.production.yml``.
``DEGRADED``
    The endpoint exists and answers, but a dependency is absent, so the
    result is a stub or a database row rather than the artefact asked for.
    A caller that treats DEGRADED as success reports work that did not
    happen.
``ABSENT``
    No endpoint anywhere in the estate serves this capability. Resolving to
    ABSENT is the point: the alternative is a near-miss route that succeeds
    loudly while doing something else.

The near-miss that motivated the design
---------------------------------------
"Edit this image" and "create an image" share their only noun. A resolver
that matched on nouns would send an edit to Sashas Photo Studio's generator,
which would return HTTP 200 and a brand-new unrelated picture. So a
capability is a candidate only when the request supplies **both** one of its
verbs and one of its nouns; `edit` is not among the generator's verbs, which
takes it out of the running rather than ranking it second.

Ambiguity is answered, not guessed
----------------------------------
When the best score ties across two or more *different* Locations and every
tied capability can actually be served, the resolution escalates to
Imaginarium: a brief spanning several creative disciplines is precisely what
an omni-creative orchestrator is for. A tie inside one Location, or a tie
touching an ABSENT capability, is refused instead — escalating the latter
would hide the gap behind an orchestrator that cannot fill it either.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

__all__ = [
    "CAPABILITIES",
    "Capability",
    "Resolution",
    "RouteStatus",
    "capability",
    "endpoint_for",
    "gaps",
    "resolve",
]


class RouteStatus(str, Enum):
    ROUTED = "routed"
    DEGRADED = "degraded"
    ABSENT = "absent"


# A phrase is worth more than the verb and noun it contains, so an explicit
# multi-word intent always outranks the single words that happen to overlap it.
PHRASE_WEIGHT = 10
VERB_WEIGHT = 3
NOUN_WEIGHT = 1

_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Capability:
    """One creative capability, and the truth about what serves it."""

    id: str
    location: str
    delivers: str
    status: RouteStatus
    verbs: tuple[str, ...]
    nouns: tuple[str, ...]
    method: str = ""
    path: str = ""
    url_env: str = ""
    default_url: str = ""
    # The worker directory, so scripts/check_creative_routes.py can verify the
    # path above against the module the Dockerfile CMD actually runs.
    worker_dir: str = ""
    phrases: tuple[str, ...] = ()
    gap: str = ""

    @property
    def servable(self) -> bool:
        """True when some endpoint answers this at all, degraded or not."""
        return self.status is not RouteStatus.ABSENT

    def score(self, tokens: frozenset[str], text: str) -> int:
        """Rank this capability against a request, or 0 if it is no candidate.

        A candidate needs one verb *and* one noun, or an explicit phrase.
        Returning 0 for everything else is what keeps an edit request out of
        the generator: sharing a noun is not sharing an intent.
        """
        phrase_hits = sum(1 for p in self.phrases if p in text)
        verb_hits = sum(1 for v in self.verbs if v in tokens)
        noun_hits = sum(1 for n in self.nouns if n in tokens)
        if not phrase_hits and not (verb_hits and noun_hits):
            return 0
        return phrase_hits * PHRASE_WEIGHT + verb_hits * VERB_WEIGHT + noun_hits * NOUN_WEIGHT

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "location": self.location,
            "status": self.status.value,
            "delivers": self.delivers,
            "endpoint": f"{self.method} {self.path}".strip(),
            "url_env": self.url_env,
            "default_url": self.default_url,
            "gap": self.gap,
        }


@dataclass
class Resolution:
    """The answer to "where does this request go?", including "nowhere"."""

    request: str
    capability: Optional[Capability] = None
    reason: str = ""
    candidates: list[Capability] = field(default_factory=list)

    @property
    def routed(self) -> bool:
        """True only when something can actually serve this.

        A named ABSENT capability is a *resolution* — it says which Location
        owns the gap — but it is not a route, and reporting it as one lets a
        caller treat unimplemented work as dispatchable. `capability` still
        carries the name; `routed` answers the different question.
        """
        return self.capability is not None and self.capability.servable

    def to_dict(self) -> dict[str, object]:
        return {
            "request": self.request,
            "reason": self.reason,
            "capability": self.capability.to_dict() if self.capability else None,
            "candidates": [c.to_dict() for c in self.candidates],
        }


# ── The route table ──────────────────────────────────────────────────────────
#
# Every status below was read off the worker source, its Dockerfile CMD and
# docker-compose.production.yml, not off the entity table's intentions.

CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        id="image.create",
        location="Sashas Photo Studio",
        delivers="An image, or an honest offline placeholder when no backend answers.",
        status=RouteStatus.DEGRADED,
        method="POST",
        path="/photo/generate",
        url_env="PHOTO_STUDIO_URL",
        default_url="http://sashas-photo-studio:8062",
        worker_dir="workers/sashas-photo-studio",
        verbs=("create", "generate", "make", "draw", "paint", "render", "produce"),
        nouns=("image", "picture", "photo", "photograph", "artwork", "illustration", "art"),
        phrases=("generate an image", "create a picture", "make me a picture"),
        gap=(
            "ComfyUI and AUTOMATIC1111 are not services in "
            "docker-compose.production.yml and the worker's defaults name "
            "localhost, which inside a container is the worker itself. Every "
            "request in the deployed stack therefore falls through to the "
            "offline placeholder branch."
        ),
    ),
    Capability(
        id="image.edit",
        location="Sashas Photo Studio",
        delivers="Nothing — no endpoint accepts an input image.",
        status=RouteStatus.ABSENT,
        verbs=("edit", "modify", "retouch", "alter", "adjust", "change", "inpaint", "recolour"),
        nouns=("image", "picture", "photo", "photograph", "artwork", "illustration"),
        phrases=("edit this image", "edit the picture", "remove the background"),
        gap=(
            "The worker exposes txt2img only. There is no img2img, no "
            "inpaint and no mask endpoint, so an edit has nowhere to send "
            "the image it is meant to edit."
        ),
    ),
    Capability(
        id="image.upscale",
        location="Sashas Photo Studio",
        delivers="HTTP 501.",
        status=RouteStatus.ABSENT,
        method="POST",
        path="/photo/upscale",
        url_env="PHOTO_STUDIO_URL",
        default_url="http://sashas-photo-studio:8062",
        worker_dir="workers/sashas-photo-studio",
        verbs=("upscale", "enlarge", "enhance"),
        nouns=("image", "picture", "photo", "resolution"),
        phrases=("upscale this image",),
        gap="The route is declared and returns 501 Not Implemented.",
    ),
    Capability(
        id="game.create",
        location="TranceFlow",
        delivers="A game record with engine, scenes, entities and assets.",
        status=RouteStatus.DEGRADED,
        method="POST",
        path="/tranceflow/projects",
        url_env="TRANCEFLOW_URL",
        default_url="http://tranceflow:8059",
        worker_dir="workers/tranceflow",
        verbs=("create", "build", "make", "develop", "start"),
        nouns=("game", "level", "gameplay"),
        phrases=("create a game", "build a game", "make a game"),
        gap=(
            "The deployed image runs main.py, which serves a generic project "
            "record at /tranceflow/projects. The games, scenes, entities and "
            "build_events API is in the sibling worker.py that no container "
            "runs. Even that one only writes rows: Godot is not a service in "
            "docker-compose.production.yml, so a game is designed here and "
            "built nowhere."
        ),
    ),
    Capability(
        id="game.asset.add",
        location="TranceFlow",
        delivers="Nothing — the deployed TranceFlow image serves no asset route.",
        status=RouteStatus.ABSENT,
        verbs=("add", "attach", "register", "upload"),
        nouns=("asset", "sprite", "texture"),
        gap=(
            "POST /assets exists in workers/tranceflow/worker.py. The "
            "Dockerfile runs main.py, which does not include it."
        ),
    ),
    Capability(
        id="model3d.create",
        location="TranceFlow",
        delivers="Nothing — the deployed TranceFlow image serves no scene route.",
        status=RouteStatus.ABSENT,
        verbs=("create", "model", "build", "make", "sculpt"),
        nouns=("model", "mesh", "scene", "3d"),
        phrases=("3d model", "three dimensional model"),
        gap=(
            "POST /scenes and POST /entities exist in "
            "workers/tranceflow/worker.py, which the Dockerfile does not run. "
            "The deployed /tranceflow/export is an export, not a create."
        ),
    ),
    Capability(
        id="video.create",
        location="TateKing",
        delivers="A video project, clips and a render job record.",
        status=RouteStatus.DEGRADED,
        method="POST",
        path="/video/create",
        url_env="TATEKING_URL",
        default_url="http://tateking:8061",
        worker_dir="workers/tateking",
        verbs=("create", "edit", "cut", "make", "produce", "render"),
        nouns=("video", "clip", "film", "footage", "movie", "trailer"),
        phrases=("edit this video", "make a video"),
        gap=(
            "The deployed main.py is a real FFmpeg implementation and shells "
            "out to the ffmpeg binary, which its image does not install — "
            "_ffmpeg_available() is the branch that decides. The project and "
            "clip API named in the entity table is in the un-deployed "
            "worker.py."
        ),
    ),
    Capability(
        id="design.create",
        location="Fabulousa",
        delivers="A Penpot design file.",
        status=RouteStatus.DEGRADED,
        method="POST",
        path="/fabulousa/projects",
        url_env="FABULOUSA_URL",
        default_url="http://fabulousa-service:8048",
        worker_dir="workers/fabulousa-service",
        verbs=("design", "create", "mock", "mockup", "wireframe", "prototype", "style"),
        nouns=("design", "mockup", "wireframe", "layout", "ui", "ux", "screen", "prototype"),
        phrases=("mock up", "design system", "style guide"),
        gap=(
            "Reachable but unauthenticated. PENPOT_URL now points at the "
            "penpot-frontend service in the same stack, so the address is no "
            "longer localhost; PENPOT_TOKEN is still unset, and without it "
            "the worker sends no Authorization header. A Penpot access token "
            "is a secret and belongs in The Void, not in compose."
        ),
    ),
    Capability(
        id="design.component",
        location="Fabulousa",
        delivers="Nothing — Fabulousa holds no components, widgets or tokens.",
        status=RouteStatus.ABSENT,
        verbs=("create", "build", "make", "supply", "provide", "generate"),
        nouns=("component", "widget", "token", "tokens", "button", "card", "block"),
        phrases=("building block", "design token", "component library", "widget library"),
        gap=(
            "The design system that exists — web/src/trancendos/tokens.ts, the "
            "components under web/src/components/ui/ and the Storybook stories "
            "— lives in Arcadia's front-end, not in the Location whose job "
            "description is styling, UX and UI. Fabulousa is a Penpot proxy "
            "with four endpoints and knows none of it."
        ),
    ),
    Capability(
        id="design.accessibility",
        location="Fabulousa",
        delivers="Nothing — no accessibility check runs anywhere in the estate.",
        status=RouteStatus.ABSENT,
        verbs=("check", "audit", "validate", "test", "review"),
        nouns=("accessibility", "aria", "wcag", "a11y", "contrast", "screenreader"),
        phrases=("accessibility check", "screen reader", "colour contrast"),
        gap=(
            "ARIA attributes are hand-written in web/src/components/ui/, and "
            "nothing verifies them: neither .github/workflows/ nor "
            ".forgejo/workflows/ runs axe, pa11y or Lighthouse."
        ),
    ),
    Capability(
        id="code.generate",
        location="The Lab",
        delivers="Generated source, reviewed and optionally executed in a sandbox.",
        status=RouteStatus.ROUTED,
        method="POST",
        path="/lab/generate",
        url_env="LAB_URL",
        default_url="http://the-lab:8055",
        worker_dir="workers/the-lab",
        verbs=("write", "generate", "implement", "code", "scaffold", "refactor"),
        nouns=("code", "function", "module", "script", "class", "api", "app", "application"),
        phrases=("write code", "build an app", "generate a module"),
    ),
    Capability(
        id="music.create",
        location="Warp Radio",
        delivers="Nothing — the deployed Warp Radio image serves no POST at all.",
        status=RouteStatus.ABSENT,
        verbs=("create", "make", "compile", "curate"),
        nouns=("playlist", "music", "soundtrack", "track", "audio", "song"),
        gap=(
            "main.py is 54 lines of read-only routes: /now-playing and "
            "/stations. The playlist and track API is in worker.py, which the "
            "Dockerfile does not run."
        ),
    ),
    Capability(
        id="creative.brief",
        location="Imaginarium",
        delivers="A project that fans out across the creative Locations.",
        status=RouteStatus.DEGRADED,
        method="POST",
        path="/create",
        url_env="IMAGINARIUM_URL",
        default_url="http://imaginarium:8064",
        worker_dir="workers/imaginarium",
        verbs=("create", "produce", "launch", "design", "build"),
        nouns=("campaign", "brand", "brief", "package", "masterpiece"),
        phrases=("brand package", "creative brief", "whole campaign"),
        gap=(
            "The fan-out reaches all six Locations, no longer discards a 200 "
            "it expected to be a 202, and — since this change put worker.py in "
            "the image — actually runs. What it fans out *to* is still "
            "degraded: no ComfyUI, no Godot, no ffmpeg binary, and three of "
            "the six Locations serve their create route only from an "
            "un-deployed worker.py. So a brief produces records and "
            "placeholders, and the project status says partial or failed "
            "rather than completed when a leg does not answer."
        ),
    ),
)

_BY_ID = {c.id: c for c in CAPABILITIES}

# The orchestrator a multi-discipline tie escalates to. Looked up rather than
# hardcoded at the call site so a rename cannot leave a dangling reference.
_ORCHESTRATOR = _BY_ID["creative.brief"]


def capability(capability_id: str) -> Optional[Capability]:
    """Return one capability by id, or None."""
    return _BY_ID.get(capability_id)


def gaps() -> list[Capability]:
    """Every capability that cannot deliver what its name promises."""
    return [c for c in CAPABILITIES if c.status is not RouteStatus.ROUTED]


def endpoint_for(cap: Capability) -> Optional[str]:
    """The URL this capability's endpoint is reachable at, or None.

    Reads the environment the same way the worker that calls it would, so a
    deployment that overrides the address gets the overridden answer rather
    than the compose default this table was written against.
    """
    if not cap.path:
        return None
    base = (os.getenv(cap.url_env) or cap.default_url).rstrip("/")
    return f"{base}{cap.path}"


def _tokenise(text: str) -> frozenset[str]:
    return frozenset(_TOKEN.findall(text.lower()))


def resolve(request: str) -> Resolution:
    """Route a request in words to the Location that answers it.

    Never guesses. An unmatched request, an ambiguous one, and one whose
    capability is ABSENT are three different answers, and each says so.
    """
    text = request.lower()
    tokens = _tokenise(request)

    scored = [(cap.score(tokens, text), cap) for cap in CAPABILITIES]
    candidates = [(s, c) for s, c in scored if s > 0]
    if not candidates:
        return Resolution(request=request, reason="no capability matches this request")

    best = max(s for s, _ in candidates)
    winners = [c for s, c in candidates if s == best]

    if len(winners) == 1:
        cap = winners[0]
        if cap.status is RouteStatus.ABSENT:
            return Resolution(
                request=request,
                capability=cap,
                reason=f"{cap.location} owns this capability and does not implement it",
                candidates=winners,
            )
        return Resolution(
            request=request,
            capability=cap,
            reason=f"routed to {cap.location}",
            candidates=winners,
        )

    absent = [c for c in winners if not c.servable]
    if absent:
        # Escalating here would put an orchestrator in front of a capability
        # nobody implements, which reads as progress and is not.
        names = ", ".join(sorted(c.id for c in absent))
        return Resolution(
            request=request,
            reason=f"ambiguous, and these tied candidates are unimplemented: {names}",
            candidates=winners,
        )

    if len({c.location for c in winners}) > 1:
        return Resolution(
            request=request,
            capability=_ORCHESTRATOR,
            reason=(
                "spans "
                + ", ".join(sorted({c.location for c in winners}))
                + f" — escalated to {_ORCHESTRATOR.location}"
            ),
            candidates=winners,
        )

    return Resolution(
        request=request,
        reason=(
            f"ambiguous within {winners[0].location}: " + ", ".join(sorted(c.id for c in winners))
        ),
        candidates=winners,
    )
