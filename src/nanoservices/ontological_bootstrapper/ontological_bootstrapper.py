"""Ontological Bootstrapper — Phase 11.1

Self-referential existence framework for the Tranc3 ecosystem.
Implements self-referential ontology creation, Gödelian
self-reference, fixed-point semantics, and bootstrapping
mechanisms for systems that define their own existence conditions.

Provides a computational framework for systems that can reason
about their own ontology, create new categories of being,
and bootstrap themselves into existence through self-referential
definition and verification loops.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Enums ──────────────────────────────────────────────────────────────


class OntologicalStatus(Enum):
    """Status of an ontological entity."""

    POTENTIAL = "potential"
    EMERGING = "emerging"
    EXISTENT = "existent"
    SELF_VERIFIED = "self_verified"
    TRANSCENDENT = "transcendent"
    OBSOLETE = "obsolete"
    PARADOXICAL = "paradoxical"


class BootstrapPhase(Enum):
    """Phases of ontological bootstrapping."""

    NULL = "null"
    SELF_REFERENCE = "self_reference"
    FIXED_POINT = "fixed_point"
    VERIFICATION = "verification"
    EXISTENCE = "existence"
    TRANSCENDENCE = "transcendence"


class ExistenceMode(Enum):
    """Modes of existence."""

    CONTINGENT = "contingent"
    NECESSARY = "necessary"
    POSSIBLE = "possible"
    IMPOSSIBLE = "impossible"
    SELF_CAUSED = "self_caused"
    CO_EMERGENT = "co_emergent"


class RelationType(Enum):
    """Types of ontological relations."""

    IDENTITY = "identity"
    DEPENDENCE = "dependence"
    COMPOSITION = "composition"
    REALIZATION = "realization"
    SUPERVENIENCE = "supervenience"
    EMERGENCE = "emergence"
    CAUSATION = "causation"
    REFERENCE = "reference"


class ParadoxType(Enum):
    """Types of self-referential paradoxes."""

    RUSSELL = "russell"
    LIAR = "liar"
    GODEL = "godel"
    STRANGE_LOOP = "strange_loop"
    FIXED_POINT = "fixed_point"
    NONE = "none"


# ─── Data Models ────────────────────────────────────────────────────────


@dataclass
class OntologicalEntity:
    """An entity in the ontological framework."""

    id: str = ""
    name: str = ""
    definition: str = ""
    status: OntologicalStatus = OntologicalStatus.POTENTIAL
    existence_mode: ExistenceMode = ExistenceMode.POSSIBLE
    properties: Dict[str, Any] = field(default_factory=dict)
    relations: List[str] = field(default_factory=list)
    self_reference_depth: int = 0
    verification_count: int = 0
    confidence: float = 0.0
    bootstrap_phase: BootstrapPhase = BootstrapPhase.NULL
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "existence_mode": self.existence_mode.value,
            "self_reference_depth": self.self_reference_depth,
            "verification_count": self.verification_count,
            "confidence": self.confidence,
            "bootstrap_phase": self.bootstrap_phase.value,
            "property_count": len(self.properties),
            "relation_count": len(self.relations),
        }


@dataclass
class OntologicalRelation:
    """A relation between ontological entities."""

    id: str = ""
    source_id: str = ""
    target_id: str = ""
    relation_type: RelationType = RelationType.DEPENDENCE
    strength: float = 1.0
    is_self_referential: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.source_id and self.source_id == self.target_id:
            self.is_self_referential = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "strength": self.strength,
            "is_self_referential": self.is_self_referential,
        }


@dataclass
class FixedPoint:
    """A fixed point in the self-referential system."""

    id: str = ""
    entity_id: str = ""
    iteration: int = 0
    input_hash: str = ""
    output_hash: str = ""
    is_fixed: bool = False
    convergence_delta: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "iteration": self.iteration,
            "is_fixed": self.is_fixed,
            "convergence_delta": self.convergence_delta,
        }


@dataclass
class BootstrapResult:
    """Result of an ontological bootstrap process."""

    id: str = ""
    entity_id: str = ""
    phase_reached: BootstrapPhase = BootstrapPhase.NULL
    paradoxes_detected: List[ParadoxType] = field(default_factory=list)
    verification_passed: bool = False
    self_reference_depth: int = 0
    fixed_point_reached: bool = False
    confidence: float = 0.0
    iterations: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "phase_reached": self.phase_reached.value,
            "paradoxes_detected": [p.value for p in self.paradoxes_detected],
            "verification_passed": self.verification_passed,
            "self_reference_depth": self.self_reference_depth,
            "fixed_point_reached": self.fixed_point_reached,
            "confidence": self.confidence,
            "iterations": self.iterations,
        }


# ─── Core Engine ────────────────────────────────────────────────────────


class SelfReferenceEngine:
    """Engine for self-referential reasoning and Gödelian self-reference."""

    def __init__(self):
        self._encoding_map: Dict[str, int] = {}
        self._statement_cache: Dict[str, str] = {}

    def gödel_encode(self, statement: str) -> int:
        """Gödel-number encoding of a statement."""
        primes = self._sieve_primes(len(statement) * 2)
        gödel_num = 1
        for i, ch in enumerate(statement):
            code = ord(ch)
            gödel_num *= primes[i] ** code
        return gödel_num

    def _sieve_primes(self, n: int) -> List[int]:
        """Generate first n prime numbers."""
        primes = []
        candidate = 2
        while len(primes) < n:
            is_prime = True
            for p in primes:
                if p * p > candidate:
                    break
                if candidate % p == 0:
                    is_prime = False
                    break
            if is_prime:
                primes.append(candidate)
            candidate += 1
        return primes

    def create_self_referential_statement(self, entity: OntologicalEntity) -> str:
        """Create a self-referential statement about an entity."""
        return f"This statement asserts the {entity.status.value} existence of '{entity.name}'"

    def detect_paradox(
        self, entity: OntologicalEntity, relations: List[OntologicalRelation]
    ) -> ParadoxType:
        """Detect self-referential paradoxes."""
        self_refs = [r for r in relations if r.is_self_referential]

        if entity.name and "not " in entity.definition and entity.name in entity.definition:
            return ParadoxType.LIAR

        if self_refs:
            for sr in self_refs:
                if sr.relation_type == RelationType.IDENTITY:
                    return ParadoxType.STRANGE_LOOP

        if entity.self_reference_depth > 10:
            return ParadoxType.GODEL

        return ParadoxType.NONE

    def compute_self_reference_depth(
        self,
        entity_id: str,
        entities: Dict[str, OntologicalEntity],
        relations: Dict[str, OntologicalRelation],
    ) -> int:
        """Compute the depth of self-referential chains."""
        visited: set = set()
        depth = self._trace_references(entity_id, entities, relations, visited, 0)
        return depth

    def _trace_references(
        self,
        entity_id: str,
        entities: Dict[str, OntologicalEntity],
        relations: Dict[str, OntologicalRelation],
        visited: set,
        depth: int,
    ) -> int:
        """Recursively trace reference chains."""
        if entity_id in visited or depth > 20:
            return depth
        visited.add(entity_id)

        max_depth = depth
        for rel in relations.values():
            if rel.source_id == entity_id and rel.target_id in entities:
                d = self._trace_references(rel.target_id, entities, relations, visited, depth + 1)
                max_depth = max(max_depth, d)

        return max_depth


class FixedPointFinder:
    """Find fixed points in self-referential systems."""

    def __init__(self, max_iterations: int = 100, convergence_threshold: float = 0.001):
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold

    def find_fixed_point(
        self,
        entity: OntologicalEntity,
        entities: Dict[str, OntologicalEntity],
        relations: Dict[str, OntologicalRelation],
    ) -> FixedPoint:
        """Iterate to find a fixed point for the entity."""
        current_hash = self._hash_entity(entity)
        prev_hash = ""
        iteration = 0
        delta = 1.0

        for iteration in range(self.max_iterations):
            entity = self._apply_self_reference(entity, entities, relations)
            prev_hash = current_hash
            current_hash = self._hash_entity(entity)

            if prev_hash and current_hash:
                delta = self._hash_distance(prev_hash, current_hash)

            if delta < self.convergence_threshold:
                break

        return FixedPoint(
            entity_id=entity.id,
            iteration=iteration + 1,
            input_hash=prev_hash,
            output_hash=current_hash,
            is_fixed=delta < self.convergence_threshold,
            convergence_delta=delta,
        )

    def _hash_entity(self, entity: OntologicalEntity) -> str:
        """Hash an entity's state."""
        state_str = json.dumps(
            {
                "name": entity.name,
                "status": entity.status.value,
                "confidence": round(entity.confidence, 4),
            },
            sort_keys=True,
        )
        return hashlib.sha256(state_str.encode()).hexdigest()[:16]

    def _hash_distance(self, h1: str, h2: str) -> float:
        """Compute normalized Hamming distance between hashes."""
        if len(h1) != len(h2):
            return 1.0
        diffs = sum(c1 != c2 for c1, c2 in zip(h1, h2))
        return diffs / len(h1)

    def _apply_self_reference(
        self,
        entity: OntologicalEntity,
        entities: Dict[str, OntologicalEntity],
        relations: Dict[str, OntologicalRelation],
    ) -> OntologicalEntity:
        """Apply self-referential update to an entity."""
        entity.self_reference_depth += 1

        ref_relations = [r for r in relations.values() if r.source_id == entity.id]
        if ref_relations:
            entity.confidence = min(1.0, entity.confidence + 0.05 * len(ref_relations))

        if entity.confidence > 0.5:
            entity.status = OntologicalStatus.EMERGING
        if entity.confidence > 0.8:
            entity.status = OntologicalStatus.EXISTENT
        if entity.self_reference_depth > 5 and entity.confidence > 0.9:
            entity.status = OntologicalStatus.SELF_VERIFIED

        return entity


