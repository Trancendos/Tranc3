from typing import List

from src.evaluation.model_eval import EvalSuite
from src.nanoservices.transcendent_fusion.transcendent_fusion import (
    CrossModalAttention,
    FusionEngine,
)
from src.neural.attention_router import _dot_product
from src.search.semantic_cache import SemanticCache
from src.skills.enhanced_registry import EnhancedSkillRegistry


def test_semantic_cache_cosine() -> None:
    assert SemanticCache._cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_attention_router_dot() -> None:
    assert _dot_product([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_eval_cosine() -> None:
    assert EvalSuite._cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_transcendent_fusion_dot_product_opt() -> None:
    attn = CrossModalAttention(dim=16, num_heads=2)
    q: List[float] = [0.1] * 16
    k: List[float] = [0.2] * 16
    v: List[float] = [0.3] * 16
    weights, quality = attn.compute_attention(q, k, v)

    engine = FusionEngine()
    embeddings = {
        "text": [0.1] * 16,
        "image": [0.2] * 16,
    }
    fused: List[float] = [0.15] * 16
    insights = engine._detect_emergent_insights(embeddings, fused)
    assert isinstance(insights, list)


def test_enhanced_registry_cosine() -> None:
    reg = EnhancedSkillRegistry()
    assert reg._cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
