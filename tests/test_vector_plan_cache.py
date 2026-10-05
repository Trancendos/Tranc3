from src.nanoservices.vector_plan_cache.vector_plan_cache import InMemoryVectorStore

def test_vector_plan_cache_cosine_similarity():
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [1.0, 0.0, 0.0]
    assert InMemoryVectorStore._cosine_similarity(vec_a, vec_b) == 1.0

    vec_a = [1.0, 0.0, 0.0]
    vec_b = [0.0, 1.0, 0.0]
    assert InMemoryVectorStore._cosine_similarity(vec_a, vec_b) == 0.0

    vec_a = [0.0, 0.0, 0.0]
    vec_b = [1.0, 0.0, 0.0]
    assert InMemoryVectorStore._cosine_similarity(vec_a, vec_b) == 0.0
