"""Every datastore in the estate, discovered rather than declared.

The owner is planning per-AI and per-Location databases, and has been advised to
move off SQLite. Both are decisions about a fleet nobody had counted, so this
module counts it: it walks the repository for datastore usage and returns one
record per store, with the engine, the owning Location where that can be
resolved, and the evidence it was found by.

Discovered, not declared, for the reason this estate keeps rediscovering: a
hand-maintained inventory describes the platform someone remembered. Adding a
`sqlite3.connect("data/whatever.db")` to a worker is a one-line change nobody
would think to record, and it is exactly the change that must not go missing
from a CMDB.

A datastore found here becomes a Configuration Item via `as_ci()`. That is the
link the owner asked for: the fleet is not a list in a document, it is CIs with
owners, engines and jurisdictions, which is what makes questions like "what does
a Postgres migration touch" and "who backs this up" answerable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

REPO = Path(__file__).resolve().parents[2]

SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "archive"}

#: Engine detection. Ordered: the first pattern a file matches names its engine,
#: so a module using both sqlite3 and psycopg is reported once per store path
#: rather than once per import.
ENGINE_PATTERNS: List[tuple[str, re.Pattern[str]]] = [
    ("postgresql", re.compile(r"\bpsycopg|postgresql://|asyncpg\b")),
    ("mysql", re.compile(r"\bpymysql|mysql://|mysqlclient|aiomysql\b")),
    ("duckdb", re.compile(r"\bduckdb\b")),
    ("redis", re.compile(r"\bredis\.|rediss?://|aioredis\b")),
    ("sqlite", re.compile(r"\bsqlite3\.connect|sqlite:///")),
]

#: Paths that look like a database file. Captures the literal so the store can be
#: named and de-duplicated across the modules that open it.
DB_PATH_RE = re.compile(r'["\']([\w./-]*\.(?:db|sqlite3?|duckdb))["\']')

#: Engines whose data lives outside the repository and is reached over a URL.
NETWORKED = {"postgresql", "mysql", "redis"}


@dataclass
class Datastore:
    """One datastore, as found."""

    name: str
    engine: str
    #: Repo-relative path for a file-backed store; an env-var name or URL scheme
    #: for a networked one. When several literals name the same store, this is
    #: the most specific of them -- see `record_locator`.
    locator: str
    #: Files observed opening it.
    evidence: List[str] = field(default_factory=list)
    #: Owning Location, where the evidence path maps to one. When more than one
    #: Location opens the store, this is the first alphabetically and every
    #: claimant is recorded -- see `record_location`.
    location: str = ""
    #: True when the store lives in a file inside a container's writable layer or
    #: a mounted volume, which is what makes its backup story a real question.
    file_backed: bool = True
    #: True when every file opening this store is a test. Fixture databases
    #: (`a.db`, `anywhere.db`, `tmp_path / "x.db"`) are real SQLite usage and
    #: real noise in a migration plan -- counted separately rather than dropped,
    #: because dropping them silently is how an inventory starts under-reporting.
    test_only: bool = False

    #: Disambiguator for stores whose name is not unique. A networked store is
    #: named after the module that reaches it (`redis@pool`), and this repository
    #: has several modules called `pool.py` -- so three distinct Redis clients
    #: collapsed onto one CI id until the qualifier was added. A CMDB that merges
    #: two Configuration Items because their names collide is worse than one that
    #: misses them: it reports full coverage of an estate it has under-counted.
    qualifier: str = ""

    #: Every path literal observed opening this store. Stores are identified by
    #: basename, so `/data/hive.db` and `hive.db` merge onto one CI -- which is
    #: what makes the fleet countable, and is also the merge most likely to be
    #: wrong. Recording both is what lets a reader check it; reporting whichever
    #: one the directory walk reached first is what this field replaced.
    locators: set[str] = field(default_factory=set)

    #: Every Location observed opening this store. One store claimed by two
    #: Locations is a real finding for a platform planning per-Location
    #: databases, not a tie to be broken quietly.
    locations: set[str] = field(default_factory=set)

    def record_location(self, name: str) -> None:
        """Note a Location that opens this store, keeping `location` stable.

        The previous rule was "first claimant wins" (`if not store.location`),
        and the first claimant was whichever file `Path.rglob` reached first --
        so `studio.db`, which both Sashas Photo Studio and The Studio open,
        changed jurisdiction between two runs of the same generator.
        """
        if not name:
            return
        self.locations.add(name)
        self.location = sorted(self.locations)[0]

    def record_locator(self, literal: str) -> None:
        """Note a literal this store was reached by, keeping `locator` stable.

        The chosen locator is the most specific literal -- longest, then
        lexicographic -- because `/data/ai_governance.db` says where the store
        lives and `ai_governance.db` says only what it is called. Both halves of
        that rule matter: without it the winner was decided by `Path.rglob`
        order, so the same tree produced different registers on different
        filesystems and `--check` reported STALE at a reader who had changed
        nothing.
        """
        self.locators.add(literal)
        self.locator = max(sorted(self.locators), key=len)

    @property
    def ci_id(self) -> str:
        """Stable CI identifier: CI-DS-<engine>-<name>[-<qualifier>]."""
        parts = [self.name] + ([self.qualifier] if self.qualifier else [])
        slug = re.sub(r"[^a-z0-9]+", "-", "-".join(parts).lower()).strip("-")
        return f"CI-DS-{self.engine}-{slug}"

    def as_ci(self) -> Dict[str, object]:
        """Configuration Item record for this datastore.

        `ci_class` follows the CMDB's existing vocabulary rather than inventing a
        parallel one; `jurisdiction` is the owning Location, which is the field
        that makes "who is accountable for this store" answerable at all.
        """
        record: Dict[str, object] = {
            "ci_id": self.ci_id,
            "ci_class": "Datastore",
            "name": self.name,
            "engine": self.engine,
            "locator": self.locator,
            "file_backed": self.file_backed,
            "jurisdiction": self.location or "_unrouted_",
            "test_only": self.test_only,
            "evidence": sorted(self.evidence),
            "evidence_count": len(self.evidence),
        }
        if len(self.locations) > 1:
            record["jurisdictions"] = sorted(self.locations)
        if len(self.locators) > 1:
            # Only when there is something to disclose, so the common row keeps
            # its shape and a merged store is visible at a glance.
            record["locators"] = sorted(self.locators)
        return record


def _candidate_files() -> Iterable[Path]:
    for path in REPO.rglob("*.py"):
        if any(part in SKIP_PARTS for part in path.relative_to(REPO).parts):
            continue
        yield path


def _location_for(rel_path: str) -> str:
    """Resolve a source path to the Location that owns it, via PLATFORM_ENTITIES."""
    try:
        from src.entities.platform import PLATFORM_ENTITIES
    except Exception:  # pragma: no cover - defensive
        return ""
    best, best_len = "", 0
    for name, entity in PLATFORM_ENTITIES.items():
        worker_path = (entity.worker_path or "").rstrip("/")
        if worker_path and rel_path.startswith(worker_path) and len(worker_path) > best_len:
            best, best_len = name, len(worker_path)
    return best


def _engine_for(text: str) -> Optional[str]:
    for engine, pattern in ENGINE_PATTERNS:
        if pattern.search(text):
            return engine
    return None


def discover() -> List[Datastore]:
    """Walk the repository and return one Datastore per distinct store."""
    stores: Dict[str, Datastore] = {}

    for path in _candidate_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        engine = _engine_for(text)
        if engine is None:
            continue
        rel = path.relative_to(REPO).as_posix()
        location = _location_for(rel)

        found_paths = set(DB_PATH_RE.findall(text))
        if found_paths:
            for literal in sorted(found_paths):
                name = Path(literal).name
                key = f"{engine}:{name}"
                store = stores.setdefault(
                    key,
                    Datastore(name=name, engine=engine, locator=literal, file_backed=True),
                )
                store.record_locator(literal)
                store.record_location(location)
                store.evidence.append(rel)
        elif engine in NETWORKED:
            # A networked store with no file literal — named by its engine and the
            # module that reaches it, because the connection string is an env var
            # resolved at runtime and is not knowable from source.
            key = f"{engine}:{rel}"
            store = stores.setdefault(
                key,
                Datastore(
                    name=f"{engine}@{Path(rel).stem}",
                    engine=engine,
                    locator=f"env://{engine.upper()}_URL",
                    file_backed=False,
                    # The module path, so two `pool.py` files are two CIs.
                    qualifier=rel.replace("/", "-").removesuffix(".py"),
                ),
            )
            store.record_location(location)
            store.evidence.append(rel)

    for store in stores.values():
        store.test_only = all(
            e.startswith("tests/") or "/tests/" in e or e.startswith("test_")
            for e in store.evidence
        )
    # Sorted by CI id, which is the identity the register keys on. The previous
    # key was (engine, name), which is NOT unique: `redis@pool` and
    # `redis@sentinel_station` each name two distinct modules, so two pairs of
    # CIs tied and Python's stable sort settled them by `rglob` order. The
    # register is the CMDB -- two Configuration Items swapping places between two
    # runs of the same generator is the register describing the filesystem it was
    # built on rather than the estate it claims to describe.
    return sorted(stores.values(), key=lambda s: s.ci_id)


def production_stores() -> List[Datastore]:
    """Stores something other than a test opens. The migration surface."""
    return [s for s in discover() if not s.test_only]


def summary() -> Dict[str, object]:
    stores = discover()
    live = [s for s in stores if not s.test_only]
    by_engine: Dict[str, int] = {}
    for store in live:
        by_engine[store.engine] = by_engine.get(store.engine, 0) + 1
    unrouted = [s for s in live if not s.location]
    return {
        "total": len(stores),
        "production": len(live),
        "test_only": len(stores) - len(live),
        "by_engine": dict(sorted(by_engine.items(), key=lambda kv: -kv[1])),
        "file_backed": sum(1 for s in live if s.file_backed),
        "unrouted": len(unrouted),
        "unrouted_names": sorted(s.name for s in unrouted)[:15],
    }