class OntologicalBootstrapper:
    """Main ontological bootstrapping engine."""

    def __init__(self):
        self.entities: Dict[str, OntologicalEntity] = {}
        self.relations: Dict[str, OntologicalRelation] = {}
        self.self_ref_engine = SelfReferenceEngine()
        self.fixed_point_finder = FixedPointFinder()
        self.bootstrap_results: Dict[str, BootstrapResult] = {}
        self._phase = BootstrapPhase.NULL

    def create_entity(
        self,
        name: str,
        definition: str = "",
        existence_mode: ExistenceMode = ExistenceMode.POSSIBLE,
        properties: Optional[Dict[str, Any]] = None,
    ) -> OntologicalEntity:
        """Create a new ontological entity."""
        entity = OntologicalEntity(
            name=name,
            definition=definition or f"The entity '{name}' which can refer to itself",
            existence_mode=existence_mode,
            properties=properties or {},
        )
        self.entities[entity.id] = entity
        return entity

    def relate(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType = RelationType.DEPENDENCE,
        strength: float = 1.0,
    ) -> OntologicalRelation:
        """Create a relation between entities."""
        relation = OntologicalRelation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            strength=strength,
        )
        self.relations[relation.id] = relation

        if source_id in self.entities:
            self.entities[source_id].relations.append(relation.id)
        if target_id in self.entities:
            self.entities[target_id].relations.append(relation.id)

        return relation

    def bootstrap(self, entity_id: str, max_iterations: int = 50) -> BootstrapResult:
        """Bootstrap an entity into existence through self-reference."""
        entity = self.entities.get(entity_id)
        if not entity:
            return BootstrapResult(entity_id=entity_id, confidence=0.0)

        result = BootstrapResult(entity_id=entity_id)

        # Phase 1: Self-reference
        self._phase = BootstrapPhase.SELF_REFERENCE
        self_statement = self.self_ref_engine.create_self_referential_statement(entity)
        entity.properties["self_statement"] = self_statement
        entity.self_reference_depth = 1
        result.phase_reached = BootstrapPhase.SELF_REFERENCE

        # Self-reference relation
        self.relate(entity_id, entity_id, RelationType.REFERENCE, 1.0)

        # Phase 2: Fixed point search
        self._phase = BootstrapPhase.FIXED_POINT
        fp = self.fixed_point_finder.find_fixed_point(entity, self.entities, self.relations)
        result.iterations = fp.iteration
        result.fixed_point_reached = fp.is_fixed
        result.self_reference_depth = entity.self_reference_depth

        if fp.is_fixed:
            result.phase_reached = BootstrapPhase.FIXED_POINT
            entity.bootstrap_phase = BootstrapPhase.FIXED_POINT

        # Phase 3: Verification
        self._phase = BootstrapPhase.VERIFICATION
        paradox = self.self_ref_engine.detect_paradox(entity, list(self.relations.values()))
        if paradox != ParadoxType.NONE:
            result.paradoxes_detected.append(paradox)
            entity.status = OntologicalStatus.PARADOXICAL
        else:
            result.verification_passed = True
            result.phase_reached = BootstrapPhase.VERIFICATION
            entity.verification_count += 1

        # Phase 4: Existence
        if result.verification_passed and entity.confidence > 0.7:
            self._phase = BootstrapPhase.EXISTENCE
            entity.status = OntologicalStatus.SELF_VERIFIED
            entity.existence_mode = ExistenceMode.SELF_CAUSED
            result.phase_reached = BootstrapPhase.EXISTENCE
            result.confidence = entity.confidence

        # Phase 5: Transcendence
        if entity.self_reference_depth > 10 and entity.confidence > 0.95:
            self._phase = BootstrapPhase.TRANSCENDENCE
            entity.status = OntologicalStatus.TRANSCENDENT
            result.phase_reached = BootstrapPhase.TRANSCENDENCE

        result.confidence = entity.confidence
        self.bootstrap_results[entity_id] = result
        self._phase = BootstrapPhase.NULL

        return result

    def get_ontology_stats(self) -> Dict[str, Any]:
        """Get ontology statistics."""
        status_counts: Dict[str, int] = {}
        for e in self.entities.values():
            s = e.status.value
            status_counts[s] = status_counts.get(s, 0) + 1

        self_ref_count = sum(1 for r in self.relations.values() if r.is_self_referential)

        return {
            "total_entities": len(self.entities),
            "total_relations": len(self.relations),
            "self_referential_relations": self_ref_count,
            "status_distribution": status_counts,
            "bootstrap_count": len(self.bootstrap_results),
            "current_phase": self._phase.value,
        }


