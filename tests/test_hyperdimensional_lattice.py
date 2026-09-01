import math

import pytest

from src.nanoservices.hyperdimensional_lattice.hyperdimensional_lattice import (
    BindingOperation,
    ConceptLattice,
    HyperdimensionalVectorOps,
    Hypervector,
    LatticeTopology,
    ProjectionMethod,
    VectorType,
)


def test_hyperdimensional_lattice_cosine_similarity():
    ops = HyperdimensionalVectorOps(dimension=3)
    a = Hypervector(data=[1.0, 2.0, 3.0])
    b = Hypervector(data=[1.0, 2.0, 3.0])

    sim = ops.similarity(a, b, metric=LatticeTopology.COSINE)
    assert math.isclose(sim, 1.0, rel_tol=1e-5), f"Expected 1.0, got {sim}"

    c = Hypervector(data=[0.0, 0.0, 0.0])
    sim_zero = ops.similarity(a, c, metric=LatticeTopology.COSINE)
    assert sim_zero == 0.0, f"Expected 0.0, got {sim_zero}"

    d = Hypervector(data=[-1.0, -2.0, -3.0])
    sim_neg = ops.similarity(a, d, metric=LatticeTopology.COSINE)
    assert math.isclose(sim_neg, -1.0, rel_tol=1e-5), f"Expected -1.0, got {sim_neg}"

    e = Hypervector(data=[1.0, 0.0, 0.0])
    f = Hypervector(data=[0.0, 1.0, 0.0])
    sim_ortho = ops.similarity(e, f, metric=LatticeTopology.COSINE)
    assert sim_ortho == 0.0, f"Expected 0.0, got {sim_ortho}"


def test_hyperdimensional_lattice_hamming_similarity():
    ops = HyperdimensionalVectorOps(dimension=3)
    a = Hypervector(data=[1.0, 2.0, 3.0])
    b = Hypervector(data=[1.0, 2.0, 3.0])

    sim = ops.similarity(a, b, metric=LatticeTopology.HAMMING)
    assert sim == 1.0

    c = Hypervector(data=[1.0, 5.0, 3.0])
    sim_partial = ops.similarity(a, c, metric=LatticeTopology.HAMMING)
    assert math.isclose(sim_partial, 2 / 3)


def test_hyperdimensional_lattice_euclidean_similarity():
    ops = HyperdimensionalVectorOps(dimension=3)
    a = Hypervector(data=[0.0, 0.0, 0.0])
    b = Hypervector(data=[1.0, 0.0, 0.0])

    sim = ops.similarity(a, b, metric=LatticeTopology.EUCLIDEAN)
    assert sim > 0.0


def test_hyperdimensional_lattice_manhattan_similarity():
    ops = HyperdimensionalVectorOps(dimension=3)
    a = Hypervector(data=[1.0, 0.0, 0.0])
    b = Hypervector(data=[2.0, 0.0, 0.0])

    sim = ops.similarity(a, b, metric=LatticeTopology.MANHATTAN)
    assert sim > 0.0


def test_hyperdimensional_lattice_bind_multiply():
    ops = HyperdimensionalVectorOps(dimension=3)
    a = Hypervector(data=[1.0, -1.0, 1.0])
    b = Hypervector(data=[-1.0, 1.0, 1.0])

    result = ops.bind(a, b, operation=BindingOperation.MULTIPLY)
    assert result.data == [-1.0, -1.0, 1.0]


def test_hyperdimensional_lattice_bind_xor():
    ops = HyperdimensionalVectorOps(dimension=3)
    a = Hypervector(data=[1.0, 0.0, 1.0])
    b = Hypervector(data=[0.0, 1.0, 1.0])

    result = ops.bind(a, b, operation=BindingOperation.XOR)
    assert result.data == [1.0, 1.0, 0.0]


def test_hyperdimensional_lattice_bind_permutation():
    ops = HyperdimensionalVectorOps(dimension=3)
    a = Hypervector(data=[1.0, 2.0, 3.0], label="test")
    b = Hypervector(data=[0.0, 1.0, 1.0], label="shift")

    result = ops.bind(a, b, operation=BindingOperation.PERMUTATION)
    # Permutation shifts by a hash of label
    assert len(result.data) == 3


def test_hyperdimensional_lattice_bundle():
    ops = HyperdimensionalVectorOps(dimension=3, vector_type=VectorType.COMPLEX)
    a = Hypervector(data=[1.0, 2.0, 3.0], label="a")
    b = Hypervector(data=[1.0, 0.0, 1.0], label="b")

    result = ops.bundle([a, b])
    assert result.data == [2.0, 2.0, 4.0]


def test_hyperdimensional_lattice_bundle_bipolar():
    ops = HyperdimensionalVectorOps(dimension=3, vector_type=VectorType.BIPOLAR)
    a = Hypervector(data=[1.0, -1.0, 1.0], label="a")
    b = Hypervector(data=[1.0, 1.0, -1.0], label="b")

    result = ops.bundle([a, b])
    assert result.data == [1.0, 0.0, 0.0]


def test_hyperdimensional_lattice_bundle_binary():
    ops = HyperdimensionalVectorOps(dimension=3, vector_type=VectorType.BINARY)
    a = Hypervector(data=[1.0, 0.0, 1.0], label="a")
    b = Hypervector(data=[1.0, 1.0, 0.0], label="b")

    result = ops.bundle([a, b])
    # n = 2, n/2 = 1. > 1
    assert result.data == [1.0, 0.0, 0.0]


def test_hyperdimensional_lattice_bundle_empty():
    ops = HyperdimensionalVectorOps(dimension=3)
    result = ops.bundle([])
    assert len(result.data) == 3


def test_hyperdimensional_lattice_bundle_ternary():
    ops = HyperdimensionalVectorOps(dimension=3, vector_type=VectorType.TERNARY)
    a = Hypervector(data=[1.0, 0.0, -1.0], label="a")
    b = Hypervector(data=[1.0, -1.0, 0.0], label="b")

    result = ops.bundle([a, b])
    assert result.data == [1.0, -1.0, -1.0]


def test_hyperdimensional_lattice_concept_lattice_project():
    lattice = ConceptLattice(dimension=10, vector_type=VectorType.BIPOLAR)
    # empty lattice returns empty projection
    proj_empty = lattice.project(target_dim=3, method=ProjectionMethod.RANDOM)
    assert proj_empty.target_dimensions == 3

    node = lattice.add_concept("test_concept")

    proj_random = lattice.project(target_dim=3, method=ProjectionMethod.RANDOM)
    assert len(proj_random.node_positions) == 1
    assert len(proj_random.node_positions[node.id]) == 3

    proj_pca = lattice.project(target_dim=3, method=ProjectionMethod.PCA)
    assert len(proj_pca.node_positions) == 1

    proj_tsne = lattice.project(target_dim=3, method=ProjectionMethod.TSNE)
    assert len(proj_tsne.node_positions) == 1


def test_hyperdimensional_lattice_concept_lattice_relate():
    lattice = ConceptLattice(dimension=10, vector_type=VectorType.BIPOLAR)
    a = lattice.add_concept("a")
    b = lattice.add_concept("b")

    # create relation
    lattice.relate(a.id, b.id, weight=0.8)

    assert len(lattice.relations) == 1

    with pytest.raises(ValueError, match="Both nodes must exist"):
        lattice.relate("missing", "missing_b")
