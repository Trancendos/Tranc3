import math

from src.nanoservices.hyperdimensional_lattice.hyperdimensional_lattice import (
    HyperdimensionalVectorOps,
    Hypervector,
    LatticeTopology,
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
