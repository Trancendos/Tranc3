import math

from src.nanoservices.vector_plan_cache.vector_plan_cache import InMemoryVectorStore


def test_in_memory_cosine_similarity_identical():
    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0, 3.0]
    result = InMemoryVectorStore._cosine_similarity(a, b)
    assert math.isclose(result, 1.0)


def test_in_memory_cosine_similarity_orthogonal():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    result = InMemoryVectorStore._cosine_similarity(a, b)
    assert math.isclose(result, 0.0)


def test_in_memory_cosine_similarity_different_lengths():
    a = [1.0, 2.0]
    b = [1.0, 2.0, 3.0]
    result = InMemoryVectorStore._cosine_similarity(a, b)
    assert result == 0.0


def test_in_memory_cosine_similarity_zero_norm():
    a = [0.0, 0.0]
    b = [1.0, 1.0]
    result = InMemoryVectorStore._cosine_similarity(a, b)
    assert result == 0.0


def test_in_memory_cosine_similarity_empty():
    result = InMemoryVectorStore._cosine_similarity([], [])
    assert result == 0.0


def test_in_memory_cosine_similarity_fallback(monkeypatch):
    import src.nanoservices.vector_plan_cache.vector_plan_cache

    monkeypatch.setattr(src.nanoservices.vector_plan_cache.vector_plan_cache, "_HAS_SUMPROD", False)

    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0, 3.0]
    result = InMemoryVectorStore._cosine_similarity(a, b)
    assert math.isclose(result, 1.0)

    # test pure map branch with 0 norm
    a = [0.0, 0.0]
    b = [1.0, 1.0]
    result = InMemoryVectorStore._cosine_similarity(a, b)
    assert result == 0.0
