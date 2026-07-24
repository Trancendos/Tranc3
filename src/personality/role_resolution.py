# src/personality/role_resolution.py
# Turing's Hub — Role Registry -> Personality Matrix resolution.
#
# The Role Assignment Registry (src/roles/registry.py) tracks which AI
# currently holds each Location's Job Description; the Personality Matrix
# (src/personality/matrix.py) loads a JSON profile per AI. Nothing wired
# these two together before — callers had to pass a personality id string by
# hand, which goes stale the moment an operator reassigns a role via
# POST /roles/{location}/assign. This module closes that gap.

from __future__ import annotations

from typing import Optional

# Maps each Location's `assigned_ai` display name (src/entities/platform.py's
# `lead_ai`, and the Role Registry's seed value for it) to a
# src/personality/profiles/*.json profile id. Deliberately an explicit table,
# not a slug-guessing function: several display names don't slugify to their
# profile id (parenthetical titles, "&", casing) and guessing wrong would
# silently resolve to the wrong persona instead of falling back cleanly.
AI_NAME_TO_PROFILE_ID: dict[str, Optional[str]] = {
    "Nexus-Prime": "the-nexus-ai",
    "The Queen": "the-queen",
    "Lilli SC": "lilli-sc",
    "Cornelius MacIntyre": "cornelius-macintyre",
    "Tristuran": "tristuran",
    "Voxx": "voxx",
    "Madam Krystal": "madam-krystal",
    "Junior Cesar": "junior-cesar",
    # TateKing's seed lead_ai is "Benji Tate" (primary of two, per
    # trance_one/platform_manifest.py's lead_ais split) — the shared
    # benji-tate-sam-king profile still voices both. Sam King is a valid
    # assign_ai() target too (a live co-lead, not just a lead_ais entry),
    # so he needs his own key rather than falling back to None.
    "Benji Tate": "benji-tate-sam-king",
    "Sam King": "benji-tate-sam-king",
    "Baron Von Hilton": "baron-von-hilton",
    "Tyler Towncroft": "tyler-towncroft",
    "The Dr. (Nikolai O'denhime)": "the-dr-slime",
    "Slime": "the-dr-slime",
    "Larry Lowhammer": "larry-lowhammer",
    "The Mad Hatter": "the-mad-hatter",
    "Lunascene": "lunascene",
    "Solarscene": "solarscene",
    "Dorris Fontaine": "dorris-fontaine",
    # Arcadian Exchange's seed lead_ai is "Clarence Porter" (primary of
    # five, per trance_one/platform_manifest.py's lead_ais split) — the
    # shared the-porter-family profile still voices the whole family. The
    # other four Porters are valid assign_ai() targets too, not just
    # lead_ais entries, so each needs its own key.
    "Clarence Porter": "the-porter-family",
    "Ann Porter": "the-porter-family",
    "George Porter": "the-porter-family",
    "Edward Porter": "the-porter-family",
    "James Porter": "the-porter-family",
    "Norman Hawkins": "norman-hawkins",
    "Zimik": "zimik",
    "Shimshi": "shimshi",
    # DocUtari's seat has a named holder (Fiddsy, per
    # trance_one/platform_manifest.py) but no personality profile authored
    # for it yet — maps to no profile rather than a guessed one.
    "Fiddsy": None,
    "Gary Glowman (Glow-Worm)": "gary-glowman",
    # norman-hawkins.json's own "serves" list already names The Spark
    # alongside The Observatory — see docs/governance/PERSONALITY-ARCHETYPES.md
    # §3 for the pre-existing Imfy/Norman-Hawkins naming inconsistency this
    # sidesteps rather than silently resolves.
    "Imfy": "norman-hawkins",
    "The Guardian (Marcus Magnolia)": "the-guardian",
    "Prometheus": "prometheus",
    "Rocking Ricki": "rocking-ricki",
    "Renik": "renik",
    "Neonach": "neonach",
    "Predictive lore": "predictive-lore",
    "Trancendos": "trancendos",
    "Samantha Turing": "samantha-turing",
    "Chronos": "chronos",
    "Kitty": "kitty",
    "Savania": "savania",
    "Elouise": "elouise",
    "tAImra": "taimra",
    "Entari": "entari",
    "Magdalena": "magdalena",
}


def resolve_personality_for_location(location: str) -> Optional[str]:
    """Resolve a Location to its currently-assigned personality profile id.

    Returns None (never raises) when the Location is unknown to the Role
    Registry, its seat is currently vacant, the assigned AI has no mapped
    profile yet, or the Role Registry itself is unavailable (e.g. its SQLite
    file can't be opened) — callers should fall back to their own default
    (e.g. "tranc3-base") rather than treat any of these as a hard error,
    since a registry outage shouldn't take /chat down when a perfectly usable
    fallback personality is available.
    """
    from src.roles.registry import get_registry

    try:
        role = get_registry().get_role(location)
    except Exception:
        return None
    if role is None or not role.assigned_ai:
        return None
    return AI_NAME_TO_PROFILE_ID.get(role.assigned_ai)
