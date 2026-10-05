from src.neural.meta_learner import _cosine_similarity


def test_meta_learner_cosine_similarity():
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
