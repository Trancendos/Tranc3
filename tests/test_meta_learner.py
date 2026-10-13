import math

from src.neural.meta_learner import _cosine_similarity


def test_cosine_similarity_identical():
    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0, 3.0]
    result = _cosine_similarity(a, b)
    assert math.isclose(result, 1.0)


def test_cosine_similarity_orthogonal():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    result = _cosine_similarity(a, b)
    assert math.isclose(result, 0.0)


def test_cosine_similarity_different_lengths():
    a = [1.0, 2.0]
    b = [1.0, 2.0, 3.0]
    result = _cosine_similarity(a, b)
    assert result == 0.0


def test_cosine_similarity_zero_norm():
    a = [0.0, 0.0]
    b = [1.0, 1.0]
    result = _cosine_similarity(a, b)
    assert result == 0.0


def test_cosine_similarity_empty():
    result = _cosine_similarity([], [])
    assert result == 0.0


def test_cosine_similarity_numpy_fallback(monkeypatch):
    import src.neural.meta_learner

    monkeypatch.setattr(src.neural.meta_learner, "_HAS_NUMPY", False)

    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0, 3.0]
    result = _cosine_similarity(a, b)
    assert math.isclose(result, 1.0)

    # Also test empty/different length to hit those lines in fallback execution
    # even though it skips the block, for completeness
    assert _cosine_similarity([], []) == 0.0
    assert _cosine_similarity([1.0], [1.0, 2.0]) == 0.0

    # Zero norm case in pure python
    assert _cosine_similarity([0.0], [1.0]) == 0.0


def test_cosine_similarity_numpy_fallback_no_sumprod(monkeypatch):
    import src.neural.meta_learner

    monkeypatch.setattr(src.neural.meta_learner, "_HAS_NUMPY", False)
    monkeypatch.setattr(src.neural.meta_learner, "_HAS_SUMPROD", False)

    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0, 3.0]
    result = _cosine_similarity(a, b)
    assert math.isclose(result, 1.0)

    assert _cosine_similarity([0.0], [1.0]) == 0.0
