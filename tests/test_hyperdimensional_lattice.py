import pytest
from src.nanoservices.hyperdimensional_lattice.hyperdimensional_lattice import (
    HyperdimensionalVectorOps,
    Hypervector,
    LatticeTopology,
)

def test_lattice_similarity():
    lattice = HyperdimensionalVectorOps()
    v1 = Hypervector(data=[1.0, 0.0, 0.0, 1.0])
    v2 = Hypervector(data=[0.0, 1.0, 0.0, 1.0])

    # Test Cosine Similarity
    sim_cos = lattice.similarity(v1, v2, metric=LatticeTopology.COSINE)
    assert 0.49 < sim_cos < 0.51

    # Test Euclidean Similarity
    sim_euc = lattice.similarity(v1, v2, metric=LatticeTopology.EUCLIDEAN)
    assert sim_euc > 0.0

    # Test Manhattan Similarity
    sim_man = lattice.similarity(v1, v2, metric=LatticeTopology.MANHATTAN)
    assert sim_man > 0.0
