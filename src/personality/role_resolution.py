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
    # The Dr. and Slime each have their own dedicated profile (2026-07-25 —
    # previously shared "the-dr-slime", when Slime was voiced as a
    # companion inside The Dr.'s own prompt rather than a distinct AI).
    "The Dr. (Nikolai O'denhime)": "the-dr",
    "Slime": "slime",
    "Larry Lowhammer": "larry-lowhammer",
    "The Mad Hatter": "the-mad-hatter",
    # The Chaos Party's second Lead AI. A chaos AI and an acceptance AI cannot
    # share one personality: the adversarial half is tuned for variance and the
    # deterministic half requires none, so alice-dream.json runs at
    # temperature 0.15 against The Mad Hatter's 0.75.
    "Alice Dream": "alice-dream",
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
    "Fiddsy": "fiddsy",
    "Gary Glowman (Glow-Worm)": "gary-glowman",
    # Imfy is NOT a naming variant of Norman Hawkins, and mapping it to
    # norman-hawkins.json was a tier collapse, not a shortcut.
    # PLATFORM_ENTITIES.md PID-SPK and src/entities/platform.py agree: The
    # Spark's Lead AI (Tier 3, AID-SPK-01) is Imfy and its Prime (Tier 2) is
    # Norman Hawkins, who is separately The Observatory's OWN Lead AI. The old
    # mapping therefore ran a Tier-3 AI on its own Tier-2 Prime's personality
    # and gave The Spark The Observatory's voice. imfy.json (2026-08-22) gives
    # the seat its own profile; see docs/governance/PERSONALITY-ARCHETYPES.md §3.
    "Imfy": "imfy",
    "The Guardian (Marcus Magnolia)": "the-guardian",
    # The Orb of Orisis (Infinity's precognitive AI) previously had no
    # profile mapped at all — added 2026-07-25 alongside its own
    # agent_teams pair (The Seer / The Cartographer).
    "The Orb of Orisis": "the-orb-of-orisis",
    "Prometheus": "prometheus",
    "Rocking Ricki": "rocking-ricki",
    "Renik": "renik",
    "Neonach": "neonach",
    "The Dutchy": "predictive-lore",
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
