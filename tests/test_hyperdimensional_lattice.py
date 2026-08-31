import pytest
from src.nanoservices.hyperdimensional_lattice.hyperdimensional_lattice import HyperdimensionalVectorOps, Hypervector, LatticeTopology

def test_hyperdimensional_vector_similarity():
    ops = HyperdimensionalVectorOps(dimension=10)
    v1 = Hypervector(data=[1.0]*10, dimension=10, vector_type="dense", label="v1")
    v2 = Hypervector(data=[1.0]*10, dimension=10, vector_type="dense", label="v2")
    v3 = Hypervector(data=[0.0]*10, dimension=10, vector_type="dense", label="v3")

    # Identical vectors
    assert ops.similarity(v1, v2, LatticeTopology.COSINE) == pytest.approx(1.0)
    assert ops.similarity(v1, v2, LatticeTopology.HAMMING) == pytest.approx(1.0)
    assert ops.similarity(v1, v2, LatticeTopology.EUCLIDEAN) == pytest.approx(1.0)
    assert ops.similarity(v1, v2, LatticeTopology.MANHATTAN) == pytest.approx(1.0)

    # Different vectors
    assert ops.similarity(v1, v3, LatticeTopology.COSINE) == pytest.approx(0.0)
    assert ops.similarity(v1, v3, LatticeTopology.HAMMING) == pytest.approx(0.0)
    assert ops.similarity(v1, v3, LatticeTopology.EUCLIDEAN) == pytest.approx(0.5)
    assert ops.similarity(v1, v3, LatticeTopology.MANHATTAN) == pytest.approx(0.5)
