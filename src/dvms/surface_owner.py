"""Which Location owns this dependency surface?

WHY THIS EXISTS

The vulnerability census reports findings against a *manifest path* --
`workers/the-studio/requirements.txt`. Every other subsystem on the platform
reasons about *Locations* -- The Studio, Cryptex, The Lab. Nothing joined the
two, so a census finding could say what was wrong and not who answers for it,
and the intended flow (Cryptex assesses -> priority Requests/Changes -> The Lab
remediates -> The Observatory records -> The Basement learns) had no first step:
Cryptex could not tell The Lab whose problem it was.

An earlier pass measured the DVMS/CMDB overlap as zero and that number was
right about the data and wrong about the architecture. `src/cmdb/identity.py`
resolves a service across ServiceID, PID, Location name and port; the census
keys everything by manifest path, which is none of those. The design was never
absent -- Cryptex and The Lab are Locations in `PLATFORM_ENTITIES.md` and
`src/entities/platform.py`, exactly as the owner described. It was UNWIRED,
which is this engagement's recurring defect: a control that exists, runs, and
reports, but is never actually invoked.

HOW A SURFACE IS RESOLVED

Three ladders, tried in order, each one derived from something already
authoritative rather than invented here:

  1. `LocationEntity.worker_path` -- every one of the 43 Locations declares its
     primary directory. A surface inside that tree belongs to that Location.
  2. The compose port. `docker-compose.production.yml` is the deployment truth
     for which port a worker serves, and `get_entity_for_port` maps a port to
     its Location. This catches a worker whose directory name does not match
     the Location's declared path.
  3. `DECLARED_OWNERS` below -- surfaces that neither ladder can reach, each
     with a written reason. A Location with two directories (The Lab is
     `workers/the-lab/` AND `workers/lab-service/`) is only visible here.

WHAT IT REFUSES TO DO

It does not guess. A surface that no ladder resolves comes back as
`unmapped`, and `scripts/check_surface_ownership.py` fails on one, because a
finding routed to the wrong Location is worse than a finding routed nowhere:
the wrong Location closes it as not-mine and the right one never hears about
it.

`shared` is a real answer, not a failure. Fifteen or so of the estate's
services are cross-cutting infrastructure -- the API gateway, the rate limiter,
the AI-framework bridges -- and belong to no single Location. `identity.py`
already takes this position and returns `pid = None` for them rather than
putting a wrong owner on every incident they raise. A shared surface still
needs somebody to ACT on it, so it carries a steward, and the steward for
dependency remediation is The Lab: that is what The Lab is for.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional, Tuple

from src.entities.platform import PLATFORM_ENTITIES, get_entity_for_port

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMPOSE = os.path.join(REPO_ROOT, "docker-compose.production.yml")

# The Location that acts on a finding nobody else owns. Not a fallback owner --
# a shared surface genuinely has no single Location -- but the Location whose
# job description is code remediation, so the Request/Change has somewhere to
# go instead of expiring in a report.
DEFAULT_STEWARD = "The Lab"


@dataclass(frozen=True)
class SurfaceOwner:
    """Who answers for one dependency surface.

    `kind` is `location`, `shared` or `unmapped`, and they are not degrees of
    the same thing:

      location  -- a named Location owns it; `location` is set.
      shared    -- cross-cutting infrastructure with no single Location.
                   `location` is None and `steward` says who acts.
      unmapped  -- nobody has said. This is a defect, not a category.
    """

    surface: str
    kind: str
    location: Optional[str] = None
    steward: str = DEFAULT_STEWARD
    reason: str = ""
    resolved_by: str = ""

    @property
    def is_owned(self) -> bool:
        return self.kind == "location"

    @property
    def responsible(self) -> Optional[str]:
        """The Location that acts on a finding here — owner, or steward.

        None for an `unmapped` surface, and that is the point: the steward
        default would otherwise make an unowned surface indistinguishable from
        a stewarded one in any roll-up built on this, quietly reporting a
        routing gap as routed.
        """
        return self.location or self.steward or None


# Surfaces neither ladder reaches. Every entry is a path PREFIX and carries the
# reason it is here, because a mapping without a reason is indistinguishable
# from a guess six months later.
#
# Keys are matched longest-first, so a more specific prefix always wins.
DECLARED_OWNERS: Dict[str, Tuple[Optional[str], str]] = {
    # ── a Location's second (or third) directory ──────────────────────────
    "workers/lab-service": ("The Lab", "The Lab's extended service layer (port 8066)"),
    "workers/chaos-party": ("The Chaos Party", "the testing platform's standalone worker"),
    "workers/library-service": ("The Library", "the knowledge base's standalone worker"),
    "workers/observatory": ("The Observatory", "the audit trail's standalone worker"),
    "workers/turings-hub-service": ("Turing's Hub", "the personality creator's worker"),
    "workers/skills-benchmark-service": (
        "Turing's Hub",
        "benchmarks the personalities Turing's Hub creates",
    ),
    "workers/vault-service": ("The Void", "the self-hosted vault replacing the CF worker"),
    "cloudflare/infinity-void": ("The Void", "the CF worker the vault is migrating off"),
    "workers/workflow-engine-service": ("The Digital Grid", "the Grid's execution engine"),
    "workers/hive-service": ("The HIVE", "the HIVE's task queue and agent coordination"),
    "workers/ledger-service": ("Royal Bank of Arcadia", "the bank's ledger"),
    "workers/infinity-portal-service": ("Infinity", "Infinity Portal — the front entrance"),
    "workers/infinity-one-service": ("Infinity", "Infinity-One — the single identity layer"),
    "workers/infinity-admin-service": ("Infinity", "Infinity Admin — Admin OS"),
    "workers/infinity-shards-service": ("Infinity", "Infinity Shards — entity power-ups"),
    "workers/infinity-bridge-service": ("Infinity", "Infinity Bridge — human traffic transfer"),
    "workers/tranc3-ai": ("Luminous", "the AI edge proxy in front of the brain"),
    "cloudflare/tranc3-ai": ("Luminous", "the CF worker the AI proxy is migrating off"),
    "workers/model-router-service": ("Luminous", "routes between the AI models Luminous serves"),
    "workers/blender-worker": ("TranceFlow", "Blender render worker for the 3D studio"),
    "workers/triposr-worker": ("TranceFlow", "image-to-3D worker for the 3D studio"),
    "workers/ffmpeg-worker": ("TateKing", "FFmpeg worker behind video creation"),
    # ── reachable through compose, declared here so they do not DEPEND on it ──
    # Each of these resolved only through the compose-port ladder, which goes
    # dark when PyYAML is absent -- and it was absent in a reviewer's checkout,
    # where the gate reported 58 owned and 10 UNOWNED and failed. The ladder is
    # an optimisation, not a dependency; the port that established each mapping
    # is recorded so the claim can be re-checked without running anything.
    "workers/analytics-service": ("The Observatory", "compose port 8016 — metrics store"),
    "workers/audit-service": ("The Observatory", "compose port 8025 — the audit trail"),
    "workers/cache-service": ("The HIVE", "compose port 8023 — the distributed cache"),
    "workers/cdn-service": ("The Studio", "compose port 8028 — static asset delivery"),
    "workers/email-service": ("Arcadia", "compose port 8018 — Arcadia's email hub"),
    "workers/notifications": ("Arcadia", "compose port 8008 — the notification service"),
    "workers/products-service": ("Arcadian Exchange", "compose port 8011 — products catalogue"),
    "workers/sms-service": ("The Nexus", "compose port 8019 — the SMS gateway"),
    "workers/storage-service": ("DocUtari", "compose port 8020 — IPFS and blob storage"),
    "workers/users-service": ("Infinity", "compose port 8006 — user management"),
    # ── cross-cutting: no single Location, steward acts ───────────────────
    "requirements.txt": (None, "the FastAPI backend every in-process router shares"),
    "requirements-ai.txt": (None, "shared AI dependencies for the backend"),
    "requirements-security.txt": (None, "shared security tooling for the backend"),
    "requirements-test.txt": (None, "shared test dependencies for the backend"),
    "tranc3-bots": (None, "the 12 bot types, used by every Location that spawns one"),
    "tranc3-ts": (None, "shared TypeScript tooling"),
    "workers/api-gateway": (None, "the gateway in front of every worker"),
    "workers/gateway-service": (None, "the gateway in front of every worker"),
    "cloudflare/trancendos-api-gateway": (None, "the CF gateway Traefik is replacing"),
    "workers/backup-service": (None, "backs up every worker's data, not one Location's"),
    "workers/config-service": (None, "central configuration for every worker"),
    "workers/geo-service": (None, "geographic routing for every worker"),
    "workers/rate-limit-service": (None, "the token bucket in front of every worker"),
    # Unowned from 2026-09-05 until this entry: The Library's `worker_path`
    # used to point here, so the Location ladder resolved it by accident.
    # Correcting that to `workers/library-service/` (its real code) left this
    # surface with nobody, which is the right outcome to record rather than
    # re-attach: `src/event_bus/wiring.py` indexes BOTH Library articles and
    # Think Tank inference results into it, and its own worker docstring
    # describes "multiple named indices" any Location may register. It is a
    # generic FTS5 index server, not one Location's search.
    "workers/search-service": (None, "compose port 8017 — the estate's shared FTS5 index"),
    "workers/health-aggregator": (None, "rolls up health across the whole estate"),
    "workers/topology-service": (None, "the service topology graph of the whole estate"),
    "workers/optional-services-health": (None, "health probes for optional services"),
    "workers/langchain-integration-service": (None, "an AI framework bridge, not a Location"),
    "workers/llamaindex-service": (None, "an AI framework bridge, not a Location"),
    "workers/haystack-service": (None, "an AI framework bridge, not a Location"),
    "workers/dspy-service": (None, "an AI framework bridge, not a Location"),
    "workers/litellm-service": (None, "the zero-cost provider proxy, used estate-wide"),
    "workers/mlflow-service": (None, "experiment tracking, used estate-wide"),
    "workers/gbrain-bridge": (None, "an AI bridge, not a Location"),
    "workers/deepagents-orchestrator-service": (None, "deep agent orchestration, estate-wide"),
    "workers/sentinel-station-service": (None, "a platform-wide guardian, not one of the 43"),
    "workers/swarm-coordinator-service": (None, "agent swarm management, estate-wide"),
    "workers/dimensional-nexus-service": (None, "multi-dimensional data routing, estate-wide"),
    # ── Go and Rust, unscanned until 2026-09-04 ───────────────────────────
    # These twelve surfaces were invisible to the census, so nothing had ever
    # needed to say who owns them. `workers/nexus-ws-rs` resolves through the
    # compose port on its own; it is declared anyway, for the same reason the
    # block above is — the compose ladder goes dark when PyYAML is absent.
    "workers/vault-service-rs": ("The Void", "the Rust vault beside workers/vault-service"),
    "workers/nexus-ws-rs": ("The Nexus", "compose port 8004 — the Rust WebSocket hub"),
    "rust_extensions/tranc3_snn": (
        "Turing's Hub",
        "INT8 SNN tensor ops for personality signal extraction, behind src/personality/snn_qat.py",
    ),
    "rust_extensions/tranc3_crypto": (
        None,
        "the AES-256-GCM primitive behind src/security/rust_crypto.py — used by "
        "anything that encrypts, not by one Location",
    ),
    "workers/rate-limit-service-rs": (
        None,
        "the Rust token bucket beside workers/rate-limit-service, in front of every worker",
    ),
    "src/nanoservices": (
        None,
        "the nanoservice layer (port 8001) — the NSA broker, its clients and the "
        "DNF orchestrator serve every Location, not one",
    ),
    "aeonmind": (
        None,
        "a generic polyglot agent-framework specification, explicitly NOT one of "
        "the 43 and not deployed — only its Python bridge is live, so its Go, "
        "Rust and WASM trees answer to no Location and The Lab acts on findings",
    ),
    # The npm root. Matched exactly, never as a prefix — see _declared_match.
    ".": (None, "the repository root's own package.json"),
}


@lru_cache(maxsize=1)
def _entity_paths() -> Tuple[Tuple[str, str], ...]:
    """(`worker_path`, Location) for all 43, longest path first."""
    pairs = [
        (entity.worker_path.rstrip("/"), entity.location)
        for entity in PLATFORM_ENTITIES.values()
        if entity.worker_path
    ]
    return tuple(sorted(pairs, key=lambda pair: (-len(pair[0]), pair[0])))


# Why the compose ladder is unavailable, when it is. Silence here was a real
# defect: `_compose_ports()` swallowed a missing PyYAML and returned {}, so in a
# checkout without it the gate reported ten surfaces as UNOWNED and failed for a
# reason that had nothing to do with ownership. Every one of those ten is now
# declared above, so this is diagnostic rather than load-bearing -- but a ladder
# that has gone dark must say so.
_COMPOSE_UNAVAILABLE: list = []


def _note_compose_unavailable(reason: str) -> None:
    if reason not in _COMPOSE_UNAVAILABLE:
        _COMPOSE_UNAVAILABLE.append(reason)


def compose_ladder_status() -> list:
    """Reasons the compose ladder could not be consulted; empty when it worked."""
    _compose_ports()  # ensure the attempt has been made
    return list(_COMPOSE_UNAVAILABLE)


def _compose_port(cfg: dict) -> Optional[int]:
    """The port a compose service actually serves on.

    Three places, in the order the deployment honours them: an explicit `PORT`
    (or `<NAME>_PORT`) in the environment, Traefik's loadbalancer label, then a
    published port. `EXPOSE` in a Dockerfile is deliberately not consulted --
    it is cosmetic, and the app reads its port env at runtime.
    """
    env = cfg.get("environment") or {}
    if isinstance(env, list):
        env = {item.split("=")[0]: item.split("=", 1)[1] for item in env if "=" in item}
    for key, value in env.items():
        if key == "PORT" or key.endswith("_PORT"):
            try:
                return int(str(value))
            except (TypeError, ValueError):
                continue
    labels = cfg.get("labels") or []
    if isinstance(labels, dict):
        labels = [f"{k}={v}" for k, v in labels.items()]
    for label in labels:
        match = re.search(r"loadbalancer\.server\.port=(\d+)", str(label))
        if match:
            return int(match.group(1))
    for published in cfg.get("ports") or []:
        match = re.match(r'^"?(\d+):', str(published))
        if match:
            return int(match.group(1))
    return None


@lru_cache(maxsize=1)
def _compose_ports() -> Dict[str, int]:
    """{compose service name: port}. Empty when compose cannot be read.

    An unreadable compose file loses ladder 2 and nothing else: ladders 1 and 3
    still resolve, and anything that depended on 2 alone surfaces as `unmapped`
    for the ownership gate to report. It must not raise -- the census calls this
    while classifying findings, and a crash there would turn a reportable gap
    into a failed scan.
    """
    try:
        import yaml
    except ModuleNotFoundError:
        _note_compose_unavailable("PyYAML is not installed")
        return {}
    try:
        with open(COMPOSE, encoding="utf-8") as handle:
            document = yaml.safe_load(handle)
    except OSError as exc:
        _note_compose_unavailable(f"{COMPOSE} could not be read ({type(exc).__name__})")
        return {}
    except yaml.YAMLError as exc:
        # `yaml.YAMLError`, not `ValueError`: a malformed compose file raises the
        # former, which the old clause did not catch, so ownership resolution
        # crashed the census instead of degrading.
        _note_compose_unavailable(f"{COMPOSE} is not valid YAML ({type(exc).__name__})")
        return {}
    if not isinstance(document, dict):
        return {}
    services = document.get("services")
    if not isinstance(services, dict):
        return {}
    out: Dict[str, int] = {}
    for name, cfg in services.items():
        if not isinstance(cfg, dict):
            continue
        port = _compose_port(cfg)
        if port is not None:
            out[str(name)] = port
    return out


def _normalise(surface: str) -> str:
    """A census surface as a repo-relative POSIX path with no trailing slash."""
    return surface.replace("\\", "/").strip("/") or "."


def _declared_match(surface: str) -> Optional[Tuple[str, Tuple[Optional[str], str]]]:
    """The longest DECLARED_OWNERS prefix covering `surface`.

    `.` is matched only as an exact surface. As a prefix it would cover the
    entire repository and quietly claim every unmapped path, which is precisely
    the guessing this module refuses to do.
    """
    best: Optional[Tuple[str, Tuple[Optional[str], str]]] = None
    # "Longest" is tracked as its own value rather than re-read off `best`.
    # `len(best[0])` behind an `or best is None` guard is correct but reads as
    # a subscript of an Optional, and static analysis says so; naming the
    # length says what the comparison is for in the same breath.
    longest = -1
    for prefix, value in DECLARED_OWNERS.items():
        if prefix == ".":
            if surface == ".":
                return prefix, value
            continue
        if surface == prefix or surface.startswith(prefix + "/"):
            if len(prefix) > longest:
                best = (prefix, value)
                longest = len(prefix)
    return best


def resolve_surface(surface: str) -> SurfaceOwner:
    """Who answers for `surface`. Never guesses; never raises."""
    path = _normalise(surface)

    for worker_path, location in _entity_paths():
        if path == worker_path or path.startswith(worker_path + "/"):
            return SurfaceOwner(
                surface=path,
                kind="location",
                location=location,
                reason=f"inside {location}'s declared worker_path {worker_path!r}",
                resolved_by="worker_path",
            )

    parts = path.split("/")
    if len(parts) > 1 and parts[0] == "workers":
        port = _compose_ports().get(parts[1])
        entity = get_entity_for_port(port) if port is not None else None
        if entity is not None:
            return SurfaceOwner(
                surface=path,
                kind="location",
                location=entity.location,
                reason=f"compose routes {parts[1]!r} to port {port}, which is {entity.location}",
                resolved_by="compose_port",
            )

    declared = _declared_match(path)
    if declared is not None:
        prefix, (location, reason) = declared
        if location is not None:
            return SurfaceOwner(
                surface=path,
                kind="location",
                location=location,
                reason=reason,
                resolved_by=f"declared:{prefix}",
            )
        return SurfaceOwner(
            surface=path,
            kind="shared",
            location=None,
            reason=reason,
            resolved_by=f"declared:{prefix}",
        )

    return SurfaceOwner(
        surface=path,
        kind="unmapped",
        location=None,
        # No steward either. Handing an unowned surface to the default steward
        # would make the gap invisible to everything downstream, which is the
        # opposite of what an unmapped result is for.
        steward="",
        reason=(
            "no Location declares this path, no compose port resolves it, and "
            "DECLARED_OWNERS does not name it"
        ),
        resolved_by="",
    )


def declared_surfaces(surfaces) -> Dict[str, SurfaceOwner]:
    """Resolve many surfaces at once, keyed by the normalised path."""
    return {owner.surface: owner for owner in (resolve_surface(s) for s in surfaces)}


def unresolved_surfaces(surfaces) -> list:
    """Just the ones nobody has claimed — what the ownership gate reports."""
    return [owner for owner in declared_surfaces(surfaces).values() if owner.kind == "unmapped"]


def reset_cache() -> None:
    """Drop the compose/entity caches. For tests that rewrite either source."""
    _entity_paths.cache_clear()
    _compose_ports.cache_clear()
    _COMPOSE_UNAVAILABLE.clear()
