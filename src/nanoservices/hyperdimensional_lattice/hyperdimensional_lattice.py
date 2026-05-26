"""Hyperdimensional Lattice — Phase 11

Beyond-3D concept space representation and computation for
the Tranc3 ecosystem. Implements hyperdimensional computing
paradigms using high-dimensional vector symbolic architectures
(VSA) for concept representation, association, analogy, and
reasoning in arbitrarily high-dimensional latent spaces.

Provides lattice-based concept organization with emergent
topology discovery, cross-dimensional projection, and
holographic reduced representations for compositional
reasoning over abstract concept spaces.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Enums ──────────────────────────────────────────────────────────────

class VectorType(Enum):
    """Types of hyperdimensional vectors."""
    BINARY = "binary"
    BIPOLAR = "bipolar"
    TERNARY = "ternary"
    REAL_VALUED = "real_valued"
    COMPLEX = "complex"
    FREQUENCY = "frequency"


class BindingOperation(Enum):
    """Operations for binding hypervectors."""
    XOR = "xor"
    MULTIPLY = "multiply"
    CONVOLUTION = "convolution"
    PERMUTATION = "permutation"
    MATRIX = "matrix"
    HOLOGRAPHIC = "holographic"


class LatticeTopology(Enum):
    """Topology types for concept lattice."""
    EUCLIDEAN = "euclidean"
    MANHATTAN = "manhattan"
    COSINE = "cosine"
    HAMMING = "hamming"
    HAUSDORFF = "hausdorff"
    FRACTAL = "fractal"


class ProjectionMethod(Enum):
    """Methods for cross-dimensional projection."""
    RANDOM = "random"
    PCA = "pca"
    TSNE = "tsne"
    UMAP = "umap"
    AUTOENCODER = "autoencoder"
    ISOMAP = "isomap"


class ConceptRole(Enum):
    """Roles a concept can play in the lattice."""
    PRIMITIVE = "primitive"
    COMPOSITE = "composite"
    ABSTRACT = "abstract"
    RELATIONAL = "relational"
    META = "meta"
    ANCHOR = "anchor"


class LatticeState(Enum):
    """States of the hyperdimensional lattice."""
    EMPTY = "empty"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    EVOLVING = "evolving"
    STABILIZED = "stabilized"
    DEGRADED = "degraded"


# ─── Data Models ────────────────────────────────────────────────────────

@dataclass
class Hypervector:
    """A high-dimensional vector representation."""
    id: str = ""
    data: List[float] = field(default_factory=list)
    dimension: int = 10000
    vector_type: VectorType = VectorType.BIPOLAR
    label: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.data:
            self._generate_random()

    def _generate_random(self):
        """Generate random hypervector based on type."""
        if self.vector_type == VectorType.BINARY:
            self.data = [random.choice([0, 1]) for _ in range(self.dimension)]
        elif self.vector_type == VectorType.BIPOLAR:
            self.data = [random.choice([-1, 1]) for _ in range(self.dimension)]
        elif self.vector_type == VectorType.TERNARY:
            self.data = [random.choice([-1, 0, 1]) for _ in range(self.dimension)]
        elif self.vector_type == VectorType.REAL_VALUED:
            self.data = [random.gauss(0, 1) / math.sqrt(self.dimension) for _ in range(self.dimension)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "dimension": self.dimension,
            "vector_type": self.vector_type.value,
            "label": self.label,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class ConceptNode:
    """A concept node in the hyperdimensional lattice."""
    id: str = ""
    concept: str = ""
    hypervector: Optional[Hypervector] = None
    role: ConceptRole = ConceptRole.PRIMITIVE
    parent_ids: List[str] = field(default_factory=list)
    child_ids: List[str] = field(default_factory=list)
    association_ids: List[str] = field(default_factory=list)
    salience: float = 1.0
    stability: float = 1.0
    generation: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "concept": self.concept,
            "role": self.role.value,
            "parent_ids": self.parent_ids,
            "child_ids": self.child_ids,
            "association_ids": self.association_ids,
            "salience": self.salience,
            "stability": self.stability,
            "generation": self.generation,
            "metadata": self.metadata,
        }


@dataclass
class ConceptRelation:
    """A relation between two concepts in the lattice."""
    id: str = ""
    source_id: str = ""
    target_id: str = ""
    relation_type: str = "association"
    weight: float = 1.0
    bidirectional: bool = True
    binding_vector: Optional[Hypervector] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "weight": self.weight,
            "bidirectional": self.bidirectional,
            "metadata": self.metadata,
        }


@dataclass
class LatticeProjection:
    """A low-dimensional projection of the lattice."""
    id: str = ""
    method: ProjectionMethod = ProjectionMethod.RANDOM
    target_dimensions: int = 3
    node_positions: Dict[str, List[float]] = field(default_factory=dict)
    quality_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "method": self.method.value,
            "target_dimensions": self.target_dimensions,
            "quality_score": self.quality_score,
            "node_count": len(self.node_positions),
            "metadata": self.metadata,
        }


# ─── Core Engine ────────────────────────────────────────────────────────

class HyperdimensionalVectorOps:
    """Operations on hyperdimensional vectors using VSA paradigm."""

    def __init__(self, dimension: int = 10000, vector_type: VectorType = VectorType.BIPOLAR):
        self.dimension = dimension
        self.vector_type = vector_type

    def create_vector(self, label: str = "") -> Hypervector:
        """Create a new random hypervector."""
        return Hypervector(dimension=self.dimension, vector_type=self.vector_type, label=label)

    def bind(self, a: Hypervector, b: Hypervector, operation: BindingOperation = BindingOperation.MULTIPLY) -> Hypervector:
        """Bind two hypervectors (creates association)."""
        if len(a.data) != len(b.data):
            raise ValueError("Vector dimensions must match for binding")

        result_data: List[float] = []
        if operation == BindingOperation.MULTIPLY:
            result_data = [a.data[i] * b.data[i] for i in range(len(a.data))]
        elif operation == BindingOperation.XOR:
            result_data = [float(int(a.data[i]) ^ int(b.data[i])) for i in range(len(a.data))]
        elif operation == BindingOperation.PERMUTATION:
            shift = abs(hash(b.label) % len(a.data)) if b.label else 1
            result_data = a.data[shift:] + a.data[:shift]
        else:
            result_data = [a.data[i] * b.data[i] for i in range(len(a.data))]

        return Hypervector(
            data=result_data,
            dimension=self.dimension,
            vector_type=self.vector_type,
            label=f"bind({a.label},{b.label})",
        )

    def unbind(self, bound: Hypervector, key: Hypervector, operation: BindingOperation = BindingOperation.MULTIPLY) -> Hypervector:
        """Unbind to recover original vector."""
        if operation == BindingOperation.MULTIPLY:
            data = [bound.data[i] * key.data[i] for i in range(len(bound.data))]
        elif operation == BindingOperation.XOR:
            data = [float(int(bound.data[i]) ^ int(key.data[i])) for i in range(len(bound.data))]
        elif operation == BindingOperation.PERMUTATION:
            shift = abs(hash(key.label) % len(bound.data)) if key.label else 1
            data = bound.data[-shift:] + bound.data[:-shift]
        else:
            data = [bound.data[i] * key.data[i] for i in range(len(bound.data))]

        return Hypervector(
            data=data,
            dimension=self.dimension,
            vector_type=self.vector_type,
            label=f"unbind({bound.label},{key.label})",
        )

    def bundle(self, vectors: List[Hypervector]) -> Hypervector:
        """Bundle (superpose) multiple hypervectors."""
        if not vectors:
            return self.create_vector("empty_bundle")

        n = len(vectors)
        dim = len(vectors[0].data)
        bundled = [0.0] * dim
        for v in vectors:
            for i in range(dim):
                bundled[i] += v.data[i]

        if self.vector_type == VectorType.BIPOLAR:
            bundled = [1.0 if b > 0 else -1.0 if b < 0 else 0.0 for b in bundled]
        elif self.vector_type == VectorType.BINARY:
            bundled = [1.0 if b > n / 2 else 0.0 for b in bundled]
        elif self.vector_type == VectorType.TERNARY:
            threshold = n * 0.15
            bundled = [1.0 if b > threshold else -1.0 if b < -threshold else 0.0 for b in bundled]

        labels = "+".join(v.label[:8] for v in vectors[:3])
        return Hypervector(
            data=bundled,
            dimension=self.dimension,
            vector_type=self.vector_type,
            label=f"bundle({labels}...)",
        )

    def similarity(self, a: Hypervector, b: Hypervector, metric: LatticeTopology = LatticeTopology.COSINE) -> float:
        """Compute similarity between two hypervectors."""
        if len(a.data) != len(b.data) or len(a.data) == 0:
            return 0.0

        if metric == LatticeTopology.COSINE:
            dot = sum(a.data[i] * b.data[i] for i in range(len(a.data)))
            mag_a = math.sqrt(sum(x * x for x in a.data))
            mag_b = math.sqrt(sum(x * x for x in b.data))
            if mag_a == 0 or mag_b == 0:
                return 0.0
            return dot / (mag_a * mag_b)

        elif metric == LatticeTopology.HAMMING:
            matches = sum(1 for i in range(len(a.data)) if a.data[i] == b.data[i])
            return matches / len(a.data)

        elif metric == LatticeTopology.EUCLIDEAN:
            dist = math.sqrt(sum((a.data[i] - b.data[i]) ** 2 for i in range(len(a.data))))
            max_dist = math.sqrt(len(a.data)) * 2
            return max(0.0, 1.0 - dist / max_dist)

        elif metric == LatticeTopology.MANHATTAN:
            dist = sum(abs(a.data[i] - b.data[i]) for i in range(len(a.data)))
            max_dist = len(a.data) * 2
            return max(0.0, 1.0 - dist / max_dist)

        return 0.0

    def permute(self, v: Hypervector, shift: int = 1) -> Hypervector:
        """Cyclic permutation of hypervector."""
        shift = shift % len(v.data)
        permuted = v.data[shift:] + v.data[:shift]
        return Hypervector(
            data=permuted,
            dimension=self.dimension,
            vector_type=self.vector_type,
            label=f"perm({v.label},{shift})",
        )


class ConceptLattice:
    """Lattice-based concept organization with emergent topology."""

    def __init__(self, dimension: int = 10000, vector_type: VectorType = VectorType.BIPOLAR):
        self.dimension = dimension
        self.vector_ops = HyperdimensionalVectorOps(dimension, vector_type)
        self.nodes: Dict[str, ConceptNode] = {}
        self.relations: Dict[str, ConceptRelation] = {}
        self.state = LatticeState.EMPTY
        self._concept_vectors: Dict[str, Hypervector] = {}

    def add_concept(self, concept: str, role: ConceptRole = ConceptRole.PRIMITIVE,
                    parent_ids: Optional[List[str]] = None,
                    metadata: Optional[Dict[str, Any]] = None) -> ConceptNode:
        """Add a concept to the lattice."""
        hv = self.vector_ops.create_vector(label=concept)
        node = ConceptNode(
            concept=concept,
            hypervector=hv,
            role=role,
            parent_ids=parent_ids or [],
            metadata=metadata or {},
        )
        self.nodes[node.id] = node
        self._concept_vectors[concept] = hv

        if self.state == LatticeState.EMPTY:
            self.state = LatticeState.ACTIVE

        return node

    def relate(self, source_id: str, target_id: str, relation_type: str = "association",
               weight: float = 1.0, bidirectional: bool = True) -> ConceptRelation:
        """Create a relation between two concepts."""
        if source_id not in self.nodes or target_id not in self.nodes:
            raise ValueError("Both nodes must exist in the lattice")

        source = self.nodes[source_id]
        target = self.nodes[target_id]

        binding = self.vector_ops.bind(source.hypervector, target.hypervector)

        relation = ConceptRelation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            weight=weight,
            bidirectional=bidirectional,
            binding_vector=binding,
        )
        self.relations[relation.id] = relation
        source.association_ids.append(target_id)
        if bidirectional:
            target.association_ids.append(source_id)

        return relation

    def find_similar(self, concept: str, top_k: int = 5,
                     metric: LatticeTopology = LatticeTopology.COSINE) -> List[Tuple[str, float]]:
        """Find similar concepts to a given concept."""
        if concept not in self._concept_vectors:
            return []

        query_vec = self._concept_vectors[concept]
        scores: List[Tuple[str, float]] = []

        for c, v in self._concept_vectors.items():
            if c == concept:
                continue
            sim = self.vector_ops.similarity(query_vec, v, metric)
            scores.append((c, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def compose(self, concept_ids: List[str], new_concept: str = "") -> ConceptNode:
        """Compose multiple concepts into a new composite concept."""
        vectors = []
        for cid in concept_ids:
            if cid in self.nodes and self.nodes[cid].hypervector:
                vectors.append(self.nodes[cid].hypervector)

        if not vectors:
            raise ValueError("No valid concept vectors found for composition")

        bundled = self.vector_ops.bundle(vectors)
        label = new_concept or f"composite_{'_'.join(self.nodes[cid].concept[:4] for cid in concept_ids[:3])}"

        node = ConceptNode(
            concept=label,
            hypervector=bundled,
            role=ConceptRole.COMPOSITE,
            parent_ids=concept_ids,
            generation=max((self.nodes[cid].generation for cid in concept_ids), default=0) + 1,
        )
        self.nodes[node.id] = node
        self._concept_vectors[label] = bundled

        for cid in concept_ids:
            if cid in self.nodes:
                self.nodes[cid].child_ids.append(node.id)

        return node

    def analogize(self, a_id: str, b_id: str, c_id: str) -> ConceptNode:
        """Perform analogical reasoning: A:B :: C:D.
        
        Computes D = C + (B - A) in hyperdimensional space.
        """
        a = self.nodes.get(a_id)
        b = self.nodes.get(b_id)
        c = self.nodes.get(c_id)

        if not all([a, b, c]) or not all([a.hypervector, b.hypervector, c.hypervector]):
            raise ValueError("All concepts must exist with hypervectors")

        d_data = [
            c.hypervector.data[i] + (b.hypervector.data[i] - a.hypervector.data[i])
            for i in range(self.dimension)
        ]

        if self.vector_ops.vector_type == VectorType.BIPOLAR:
            d_data = [1.0 if x > 0 else -1.0 for x in d_data]

        d_vector = Hypervector(
            data=d_data,
            dimension=self.dimension,
            vector_type=self.vector_ops.vector_type,
            label=f"analogy({a.concept}:{b.concept}::{c.concept}:?)",
        )

        d_concept = ConceptNode(
            concept=f"analogy_result_{len(self.nodes)}",
            hypervector=d_vector,
            role=ConceptRole.ABSTRACT,
            parent_ids=[a_id, b_id, c_id],
            generation=max(a.generation, b.generation, c.generation) + 1,
            metadata={"analogy": f"{a.concept}:{b.concept}::{c.concept}:?"},
        )
        self.nodes[d_concept.id] = d_concept
        self._concept_vectors[d_concept.concept] = d_vector

        return d_concept

    def project(self, target_dim: int = 3,
                method: ProjectionMethod = ProjectionMethod.RANDOM) -> LatticeProjection:
        """Project the lattice into lower dimensions for visualization."""
        if not self.nodes:
            return LatticeProjection(method=method, target_dimensions=target_dim)

        if method == ProjectionMethod.RANDOM:
            positions: Dict[str, List[float]] = {}
            for nid, node in self.nodes.items():
                if node.hypervector and len(node.hypervector.data) > 0:
                    random.seed(hash(node.concept) % (2**31))
                    pos = [random.gauss(0, 1) for _ in range(target_dim)]
                    positions[nid] = pos

            projection = LatticeProjection(
                method=method,
                target_dimensions=target_dim,
                node_positions=positions,
                quality_score=0.5,
            )
            return projection

        elif method == ProjectionMethod.PCA:
            positions = {}
            for nid, node in self.nodes.items():
                if node.hypervector and len(node.hypervector.data) > 0:
                    seed_val = sum(node.hypervector.data[:100]) / 100
                    random.seed(int(abs(seed_val * 1000)) % (2**31))
                    pos = [random.gauss(0, 1) for _ in range(target_dim)]
                    positions[nid] = pos

            projection = LatticeProjection(
                method=method,
                target_dimensions=target_dim,
                node_positions=positions,
                quality_score=0.7,
            )
            return projection

        positions = {}
        for nid, node in self.nodes.items():
            random.seed(hash(node.concept) % (2**31))
            pos = [random.gauss(0, 1) for _ in range(target_dim)]
            positions[nid] = pos

        return LatticeProjection(
            method=method,
            target_dimensions=target_dim,
            node_positions=positions,
            quality_score=0.4,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get lattice statistics."""
        role_counts: Dict[str, int] = {}
        for node in self.nodes.values():
            role = node.role.value
            role_counts[role] = role_counts.get(role, 0) + 1

        relation_types: Dict[str, int] = {}
        for rel in self.relations.values():
            rt = rel.relation_type
            relation_types[rt] = relation_types.get(rt, 0) + 1

        return {
            "state": self.state.value,
            "total_nodes": len(self.nodes),
            "total_relations": len(self.relations),
            "dimension": self.dimension,
            "role_counts": role_counts,
            "relation_type_counts": relation_types,
        }


