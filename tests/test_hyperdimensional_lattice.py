from unittest.mock import MagicMock

import pytest

from src.nanoservices.hyperdimensional_lattice.hyperdimensional_lattice import (
    ConceptLattice,
    HyperdimensionalLatticeService,
    HyperdimensionalVectorOps,
    Hypervector,
    LatticeTopology,
)


def test_hyperdimensional_vector_similarity():
    ops = HyperdimensionalVectorOps(dimension=10)
    v1 = Hypervector(data=[1.0] * 10, dimension=10, vector_type="dense", label="v1")
    v2 = Hypervector(data=[1.0] * 10, dimension=10, vector_type="dense", label="v2")
    v3 = Hypervector(data=[0.0] * 10, dimension=10, vector_type="dense", label="v3")

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


def test_hyperdimensional_vector_binding_and_bundling():
    ops = HyperdimensionalVectorOps(dimension=10)
    v1 = Hypervector(data=[1.0, -1.0] * 5, dimension=10, vector_type="dense", label="v1")
    v2 = Hypervector(data=[-1.0, 1.0] * 5, dimension=10, vector_type="dense", label="v2")

    v_bind = ops.bind(v1, v2)
    assert len(v_bind.data) == 10

    v_bundle = ops.bundle([v1, v2])
    assert len(v_bundle.data) == 10


def test_hyperdimensional_vector_permute():
    ops = HyperdimensionalVectorOps(dimension=10)
    v1 = Hypervector(
        data=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        dimension=10,
        vector_type="dense",
        label="v1",
    )
    v_perm = ops.permute(v1, shift=2)
    assert v_perm.data == [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 1.0, 2.0]


def test_concept_lattice():
    lattice = ConceptLattice(dimension=10)
    n1 = lattice.add_concept("concept1", "domain1")
    n2 = lattice.add_concept("concept2", "domain1")

    rel = lattice.relate(n1.id, n2.id, "related", 1.0)
    assert rel.source_id == n1.id

    n3 = lattice.compose([n1.id, n2.id], "concept3")
    assert n3.concept == "concept3"

    res = lattice.find_similar(n1.id, top_k=10)
    assert isinstance(res, list)


def test_concept_lattice_project():
    lattice = ConceptLattice(dimension=10)
    lattice.add_concept("concept1", "domain1")
    lattice.add_concept("concept2", "domain1")

    proj = lattice.project(target_dim=3, method="random")
    assert proj.method == "random"


@pytest.mark.asyncio
async def test_hyperdimensional_lattice_service_endpoints():
    svc = HyperdimensionalLatticeService(dimension=10)

    mock_request = MagicMock()
    mock_request.concept = "concept_test"
    mock_request.domain = "test_domain"

    response = svc.add_concept(mock_request)
    assert response is not None
