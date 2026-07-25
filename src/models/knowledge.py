# src/models/knowledge.py
"""Trancendos Models Matrix <-> The Library integration.

Two directions, both serving "models advance and enhance further, learning
from aspects within The Library, kept up to date with context from our own
systems, with knowledge distributed based on skills and job descriptions":

    Read direction (`library_context_for`):
        Before a reviewer (Cornelius, a Board member, a Human) assesses an
        advancement proposal, they can pull whatever The Library already
        knows about that skill domain — prior advancements, incident
        write-ups, anything tagged for that skill — as review context.

    Write direction (`publish_advancement_article`):
        Once a proposal is APPROVED, it's published back into The Library
        as an article tagged by skill domain, model tier, and the model's
        own Job Description (via the Location it leads, if any) — so the
        next reviewer looking at that same skill domain, or anyone
        browsing by Job Description, finds it. This is the same "forward
        real events into The Library" shape already proven for Observatory
        SECURITY/CRITICAL events (`src/observability/library_pipeline.py`),
        applied to model governance instead of audit events.

Both directions are best-effort / non-fatal — a Library outage must never
block a review or lose a proposal's own audit trail (which lives in
`governance.py`'s SQLite tables regardless of whether the Library article
was published).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.entities.platform import PLATFORM_ENTITIES, get_job_description, get_orchestration_tier

if TYPE_CHECKING:
    from src.library.knowledge_base import Article
    from src.models.governance import AdvancementProposal

logger = logging.getLogger(__name__)

ADVANCEMENT_TAG = "model-advancement"


def job_description_for_ai(ai_name: str) -> Optional[str]:
    """The Job Description of the Location `ai_name` leads, if any — an
    AI can lead more than one Location's `lead_ais` list in principle, so
    this returns the first match rather than assuming uniqueness."""
    for location, entity in PLATFORM_ENTITIES.items():
        names = entity.lead_ais if entity.lead_ais else [entity.lead_ai]
        if ai_name in names:
            return get_job_description(location)
    return None


def library_context_for(skill_domain: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Existing Library articles tagged with this skill domain — read-only
    context for a reviewer, not a review input the pipeline itself acts
    on. Returns an empty list (never raises) if The Library is unavailable
    in the current runtime/test context."""
    try:
        from src.library.knowledge_base import get_library

        articles = get_library().by_tag(skill_domain, limit=limit)
        return [
            {
                "id": a.id,
                "title": a.title,
                "tags": a.tags,
                "author": a.author,
                "created_at": a.created_at,
            }
            for a in articles
        ]
    except Exception:
        logger.debug("library_context_for(%r) unavailable", skill_domain, exc_info=True)
        return []


def _format_advancement_body(proposal: "AdvancementProposal") -> str:
    lines = [
        f"# Model Advancement — {proposal.model_name} / {proposal.skill_domain}",
        "",
        f"- Pipeline: {proposal.pipeline.value}",
        f"- Advancement: {proposal.prior_score} -> {proposal.new_score} "
        f"({proposal.advancement_pct:+.2f}%)",
        f"- Submitted by: {proposal.submitted_by}",
    ]
    if proposal.prime_reviewer:
        lines.append(f"- Prime review ({proposal.prime_reviewer}): {proposal.prime_notes}")
    if proposal.cornelius_reviewer:
        lines.append(
            f"- Cornelius review ({proposal.cornelius_reviewer}, "
            f"{proposal.cornelius_assessed_pct}%): {proposal.cornelius_notes}"
        )
    if proposal.human_decider:
        lines.append(f"- Human approval ({proposal.human_decider}): {proposal.human_notes}")
    return "\n".join(lines)


def publish_advancement_article(proposal: "AdvancementProposal") -> Optional["Article"]:
    """Publish an APPROVED advancement proposal into The Library. Best-
    effort — returns None (and logs, never raises) if The Library is
    unavailable, since losing this write must never fail the governance
    decision itself, which is already durably recorded in
    ModelGovernanceRegistry's own SQLite tables."""
    try:
        from src.library.knowledge_base import get_library

        tier = get_orchestration_tier(proposal.model_name)
        job_description = job_description_for_ai(proposal.model_name)
        tags = [ADVANCEMENT_TAG, proposal.skill_domain, tier]
        if job_description:
            tags.append(job_description)
        return get_library().create(
            title=f"{proposal.model_name}: {proposal.skill_domain} advancement approved",
            body=_format_advancement_body(proposal),
            tags=tags,
            author=proposal.model_name,
            source="models-governance",
        )
    except Exception:
        logger.debug(
            "publish_advancement_article failed for proposal id=%s", proposal.id, exc_info=True
        )
        return None