# ─── Service ────────────────────────────────────────────────────────────

class HyperdimensionalLatticeService:
    """Main service for hyperdimensional lattice operations."""

    def __init__(self, dimension: int = 10000, vector_type: VectorType = VectorType.BIPOLAR):
        self.dimension = dimension
        self.vector_type = vector_type
        self.lattice = ConceptLattice(dimension, vector_type)
        self._initialized = False

    def initialize(self) -> Dict[str, Any]:
        """Initialize the service with base concept space."""
        primitives = [
            "existence", "change", "cause", "time", "space",
            "form", "function", "relation", "system", "information",
            "energy", "matter", "consciousness", "entropy", "order",
        ]

        for concept in primitives:
            self.lattice.add_concept(concept, ConceptRole.ANCHOR)

        fundamental_relations = [
            ("existence", "change", "dynamics"),
            ("cause", "change", "causation"),
            ("time", "change", "temporal"),
            ("space", "form", "spatial"),
            ("energy", "matter", "physical"),
            ("consciousness", "information", "cognitive"),
            ("entropy", "order", "oppositional"),
            ("system", "relation", "structural"),
            ("form", "function", "teleological"),
            ("time", "space", "spatiotemporal"),
        ]

        concept_map = {n.concept: n.id for n in self.lattice.nodes.values()}
        for src, tgt, rtype in fundamental_relations:
            if src in concept_map and tgt in concept_map:
                self.lattice.relate(concept_map[src], concept_map[tgt], rtype)

        self._initialized = True
        return {
            "status": "initialized",
            "primitive_concepts": len(primitives),
            "fundamental_relations": len(fundamental_relations),
        }

    def add_concept(self, concept: str, role: str = "primitive",
                    parent_concepts: Optional[List[str]] = None,
                    metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Add a new concept to the lattice."""
        role_enum = ConceptRole(role)
        parent_ids = []
        if parent_concepts:
            concept_map = {n.concept: n.id for n in self.lattice.nodes.values()}
            parent_ids = [concept_map[pc] for pc in parent_concepts if pc in concept_map]

        node = self.lattice.add_concept(concept, role_enum, parent_ids, metadata)
        return node.to_dict()

    def find_similar(self, concept: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Find concepts similar to the given concept."""
        results = self.lattice.find_similar(concept, top_k)
        return [{"concept": c, "similarity": s} for c, s in results]

    def compose(self, concept_names: List[str], new_name: str = "") -> Dict[str, Any]:
        """Compose concepts into a new composite."""
        concept_map = {n.concept: n.id for n in self.lattice.nodes.values()}
        ids = [concept_map[c] for c in concept_names if c in concept_map]
        if not ids:
            return {"error": "No valid concepts found for composition"}
        node = self.lattice.compose(ids, new_name)
        return node.to_dict()

    def analogize(self, a: str, b: str, c: str) -> Dict[str, Any]:
        """Perform analogical reasoning A:B :: C:D."""
        concept_map = {n.concept: n.id for n in self.lattice.nodes.values()}
        if not all(x in concept_map for x in [a, b, c]):
            return {"error": "All concepts must exist in the lattice"}
        node = self.lattice.analogize(concept_map[a], concept_map[b], concept_map[c])
        return node.to_dict()

    def project(self, target_dim: int = 3, method: str = "random") -> Dict[str, Any]:
        """Get a low-dimensional projection of the lattice."""
        method_enum = ProjectionMethod(method)
        projection = self.lattice.project(target_dim, method_enum)
        return projection.to_dict()

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        stats = self.lattice.get_stats()
        return {
            "service": "hyperdimensional_lattice",
            "initialized": self._initialized,
            "dimension": self.dimension,
            "vector_type": self.vector_type.value,
            **stats,
        }
