from src.nanoservices.hyperdimensional_lattice.hyperdimensional_lattice import (
    HyperdimensionalVectorOps,
    Hypervector,
    LatticeTopology,
    VectorType,
)


def test_lattice_similarity():
    lattice = HyperdimensionalVectorOps()
    v1 = Hypervector(data=[1.0, -1.0, -1.0, 1.0], dimension=4, vector_type=VectorType.BIPOLAR)
    v2 = Hypervector(data=[-1.0, 1.0, -1.0, 1.0], dimension=4, vector_type=VectorType.BIPOLAR)

    # Test Cosine Similarity
    sim_cos = lattice.similarity(v1, v2, metric=LatticeTopology.COSINE)
    assert sim_cos > -1.0

    # Test Euclidean Similarity
    sim_euc = lattice.similarity(v1, v2, metric=LatticeTopology.EUCLIDEAN)
    assert sim_euc > 0.0

    # Test Manhattan Similarity
    sim_man = lattice.similarity(v1, v2, metric=LatticeTopology.MANHATTAN)
    assert sim_man > 0.0