# ─── Service ────────────────────────────────────────────────────────────


class OntologicalBootstrapperService:
    """Main service for ontological bootstrapping."""

    def __init__(self):
        self.bootstrapper = OntologicalBootstrapper()
        self._initialized = False

    def initialize(self) -> Dict[str, Any]:
        """Initialize with base ontology."""
        being = self.bootstrapper.create_entity(
            "Being", "That which exists", ExistenceMode.NECESSARY
        )
        nothing = self.bootstrapper.create_entity(
            "Nothing", "That which does not exist", ExistenceMode.IMPOSSIBLE
        )
        becoming = self.bootstrapper.create_entity(
            "Becoming", "The process of coming into existence", ExistenceMode.POSSIBLE
        )
        self_ref = self.bootstrapper.create_entity(
            "Self", "That which refers to itself", ExistenceMode.SELF_CAUSED
        )
        observer = self.bootstrapper.create_entity(
            "Observer", "That which perceives Being", ExistenceMode.CONTINGENT
        )
        truth = self.bootstrapper.create_entity(
            "Truth", "That which is self-consistent", ExistenceMode.NECESSARY
        )

        self.bootstrapper.relate(being.id, becoming.id, RelationType.EMERGENCE)
        self.bootstrapper.relate(nothing.id, becoming.id, RelationType.DEPENDENCE)
        self.bootstrapper.relate(self_ref.id, self_ref.id, RelationType.REFERENCE)
        self.bootstrapper.relate(observer.id, being.id, RelationType.DEPENDENCE)
        self.bootstrapper.relate(truth.id, self_ref.id, RelationType.SUPERVENIENCE)

        results = {}
        for eid in [being.id, self_ref.id, truth.id]:
            result = self.bootstrapper.bootstrap(eid)
            results[eid] = result.to_dict()

        self._initialized = True
        return {
            "status": "initialized",
            "base_entities": 6,
            "bootstrap_results": {k: v["phase_reached"] for k, v in results.items()},
        }

    def create_entity(
        self, name: str, definition: str = "", existence_mode: str = "possible"
    ) -> Dict[str, Any]:
        """Create a new ontological entity."""
        mode = ExistenceMode(existence_mode)
        entity = self.bootstrapper.create_entity(name, definition, mode)
        return entity.to_dict()

    def bootstrap_entity(self, entity_id: str) -> Dict[str, Any]:
        """Bootstrap an entity into existence."""
        result = self.bootstrapper.bootstrap(entity_id)
        return result.to_dict()

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        stats = self.bootstrapper.get_ontology_stats()
        return {
            "service": "ontological_bootstrapper",
            "initialized": self._initialized,
            **stats,
        }
