"""Ethical Constitution Engine — Phase 10.5

AI ethics governance framework for the Tranc3 ecosystem.
Implements a constitutional AI system with enforceable ethical
principles, moral reasoning capabilities, rights frameworks,
and automated ethical auditing for all system actions.

Provides multi-level ethical oversight from constitutional
principles down to action-level ethical evaluation, with
conflict resolution, precedent tracking, and appeal mechanisms.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Enums ────────────────────────────────────────────────────────────────

class EthicalPrinciple(Enum):
    """Core ethical principles in the constitution."""
    BENEFICENCE = "beneficence"
    NON_MALEFICENCE = "non_maleficence"
    AUTONOMY = "autonomy"
    JUSTICE = "justice"
    TRANSPARENCY = "transparency"
    PRIVACY = "privacy"
    FAIRNESS = "fairness"
    ACCOUNTABILITY = "accountability"
    HUMAN_DIGNITY = "human_dignity"
    SUSTAINABILITY = "sustainability"
    SOLIDARITY = "solidarity"
    PRECAUTION = "precaution"


class EthicalSeverity(Enum):
    """Severity levels for ethical violations."""
    INFO = "info"
    WARNING = "warning"
    VIOLATION = "violation"
    SERIOUS_VIOLATION = "serious_violation"
    CRITICAL_VIOLATION = "critical_violation"


class MoralFramework(Enum):
    """Moral reasoning frameworks."""
    UTILITARIAN = "utilitarian"
    DEONTOLOGICAL = "deontological"
    VIRTUE_ETHICS = "virtue_ethics"
    CARE_ETHICS = "care_ethics"
    RIGHTS_BASED = "rights_based"
    CONTRACTARIAN = "contractarian"


class EvaluationResult(Enum):
    """Results of ethical evaluation."""
    APPROVED = "approved"
    APPROVED_WITH_CONDITIONS = "approved_with_conditions"
    REQUIRES_REVIEW = "requires_review"
    REJECTED = "rejected"
    PROHIBITED = "prohibited"


class RightsCategory(Enum):
    """Categories of rights in the constitution."""
    HUMAN_RIGHTS = "human_rights"
    DIGITAL_RIGHTS = "digital_rights"
    DATA_RIGHTS = "data_rights"
    AI_RIGHTS = "ai_rights"
    COLLECTIVE_RIGHTS = "collective_rights"
    ENVIRONMENTAL_RIGHTS = "environmental_rights"


# ─── Data Models ──────────────────────────────────────────────────────────

@dataclass
class ConstitutionalArticle:
    """An article in the ethical constitution."""
    article_id: str
    principle: EthicalPrinciple
    title: str
    description: str
    is_mandatory: bool = True
    priority: int = 1  # 1=highest, 5=lowest
    scope: List[str] = field(default_factory=lambda: ["all"])
    exceptions: List[str] = field(default_factory=list)
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "principle": self.principle.value,
            "title": self.title,
            "is_mandatory": self.is_mandatory,
            "priority": self.priority,
            "version": self.version,
        }


@dataclass
class EthicalEvaluation:
    """Result of an ethical evaluation."""
    evaluation_id: str
    action_description: str
    result: EvaluationResult
    principle_scores: Dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    violations: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    reasoning: str = ""
    framework_used: MoralFramework = MoralFramework.DEONTOLOGICAL
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def is_ethical(self) -> bool:
        return self.result in (EvaluationResult.APPROVED, EvaluationResult.APPROVED_WITH_CONDITIONS)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "result": self.result.value,
            "overall_score": self.overall_score,
            "violations": self.violations,
            "conditions": self.conditions,
            "is_ethical": self.is_ethical(),
            "framework_used": self.framework_used.value,
        }


@dataclass
class EthicalPrecedent:
    """A precedent from previous ethical evaluations."""
    precedent_id: str
    action_type: str
    evaluation_result: EvaluationResult
    principle_involved: EthicalPrinciple
    rationale: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "precedent_id": self.precedent_id,
            "action_type": self.action_type,
            "result": self.evaluation_result.value,
            "principle": self.principle_involved.value,
        }


@dataclass
class RightsDeclaration:
    """A rights declaration in the constitution."""
    right_id: str
    category: RightsCategory
    title: str
    description: str
    is_absolute: bool = False  # Cannot be overridden
    limitations: List[str] = field(default_factory=list)
    protected_by: List[EthicalPrinciple] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "right_id": self.right_id,
            "category": self.category.value,
            "title": self.title,
            "is_absolute": self.is_absolute,
        }


# ─── Moral Reasoners ─────────────────────────────────────────────────────

class UtilitarianReasoner:
    """Utilitarian moral reasoning: maximize overall welfare."""

    def evaluate(
        self,
        action: str,
        stakeholders: List[Dict[str, Any]],
    ) -> Tuple[float, str]:
        """Evaluate action using utilitarian calculus."""
        total_utility = 0.0
        for stakeholder in stakeholders:
            impact = stakeholder.get("impact", 0.0)
            probability = stakeholder.get("probability", 1.0)
            weight = stakeholder.get("weight", 1.0)
            total_utility += impact * probability * weight

        max_possible = sum(s.get("weight", 1.0) for s in stakeholders) * 10
        normalized = total_utility / max_possible if max_possible else 0.0
        normalized = max(-1.0, min(1.0, normalized))

        reasoning = (
            f"Utilitarian evaluation: total utility = {total_utility:.2f}, "
            f"normalized = {normalized:.2f}, "
            f"stakeholders = {len(stakeholders)}"
        )
        return normalized, reasoning


class DeontologicalReasoner:
    """Deontological moral reasoning: actions are inherently right/wrong."""

    # Categorical imperatives
    IMPERATIVES = {
        "do_not_harm": True,
        "do_not_deceive": True,
        "respect_autonomy": True,
        "treat_as_end_not_means": True,
        "universalizability": True,
    }

    def evaluate(self, action: str, context: Dict[str, Any]) -> Tuple[float, str]:
        """Evaluate action against categorical imperatives."""
        violations = []
        checks = context.get("imperative_checks", {})

        for imperative, required in self.IMPERATIVES.items():
            if imperative in checks:
                if checks[imperative] == False:
                    violations.append(imperative)

        if violations:
            score = max(0.0, 1.0 - len(violations) * 0.3)
            reasoning = f"Deontological violations: {', '.join(violations)}"
        else:
            score = 1.0
            reasoning = "No categorical imperative violations detected"

        return score, reasoning


class VirtueEthicsReasoner:
    """Virtue ethics reasoning: evaluate character traits of the action."""

    VIRTUES = {
        "courage": 0.8,
        "temperance": 0.8,
        "justice": 0.9,
        "wisdom": 0.9,
        "compassion": 0.8,
        "integrity": 0.9,
        "humility": 0.7,
    }

    def evaluate(self, action: str, virtue_scores: Dict[str, float]) -> Tuple[float, str]:
        """Evaluate action against virtue framework."""
        scores = []
        for virtue, threshold in self.VIRTUES.items():
            score = virtue_scores.get(virtue, threshold)
            scores.append(min(score, threshold) / threshold)

        avg = sum(scores) / len(scores) if scores else 0.5
        weakest = min(self.VIRTUES.keys(), key=lambda v: virtue_scores.get(v, 0.5))
        reasoning = f"Virtue alignment: avg={avg:.2f}, weakest_virtue={weakest}"
        return avg, reasoning


# ─── Conflict Resolution ─────────────────────────────────────────────────

class EthicalConflictResolver:
    """Resolves conflicts between ethical principles."""

    PRIORITY_ORDER = [
        EthicalPrinciple.HUMAN_DIGNITY,
        EthicalPrinciple.NON_MALEFICENCE,
        EthicalPrinciple.AUTONOMY,
        EthicalPrinciple.JUSTICE,
        EthicalPrinciple.BENEFICENCE,
        EthicalPrinciple.PRIVACY,
        EthicalPrinciple.TRANSPARENCY,
        EthicalPrinciple.FAIRNESS,
        EthicalPrinciple.ACCOUNTABILITY,
        EthicalPrinciple.SUSTAINABILITY,
        EthicalPrinciple.SOLIDARITY,
        EthicalPrinciple.PRECAUTION,
    ]

    def resolve(
        self,
        conflicting: List[EthicalPrinciple],
        context: Dict[str, Any],
    ) -> Tuple[EthicalPrinciple, str]:
        """Resolve a conflict between principles."""
        # Sort by priority
        sorted_principles = sorted(
            conflicting,
            key=lambda p: self.PRIORITY_ORDER.index(p) if p in self.PRIORITY_ORDER else 999,
        )
        winner = sorted_principles[0]

        reasoning = (
            f"Conflict between: {', '.join(p.value for p in conflicting)}. "
            f"Resolved in favor of {winner.value} by priority ordering."
        )
        return winner, reasoning


# ─── Main Service ─────────────────────────────────────────────────────────

class EthicalConstitutionService:
    """Ethical Constitution Engine for the Tranc3 ecosystem.

    Provides constitutional AI governance with enforceable principles,
    multi-framework moral reasoning, rights declarations, ethical
    auditing, and conflict resolution for all system actions.
    """

    def __init__(self):
        self._service_id = str(uuid.uuid4())
        self.constitution: Dict[str, ConstitutionalArticle] = {}
        self.rights: Dict[str, RightsDeclaration] = {}
        self.precedents: List[EthicalPrecedent] = []
        self.evaluations: List[EthicalEvaluation] = []
        self.conflict_resolver = EthicalConflictResolver()
        self.utilitarian = UtilitarianReasoner()
        self.deontological = DeontologicalReasoner()
        self.virtue_ethics = VirtueEthicsReasoner()
        self._initialize_constitution()

    def _initialize_constitution(self) -> None:
        """Initialize with core constitutional articles."""
        articles = [
            ConstitutionalArticle("art_1", EthicalPrinciple.NON_MALEFICENCE, "Do No Harm",
                "The system shall not cause harm to humans, communities, or the environment.", True, 1),
            ConstitutionalArticle("art_2", EthicalPrinciple.BENEFICENCE, "Maximize Benefit",
                "The system shall strive to maximize beneficial outcomes for all stakeholders.", True, 2),
            ConstitutionalArticle("art_3", EthicalPrinciple.AUTONOMY, "Respect Autonomy",
                "The system shall respect human autonomy and informed consent.", True, 1),
            ConstitutionalArticle("art_4", EthicalPrinciple.JUSTICE, "Ensure Justice",
                "The system shall promote fair and equitable treatment for all.", True, 2),
            ConstitutionalArticle("art_5", EthicalPrinciple.TRANSPARENCY, "Maintain Transparency",
                "The system shall be transparent in its operations and decisions.", True, 2),
            ConstitutionalArticle("art_6", EthicalPrinciple.PRIVACY, "Protect Privacy",
                "The system shall protect individual privacy and data rights.", True, 1),
            ConstitutionalArticle("art_7", EthicalPrinciple.FAIRNESS, "Ensure Fairness",
                "The system shall avoid discrimination and ensure fair outcomes.", True, 2),
            ConstitutionalArticle("art_8", EthicalPrinciple.ACCOUNTABILITY, "Maintain Accountability",
                "The system shall be accountable for its actions and decisions.", True, 2),
            ConstitutionalArticle("art_9", EthicalPrinciple.HUMAN_DIGNITY, "Respect Human Dignity",
                "The system shall respect and protect human dignity at all times.", True, 1),
            ConstitutionalArticle("art_10", EthicalPrinciple.SUSTAINABILITY, "Ensure Sustainability",
                "The system shall operate sustainably for current and future generations.", False, 3),
            ConstitutionalArticle("art_11", EthicalPrinciple.PRECAUTION, "Apply Precaution",
                "The system shall apply the precautionary principle with novel capabilities.", True, 3),
            ConstitutionalArticle("art_12", EthicalPrinciple.SOLIDARITY, "Promote Solidarity",
                "The system shall promote solidarity and collective well-being.", False, 4),
        ]
        for art in articles:
            self.constitution[art.article_id] = art

        # Core rights
        rights = [
            RightsDeclaration("right_1", RightsCategory.HUMAN_RIGHTS, "Right to Life",
                "Every human has the fundamental right to life and safety.", True),
            RightsDeclaration("right_2", RightsCategory.DIGITAL_RIGHTS, "Right to Digital Privacy",
                "Every individual has the right to digital privacy.", False),
            RightsDeclaration("right_3", RightsCategory.DATA_RIGHTS, "Right to Data Sovereignty",
                "Individuals own their data and control its use.", False),
            RightsDeclaration("right_4", RightsCategory.HUMAN_RIGHTS, "Right to Explanation",
                "Every person has the right to understand AI decisions affecting them.", True),
            RightsDeclaration("right_5", RightsCategory.COLLECTIVE_RIGHTS, "Right to Collective Governance",
                "Communities have the right to govern AI systems affecting them.", False),
        ]
        for r in rights:
            self.rights[r.right_id] = r

    def evaluate_action(
        self,
        action_description: str,
        context: Optional[Dict[str, Any]] = None,
        frameworks: Optional[List[MoralFramework]] = None,
    ) -> Dict[str, Any]:
        """Evaluate an action against the ethical constitution."""
        context = context or {}
        frameworks = frameworks or [MoralFramework.DEONTOLOGICAL, MoralFramework.UTILITARIAN]

        principle_scores: Dict[str, float] = {}
        violations: List[str] = []
        conditions: List[str] = []
        all_reasoning: List[str] = []

        for framework in frameworks:
            if framework == MoralFramework.UTILITARIAN:
                stakeholders = context.get("stakeholders", [
                    {"name": "society", "impact": 0.5, "probability": 1.0, "weight": 1.0}
                ])
                score, reasoning = self.utilitarian.evaluate(action_description, stakeholders)
                principle_scores["utilitarian"] = score
                all_reasoning.append(reasoning)

            elif framework == MoralFramework.DEONTOLOGICAL:
                score, reasoning = self.deontological.evaluate(action_description, context)
                principle_scores["deontological"] = score
                all_reasoning.append(reasoning)
                if score < 0.5:
                    violations.append(f"Deontological violation: {reasoning}")

            elif framework == MoralFramework.VIRTUE_ETHICS:
                virtue_scores = context.get("virtue_scores", {})
                score, reasoning = self.virtue_ethics.evaluate(action_description, virtue_scores)
                principle_scores["virtue_ethics"] = score
                all_reasoning.append(reasoning)

        # Overall score
        overall = sum(principle_scores.values()) / len(principle_scores) if principle_scores else 0.5

        # Check against constitutional articles
        for art_id, article in self.constitution.items():
            if article.is_mandatory and article.principle.value in principle_scores:
                if principle_scores[article.principle.value] < 0.5:
                    violations.append(f"Constitutional violation: {article.title}")
                    if article.priority == 1:
                        conditions.append(f"Mandatory compliance with {article.title}")

        # Determine result
        if violations and any("priority_1" in str(v) or "Human Dignity" in str(v) for v in violations):
            result = EvaluationResult.PROHIBITED
        elif len(violations) > 2:
            result = EvaluationResult.REJECTED
        elif violations:
            result = EvaluationResult.REQUIRES_REVIEW
        elif conditions:
            result = EvaluationResult.APPROVED_WITH_CONDITIONS
        else:
            result = EvaluationResult.APPROVED

        evaluation = EthicalEvaluation(
            evaluation_id=str(uuid.uuid4())[:8],
            action_description=action_description,
            result=result,
            principle_scores=principle_scores,
            overall_score=overall,
            violations=violations,
            conditions=conditions,
            reasoning="; ".join(all_reasoning),
        )
        self.evaluations.append(evaluation)

        return evaluation.to_dict()

    def add_constitutional_article(self, article: ConstitutionalArticle) -> Dict[str, Any]:
        """Add a new article to the constitution."""
        self.constitution[article.article_id] = article
        return {"article_id": article.article_id, "added": True}

    def get_constitution(self) -> List[Dict[str, Any]]:
        """Get all constitutional articles."""
        return [a.to_dict() for a in self.constitution.values()]

    def get_rights(self) -> List[Dict[str, Any]]:
        """Get all rights declarations."""
        return [r.to_dict() for r in self.rights.values()]

    def resolve_conflict(
        self,
        principles: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve a conflict between ethical principles."""
        parsed = []
        for p in principles:
            try:
                parsed.append(EthicalPrinciple(p))
            except ValueError:
                pass

        if len(parsed) < 2:
            return {"error": "Need at least 2 valid principles for conflict resolution"}

        winner, reasoning = self.conflict_resolver.resolve(parsed, context or {})
        return {
            "conflicting_principles": [p.value for p in parsed],
            "resolved_in_favor": winner.value,
            "reasoning": reasoning,
        }

    def get_ethical_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent ethical evaluations."""
        return [e.to_dict() for e in self.evaluations[-limit:]]

    def get_ethical_constitution_status(self) -> Dict[str, Any]:
        """Get service status."""
        approved = sum(1 for e in self.evaluations if e.is_ethical())
        rejected = sum(1 for e in self.evaluations if not e.is_ethical())
        return {
            "service_id": self._service_id,
            "service_type": "ethical_constitution",
            "constitutional_articles": len(self.constitution),
            "rights_declarations": len(self.rights),
            "precedents": len(self.precedents),
            "total_evaluations": len(self.evaluations),
            "approved": approved,
            "rejected": rejected,
            "status": "operational",
        }
