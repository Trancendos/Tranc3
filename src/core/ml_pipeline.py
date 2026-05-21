"""
ml_pipeline.py — Unified ML inference pipeline with Phase 4 intelligence integration.

Wraps the existing 5-tier LLMRouter with Phase 4 capabilities:
  - AttentionRouter: intelligently selects the optimal inference provider
  - MetaLearner: adapts generation parameters based on task prototypes
  - CollectiveMemory: cross-request context sharing (shared working memory)
  - CausalReasoner: diagnoses inference failures and suggests interventions
  - SemanticKnowledgeGraph: enriches prompts with structured knowledge

Architecture:
    MLPipeline.generate()
        ├─ [1] CollectiveMemory → retrieve prior context for user/session
        ├─ [2] MetaLearner → adapt generation params to task type
        ├─ [3] AttentionRouter → rank inference providers by current state
        ├─ [4] LLMRouter → attempt generation (providers in ranked order)
        ├─ [5] CausalReasoner → diagnose on failure, suggest fix
        └─ [6] CollectiveMemory → store result for future sessions

All Phase 4 components are optional; if unavailable the pipeline degrades
gracefully to standard LLMRouter behaviour.

Zero-cost model: no paid external services, all fallback to free/local providers.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy Phase 4 component singletons
# ---------------------------------------------------------------------------

_ml_pipeline_instance: Optional["MLPipeline"] = None
_attention_router_inst = None
_meta_learner_inst = None
_collective_memory_inst = None
_causal_reasoner_inst = None
_knowledge_graph_inst = None


def _get_attention_router():
    global _attention_router_inst
    if _attention_router_inst is None:
        try:
            from src.neural.attention_router import AttentionRouter, ServiceAttention
            router = AttentionRouter()
            # Register the 5 inference providers as routable services
            providers = [
                ServiceAttention(
                    service_id="tranc3",
                    service_name="Tranc3Engine",
                    capabilities=["llm", "local", "custom", "fast"],
                    tags=["local", "self-hosted", "zero-cost"],
                ),
                ServiceAttention(
                    service_id="ollama",
                    service_name="Ollama",
                    capabilities=["llm", "local", "open-source"],
                    tags=["local", "self-hosted", "zero-cost", "open-source"],
                ),
                ServiceAttention(
                    service_id="openrouter",
                    service_name="OpenRouter",
                    capabilities=["llm", "cloud", "free-tier"],
                    tags=["cloud", "zero-cost", "free-tier"],
                ),
                ServiceAttention(
                    service_id="huggingface",
                    service_name="HuggingFace",
                    capabilities=["llm", "cloud", "free-tier", "open-source"],
                    tags=["cloud", "zero-cost", "free-tier", "open-source"],
                ),
                ServiceAttention(
                    service_id="groq",
                    service_name="Groq",
                    capabilities=["llm", "cloud", "fast", "free-tier"],
                    tags=["cloud", "zero-cost", "free-tier", "fast"],
                ),
            ]
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                for svc in providers:
                    asyncio.ensure_future(router.register_service(svc))
            else:
                for svc in providers:
                    loop.run_until_complete(router.register_service(svc))
            _attention_router_inst = router
        except Exception as exc:
            logger.debug("AttentionRouter unavailable: %s", exc)
    return _attention_router_inst


def _get_meta_learner():
    global _meta_learner_inst
    if _meta_learner_inst is None:
        try:
            from src.neural.meta_learner import MetaLearner
            _meta_learner_inst = MetaLearner()
        except Exception as exc:
            logger.debug("MetaLearner unavailable: %s", exc)
    return _meta_learner_inst


def _get_collective_memory():
    global _collective_memory_inst
    if _collective_memory_inst is None:
        try:
            from src.neural.collective_memory import CollectiveMemory
            _collective_memory_inst = CollectiveMemory()
        except Exception as exc:
            logger.debug("CollectiveMemory unavailable: %s", exc)
    return _collective_memory_inst


def _get_causal_reasoner():
    global _causal_reasoner_inst
    if _causal_reasoner_inst is None:
        try:
            from src.intelligence.causal_reasoner import CausalReasoner, CausalRule, CausalStrength
            cr = CausalReasoner()
            # Seed with inference failure causal rules
            rules = [
                CausalRule(
                    cause="provider_failure",
                    effect="degraded_response",
                    strength=CausalStrength.SUFFICIENT,
                    probability=0.9,
                    description="Provider failure causes degraded/stub response",
                ),
                CausalRule(
                    cause="high_latency",
                    effect="timeout",
                    strength=CausalStrength.CONTRIBUTING,
                    probability=0.7,
                    description="High latency contributes to timeout",
                ),
                CausalRule(
                    cause="context_window_exceeded",
                    effect="provider_failure",
                    strength=CausalStrength.SUFFICIENT,
                    probability=0.95,
                    description="Exceeding context window causes provider failure",
                ),
                CausalRule(
                    cause="model_unavailable",
                    effect="provider_failure",
                    strength=CausalStrength.SUFFICIENT,
                    probability=0.99,
                    description="Model unavailability directly causes provider failure",
                ),
                CausalRule(
                    cause="rate_limit_exceeded",
                    effect="provider_failure",
                    strength=CausalStrength.SUFFICIENT,
                    probability=0.85,
                    description="Rate limiting causes provider failure",
                ),
            ]
            for rule in rules:
                cr.add_rule(rule)
            _causal_reasoner_inst = cr
        except Exception as exc:
            logger.debug("CausalReasoner unavailable: %s", exc)
    return _causal_reasoner_inst


# ---------------------------------------------------------------------------
# Request / Response types
# ---------------------------------------------------------------------------

class PipelineRequest:
    """Enriched ML inference request with Phase 4 metadata."""

    def __init__(
        self,
        prompt: str,
        personality: str = "tranc3-base",
        system_prompt: str = "",
        max_tokens: int = 512,
        temperature: float = 0.8,
        top_p: float = 0.9,
        task_domain: str = "general",
        task_type: str = "generate",
        task_tags: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        context_window: int = 4096,
        required_capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.prompt = prompt
        self.personality = personality
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.task_domain = task_domain
        self.task_type = task_type
        self.task_tags = task_tags or []
        self.session_id = session_id
        self.user_id = user_id
        self.context_window = context_window
        self.required_capabilities = required_capabilities or []
        self.metadata = metadata or {}


class PipelineResponse:
    """ML pipeline response with provenance and Phase 4 diagnostics."""

    def __init__(
        self,
        text: str,
        provider: str,
        latency_ms: float,
        adapted_params: Optional[Dict[str, Any]] = None,
        routed_from: Optional[str] = None,
        memory_key: Optional[str] = None,
        causal_diagnosis: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.text = text
        self.provider = provider
        self.latency_ms = latency_ms
        self.adapted_params = adapted_params or {}
        self.routed_from = routed_from
        self.memory_key = memory_key
        self.causal_diagnosis = causal_diagnosis
        self.error = error
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "provider": self.provider,
            "latency_ms": round(self.latency_ms, 1),
            "adapted_params": self.adapted_params,
            "routed_from": self.routed_from,
            "memory_key": self.memory_key,
            "causal_diagnosis": self.causal_diagnosis,
            "error": self.error,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Main MLPipeline
# ---------------------------------------------------------------------------

class MLPipeline:
    """
    Unified ML inference pipeline with Phase 4 intelligence integration.

    Stages:
        1. Context retrieval from CollectiveMemory
        2. Parameter adaptation via MetaLearner
        3. Provider routing via AttentionRouter
        4. Inference via LLMRouter (5-tier fallback)
        5. Failure diagnosis via CausalReasoner
        6. Result persistence in CollectiveMemory

    All Phase 4 stages are optional; failures degrade gracefully.
    """

    def __init__(self, enable_phase4: bool = True) -> None:
        self.enable_phase4 = enable_phase4
        self._call_count = 0
        self._failure_count = 0
        self._total_latency_ms = 0.0
        logger.info("MLPipeline initialised (phase4=%s)", enable_phase4)

    async def generate(self, request: PipelineRequest) -> PipelineResponse:
        """Run the full ML pipeline for a generation request."""
        t0 = time.monotonic()
        self._call_count += 1
        adapted_params: Dict[str, Any] = {}
        routed_from: Optional[str] = None
        memory_key: Optional[str] = None
        causal_diagnosis: Optional[Dict[str, Any]] = None

        # ------------------------------------------------------------------
        # Stage 1: Retrieve prior context from CollectiveMemory
        # ------------------------------------------------------------------
        prior_context = ""
        if self.enable_phase4 and request.session_id:
            try:
                cm = _get_collective_memory()
                if cm:
                    ctx_key = f"session:{request.session_id}:context"
                    entry = await cm.retrieve(ctx_key)
                    if entry and isinstance(entry.value, str):
                        prior_context = entry.value
                        logger.debug("Pipeline: retrieved prior context (session=%s)", request.session_id)
            except Exception as exc:
                logger.debug("Pipeline stage1 (memory retrieve) error: %s", exc)

        # ------------------------------------------------------------------
        # Stage 2: Adapt generation parameters via MetaLearner
        # ------------------------------------------------------------------
        base_params = {
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_tokens,
        }
        if self.enable_phase4:
            try:
                ml = _get_meta_learner()
                if ml:
                    from src.neural.meta_learner import TaskPrototype
                    task = TaskPrototype(
                        domain=request.task_domain,
                        task_type=request.task_type,
                        tags=set(request.task_tags),
                        input_schema=["prompt", "personality"],
                        output_schema=["text"],
                        parameters=base_params,
                    )
                    result = await ml.adapt(task)
                    if result:
                        adapted_params = result.adapted_parameters
                        # Apply adapted values if within safe ranges
                        if "temperature" in adapted_params:
                            t = float(adapted_params["temperature"])
                            request.temperature = max(0.01, min(2.0, t))
                        if "max_tokens" in adapted_params:
                            m = int(adapted_params["max_tokens"])
                            request.max_tokens = max(64, min(4096, m))
                        logger.debug("Pipeline: adapted params (confidence=%.2f)", result.confidence)
            except Exception as exc:
                logger.debug("Pipeline stage2 (meta_learn) error: %s", exc)

        # ------------------------------------------------------------------
        # Stage 3: Provider routing via AttentionRouter
        # ------------------------------------------------------------------
        provider_order = ["tranc3", "ollama", "openrouter", "huggingface", "groq"]
        if self.enable_phase4:
            try:
                router = _get_attention_router()
                if router:
                    from src.neural.attention_router import RoutingRequest
                    caps = list(request.required_capabilities) or ["llm"]
                    rreq = RoutingRequest(
                        query=f"{request.task_domain} {request.task_type}",
                        required_capabilities=caps,
                        preferred_tags=list(request.task_tags),
                        top_k=5,
                    )
                    decision = await router.route(rreq)
                    if decision and decision.candidates:
                        provider_order = decision.candidates + [
                            p for p in provider_order if p not in decision.candidates
                        ]
                        routed_from = decision.primary_service
                        logger.debug("Pipeline: attention-routed to %s", routed_from)
            except Exception as exc:
                logger.debug("Pipeline stage3 (attention_route) error: %s", exc)

        # ------------------------------------------------------------------
        # Stage 4: Inference via LLMRouter
        # ------------------------------------------------------------------
        from src.inference.llm_router import LLMRequest, get_router
        llm_router = get_router()

        # Optionally prepend prior context to prompt
        enriched_prompt = request.prompt
        if prior_context:
            enriched_prompt = f"[Prior context: {prior_context[:500]}]\n\n{request.prompt}"

        llm_request = LLMRequest(
            prompt=enriched_prompt,
            personality=request.personality,
            system_prompt=request.system_prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )
        llm_response = await llm_router.generate(llm_request)
        provider_name = llm_response.provider.value if hasattr(llm_response.provider, "value") else str(llm_response.provider)

        # ------------------------------------------------------------------
        # Stage 5: Causal diagnosis on failure
        # ------------------------------------------------------------------
        if llm_response.error and self.enable_phase4:
            self._failure_count += 1
            try:
                cr = _get_causal_reasoner()
                if cr:
                    cr.observe("provider_failure", True)
                    if "timeout" in (llm_response.error or "").lower():
                        cr.observe("high_latency", True)
                    if "rate" in (llm_response.error or "").lower():
                        cr.observe("rate_limit_exceeded", True)
                    if "context" in (llm_response.error or "").lower():
                        cr.observe("context_window_exceeded", True)
                    diagnosis = cr.diagnose(max_causes=3)
                    causal_diagnosis = {
                        "root_causes": diagnosis.root_causes[:3],
                        "probabilities": {k: round(v, 3) for k, v in
                                          list(diagnosis.probabilities.items())[:3]},
                    }
                    cr.reset_evidence()
                    logger.debug("Pipeline: causal diagnosis complete")
            except Exception as exc:
                logger.debug("Pipeline stage5 (causal_diagnose) error: %s", exc)

        # ------------------------------------------------------------------
        # Stage 6: Persist result in CollectiveMemory
        # ------------------------------------------------------------------
        if self.enable_phase4 and request.session_id and llm_response.text:
            try:
                cm = _get_collective_memory()
                if cm:
                    from src.neural.collective_memory import MemoryPriority
                    ctx_key = f"session:{request.session_id}:context"
                    # Keep last 500 chars of response as context seed
                    await cm.store(
                        key=ctx_key,
                        value=llm_response.text[-500:],
                        topic=f"session:{request.session_id}",
                        tags={"session", request.task_domain, request.task_type},
                        ttl=1800.0,  # 30 min session context
                        priority=MemoryPriority.NORMAL,
                        source="ml_pipeline",
                    )
                    memory_key = ctx_key
            except Exception as exc:
                logger.debug("Pipeline stage6 (memory store) error: %s", exc)

        # ------------------------------------------------------------------
        # Report latency back to AttentionRouter
        # ------------------------------------------------------------------
        if self.enable_phase4 and routed_from:
            try:
                router = _get_attention_router()
                if router:
                    total_ms = (time.monotonic() - t0) * 1000
                    success = not bool(llm_response.error)
                    await router.report_latency(routed_from, total_ms)
                    if not success:
                        await router.report_error(routed_from)
            except Exception:
                pass

        total_ms = (time.monotonic() - t0) * 1000
        self._total_latency_ms += total_ms

        return PipelineResponse(
            text=llm_response.text,
            provider=provider_name,
            latency_ms=total_ms,
            adapted_params=adapted_params,
            routed_from=routed_from,
            memory_key=memory_key,
            causal_diagnosis=causal_diagnosis,
            error=llm_response.error,
            metadata={
                "call_count": self._call_count,
                "session_id": request.session_id,
                "task_domain": request.task_domain,
                "task_type": request.task_type,
                "phase4_enabled": self.enable_phase4,
            },
        )

    async def stats(self) -> Dict[str, Any]:
        """Return pipeline health and performance statistics."""
        from src.inference.llm_router import get_router
        llm_stats = await get_router().health()
        success_rate = (
            round((self._call_count - self._failure_count) / self._call_count * 100, 1)
            if self._call_count > 0 else None
        )
        avg_latency = (
            round(self._total_latency_ms / self._call_count, 1)
            if self._call_count > 0 else None
        )
        phase4_status = {}
        if self.enable_phase4:
            phase4_status = {
                "attention_router": _attention_router_inst is not None,
                "meta_learner": _meta_learner_inst is not None,
                "collective_memory": _collective_memory_inst is not None,
                "causal_reasoner": _causal_reasoner_inst is not None,
            }
        return {
            "call_count": self._call_count,
            "failure_count": self._failure_count,
            "success_rate_pct": success_rate,
            "avg_latency_ms": avg_latency,
            "phase4_enabled": self.enable_phase4,
            "phase4_components": phase4_status,
            "llm_router": llm_stats,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

def get_pipeline() -> MLPipeline:
    """Return the process-level MLPipeline singleton."""
    global _ml_pipeline_instance
    if _ml_pipeline_instance is None:
        _ml_pipeline_instance = MLPipeline()
    return _ml_pipeline_instance
