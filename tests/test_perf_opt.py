from src.evaluation.model_eval import EvalSuite
from src.nanoservices.transcendent_fusion.transcendent_fusion import (
    CrossModalAttention,
    FusionEngine,
)
from src.neural.attention_router import _dot_product
from src.search.semantic_cache import SemanticCache


def test_semantic_cache_cosine():
    assert SemanticCache._cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_attention_router_dot():
    assert _dot_product([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_eval_cosine():
    assert EvalSuite._cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_transcendent_fusion_dot_product_opt():
    attn = CrossModalAttention(dim=16, num_heads=2)
    q = [0.1] * 16
    k = [0.2] * 16
    v = [0.3] * 16
    weights, quality = attn.compute_attention(q, k, v)

    engine = FusionEngine()
    embeddings = {"text": [0.1] * 16, "image": [0.2] * 16}
    fused = [0.15] * 16
    insights = engine._detect_emergent_insights(embeddings, fused)
    assert isinstance(insights, list)


from src.skills.enhanced_registry import EnhancedSkillRegistry


def test_enhanced_registry_cosine():
    reg = EnhancedSkillRegistry()
    assert reg._cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
