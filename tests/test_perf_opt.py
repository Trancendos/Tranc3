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

def test_attention_router_norm() -> None:
    import math

    from src.neural.attention_router import _vector_norm
    assert math.isclose(_vector_norm([3.0, 4.0]), 5.0)

def test_attention_router_softmax() -> None:
    from src.neural.attention_router import _softmax
    scores = [1.0, 2.0]
    out = _softmax(scores)
    assert len(out) == 2
    assert sum(out) > 0

import pytest

from src.neural.attention_router import AttentionRouter, RoutingRequest


@pytest.mark.asyncio
async def test_attention_router_full() -> None:
    router = AttentionRouter(embedding_dim=4)
    svc = await router.register_service("svc1", capability_tags={"test"})
    assert svc.service_id == "svc1"

    await router.report_load("svc1", 50)
    await router.report_latency("svc1", 0.5)
    await router.report_error("svc1", False)

    req = RoutingRequest(request_id="req1", required_tags={"test"})
    decision = await router.route(req)
    assert decision.selected_service == "svc1"

    stats = router.stats()
    assert stats["total_services"] == 1

    router.get_service("svc1")
    router.list_services()
    router.routing_history()

    await router.deregister_service("svc1")
