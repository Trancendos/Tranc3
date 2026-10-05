import src.neural.meta_learner


def test_meta_learner_cosine_similarity_no_numpy(monkeypatch):
    monkeypatch.setattr(src.neural.meta_learner, "_HAS_NUMPY", False)
    _cosine_similarity = src.neural.meta_learner._cosine_similarity

    vec_a = [1.0, 0.0, 0.0]
    vec_b = [1.0, 0.0, 0.0]
    assert _cosine_similarity(vec_a, vec_b) == 1.0

    vec_a = [1.0, 0.0, 0.0]
    vec_b = [0.0, 1.0, 0.0]
    assert _cosine_similarity(vec_a, vec_b) == 0.0

    vec_a = [0.0, 0.0, 0.0]
    vec_b = [1.0, 0.0, 0.0]
    assert _cosine_similarity(vec_a, vec_b) == 0.0

    vec_a = []
    vec_b = []
    assert _cosine_similarity(vec_a, vec_b) == 0.0

    vec_a = [1.0, 0.0]
    vec_b = [1.0, 0.0, 0.0]
    assert _cosine_similarity(vec_a, vec_b) == 0.0
