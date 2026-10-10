import pytest
from src.nanoservices.vector_plan_cache.vector_plan_cache import InMemoryVectorStore
import src.neural.meta_learner as ml

def test_vector_plan_cache_cosine_similarity():
    # Test equal vectors
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert InMemoryVectorStore._cosine_similarity(v1, v2) == 1.0

    # Test orthogonal vectors
    v3 = [0.0, 1.0, 0.0]
    assert InMemoryVectorStore._cosine_similarity(v1, v3) == 0.0

    # Test unequal length vectors
    v_short = [1.0, 0.0]
    assert InMemoryVectorStore._cosine_similarity(v1, v_short) == 0.0

    # Test zero vectors
    v_zero = [0.0, 0.0, 0.0]
    assert InMemoryVectorStore._cosine_similarity(v_zero, v1) == 0.0
    assert InMemoryVectorStore._cosine_similarity(v1, v_zero) == 0.0


def test_meta_learner_cosine_similarity_pure_python(monkeypatch):
    # Force pure Python fallback
    monkeypatch.setattr(ml, "_HAS_NUMPY", False)

    # Test equal vectors
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert ml._cosine_similarity(v1, v2) == 1.0

    # Test orthogonal vectors
    v3 = [0.0, 1.0, 0.0]
    assert ml._cosine_similarity(v1, v3) == 0.0

    # Test unequal length vectors
    v_short = [1.0, 0.0]
    assert ml._cosine_similarity(v1, v_short) == 0.0

    # Test zero vectors
    v_zero = [0.0, 0.0, 0.0]
    assert ml._cosine_similarity(v_zero, v1) == 0.0
    assert ml._cosine_similarity(v1, v_zero) == 0.0

    # Test empty vectors
    assert ml._cosine_similarity([], []) == 0.0
