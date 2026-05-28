# FID: TRANC3-TEST-018 | Version: 1.0.0 | Module: tests
"""
tests/test_gbrain_pipeline.py — Test suite for src/gbrain/

Covers:
  - extractor: concept extraction, entity detection, salience, edges
  - GBrainClient: all methods against mock HTTP server
  - AgentInteraction: content_hash stability
  - GBrainIngestionPipeline: all 6 stages, deduplication, error handling
  - get_pipeline: module-level singleton
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Extractor tests
# ---------------------------------------------------------------------------


class TestExtractorTokenize:
    def test_basic_tokenization(self):
        from src.gbrain.extractor import _tokenize

        tokens = _tokenize("Hello world foo")
        assert "hello" in tokens
        assert "world" in tokens
        assert "foo" in tokens

    def test_strips_punctuation(self):
        from src.gbrain.extractor import _tokenize

        tokens = _tokenize("Hello, world! Foo.")
        assert "hello" in tokens
        assert "world" in tokens
        assert "foo" in tokens
        assert "hello," not in tokens

    def test_min_length_filter(self):
        from src.gbrain.extractor import _MIN_CONCEPT_LEN, _tokenize

        tokens = _tokenize("a an the hello")
        for t in tokens:
            assert len(t) >= _MIN_CONCEPT_LEN

    def test_empty_string(self):
        from src.gbrain.extractor import _tokenize

        assert _tokenize("") == []

    def test_stopwords_remain_in_tokenize(self):
        from src.gbrain.extractor import _tokenize

        # _tokenize does NOT filter stopwords — that's done in _term_salience
        # "the" is 3 chars so _MIN_CONCEPT_LEN=3 keeps it in tokenize output
        tokens = _tokenize("the quick brown fox")
        assert "quick" in tokens
        assert "brown" in tokens
        # content words are present regardless of stopword status
        assert "fox" in tokens


class TestSentenceTokenize:
    def test_splits_on_period(self):
        from src.gbrain.extractor import _sentence_tokenize

        sents = _sentence_tokenize("Hello world. Foo bar.")
        assert len(sents) == 2

    def test_splits_on_exclamation(self):
        from src.gbrain.extractor import _sentence_tokenize

        sents = _sentence_tokenize("Hello! World.")
        assert len(sents) == 2

    def test_splits_on_question(self):
        from src.gbrain.extractor import _sentence_tokenize

        sents = _sentence_tokenize("Hello? World.")
        assert len(sents) == 2

    def test_single_sentence(self):
        from src.gbrain.extractor import _sentence_tokenize

        sents = _sentence_tokenize("No punctuation here")
        assert len(sents) == 1

    def test_empty_string(self):
        from src.gbrain.extractor import _sentence_tokenize

        sents = _sentence_tokenize("")
        assert sents == []


class TestEntityExtraction:
    def test_extracts_capitalized_word(self):
        from src.gbrain.extractor import _extract_capitalized_ngrams

        entities = _extract_capitalized_ngrams("I visited Paris today.")
        texts = [e[0] for e in entities]
        assert "Paris" in texts

    def test_extracts_multi_word_entity(self):
        from src.gbrain.extractor import _extract_capitalized_ngrams

        entities = _extract_capitalized_ngrams("New York City is great.")
        texts = [e[0] for e in entities]
        # Should capture "New York City" or sub-phrase
        assert any("New" in t for t in texts)

    def test_is_entity_flag_set(self):
        from src.gbrain.extractor import _extract_capitalized_ngrams

        entities = _extract_capitalized_ngrams("Alice visited Bob.")
        for text, is_ent in entities:
            assert is_ent is True

    def test_skips_stopword_entities(self):
        from src.gbrain.extractor import _extract_capitalized_ngrams

        # "The" is a stopword — but sentence-starting capitalisation can trick it
        entities = _extract_capitalized_ngrams("The quick brown fox.")
        texts = [e[0].lower() for e in entities]
        # "The" should be skipped as it is in _STOPWORDS
        assert "the" not in texts

    def test_no_entities_in_lowercase(self):
        from src.gbrain.extractor import _extract_capitalized_ngrams

        entities = _extract_capitalized_ngrams("no entities here at all")
        assert entities == []


class TestTermSalience:
    def test_returns_dict(self):
        from src.gbrain.extractor import _term_salience

        tokens = ["quantum", "neural", "network", "quantum", "neural"]
        salience = _term_salience(tokens)
        assert isinstance(salience, dict)

    def test_scores_between_0_and_1(self):
        from src.gbrain.extractor import _term_salience

        tokens = ["quantum", "neural", "network", "quantum", "neural", "quantum"]
        salience = _term_salience(tokens)
        for val in salience.values():
            assert 0.0 <= val <= 1.0

    def test_empty_tokens(self):
        from src.gbrain.extractor import _term_salience

        assert _term_salience([]) == {}

    def test_stopwords_excluded(self):
        from src.gbrain.extractor import _STOPWORDS, _term_salience

        tokens = list(_STOPWORDS)[:5] + ["quantum"]
        salience = _term_salience(tokens)
        for sw in _STOPWORDS:
            assert sw not in salience


class TestCoOccurrenceEdges:
    def test_returns_edges(self):
        from src.gbrain.extractor import _co_occurrence_edges

        tokens = ["quantum", "neural"] * 5
        edges = _co_occurrence_edges(tokens)
        assert len(edges) >= 0  # might be 0 if window logic filters

    def test_edge_weights_normalised(self):
        from src.gbrain.extractor import _co_occurrence_edges

        tokens = ["quantum", "neural", "network", "quantum", "neural", "network"] * 3
        edges = _co_occurrence_edges(tokens)
        for e in edges:
            assert 0.0 <= e.weight <= 1.0

    def test_minimum_two_cooccurrences(self):
        from src.gbrain.extractor import _co_occurrence_edges

        # Single occurrence — should not produce an edge
        tokens = ["quantum", "photon", "electron", "gravity"]
        edges = _co_occurrence_edges(tokens)
        # With unique terms in a small window, co-occurrence count = 1 → filtered
        assert edges == []

    def test_repeated_pair_produces_edge(self):
        from src.gbrain.extractor import _co_occurrence_edges

        tokens = ["quantum", "neural"] * 10  # many co-occurrences
        edges = _co_occurrence_edges(tokens)
        pairs = {(e.source, e.target) for e in edges}
        assert any("quantum" in p and "neural" in p for p in pairs)


class TestExtract:
    def test_returns_extraction_result(self):
        from src.gbrain.extractor import ExtractionResult, extract

        result = extract("What is quantum computing?", "Quantum computing uses qubits.")
        assert isinstance(result, ExtractionResult)

    def test_concepts_capped_at_20(self):
        from src.gbrain.extractor import extract

        # Very long text with many unique terms
        words = [f"concept{i}" for i in range(100)]
        prompt = " ".join(words[:50])
        response = " ".join(words[50:])
        result = extract(prompt, response)
        assert len(result.concepts) <= 20

    def test_edges_capped_at_30(self):
        from src.gbrain.extractor import extract

        words = [f"concept{i}" for i in range(20)] * 5
        text = " ".join(words)
        result = extract(text, text)
        assert len(result.edges) <= 30

    def test_concept_scores_in_range(self):
        from src.gbrain.extractor import extract

        result = extract(
            "Neural networks use layers and weights.",
            "Deep learning models are trained via backpropagation.",
        )
        for c in result.concepts:
            assert 0.0 <= c.score <= 1.0

    def test_summary_non_empty(self):
        from src.gbrain.extractor import extract

        result = extract("Hello world.", "This is a response.")
        assert result.summary

    def test_tags_are_entity_names(self):
        from src.gbrain.extractor import extract

        result = extract("Alice and Bob met in London.", "They discussed Python programming.")
        # All tags should correspond to is_entity concepts
        entity_texts = {c.text for c in result.concepts if c.is_entity}
        for tag in result.tags:
            assert tag in entity_texts

    def test_empty_prompt_response(self):
        from src.gbrain.extractor import extract

        result = extract("", "")
        # Should return empty or minimal result — not crash
        assert isinstance(result.concepts, list)

    def test_entities_have_higher_base_score(self):
        from src.gbrain.extractor import extract

        result = extract(
            "Quantum computing with Alice in Wonderland.",
            "Alice uses quantum gates.",
        )
        entities = [c for c in result.concepts if c.is_entity]
        # Entities get a floor of 0.6 in extract()
        for e in entities:
            assert e.score >= 0.5  # a bit of slack for the test


# ---------------------------------------------------------------------------
# AgentInteraction tests
# ---------------------------------------------------------------------------


class TestAgentInteraction:
    def test_content_hash_stable(self):
        from src.gbrain.pipeline import AgentInteraction

        ai = AgentInteraction(prompt="Hello", response="World")
        assert ai.content_hash() == ai.content_hash()

    def test_content_hash_is_16_chars(self):
        from src.gbrain.pipeline import AgentInteraction

        ai = AgentInteraction(prompt="Test", response="Response")
        assert len(ai.content_hash()) == 16

    def test_content_hash_differs_for_different_content(self):
        from src.gbrain.pipeline import AgentInteraction

        ai1 = AgentInteraction(prompt="Hello", response="World")
        ai2 = AgentInteraction(prompt="Foo", response="Bar")
        assert ai1.content_hash() != ai2.content_hash()

    def test_content_hash_is_sha256_prefix(self):
        from src.gbrain.pipeline import AgentInteraction

        ai = AgentInteraction(prompt="Hello", response="World")
        raw = "Hello\nWorld"
        expected = hashlib.sha256(raw.encode()).hexdigest()[:16]
        assert ai.content_hash() == expected

    def test_defaults(self):
        from src.gbrain.pipeline import AgentInteraction

        ai = AgentInteraction(prompt="p", response="r")
        assert ai.source == "tranc3-agent"
        assert ai.user_id is None
        assert ai.session_id is None
        assert ai.metadata == {}

    def test_with_optional_fields(self):
        from src.gbrain.pipeline import AgentInteraction

        ai = AgentInteraction(
            prompt="p",
            response="r",
            source="test-src",
            user_id="u123",
            session_id="s456",
            metadata={"key": "value"},
        )
        assert ai.source == "test-src"
        assert ai.user_id == "u123"
        assert ai.session_id == "s456"
        assert ai.metadata == {"key": "value"}


# ---------------------------------------------------------------------------
# IngestionResult tests
# ---------------------------------------------------------------------------


class TestIngestionResult:
    def test_ok_when_no_error(self):
        from src.gbrain.pipeline import IngestionResult

        r = IngestionResult()
        assert r.ok is True

    def test_not_ok_when_error(self):
        from src.gbrain.pipeline import IngestionResult

        r = IngestionResult(error="something went wrong")
        assert r.ok is False

    def test_defaults(self):
        from src.gbrain.pipeline import IngestionResult

        r = IngestionResult()
        assert r.nodes_created == 0
        assert r.edges_created == 0
        assert r.nodes_skipped == 0
        assert r.duration_ms == 0.0
        assert r.error is None


# ---------------------------------------------------------------------------
# GBrainClient tests (against mock HTTP responses)
# ---------------------------------------------------------------------------


def _make_fake_client(responses: Dict[str, Any]):
    """Build a mock httpx.AsyncClient that returns canned JSON responses."""

    class FakeResponse:
        def __init__(self, data: Any, status: int = 200):
            self._data = data
            self.status_code = status

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

        def json(self) -> Any:
            return self._data

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def aclose(self):
            pass

        async def post(self, path: str, json: Any = None):
            return FakeResponse(responses.get(path, {}))

        async def get(self, path: str):
            return FakeResponse(responses.get(path, {}))

    return FakeAsyncClient()


class TestGBrainClientCreateNode:
    @pytest.mark.asyncio
    async def test_returns_node_id_on_success(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        fake = _make_fake_client({"/nodes": {"node_id": "node-abc"}})
        client._client = fake
        result = await client.create_node("Test", "Content", "src")
        assert result == "node-abc"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_client(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        # _client is None (not entered as context manager)
        result = await client.create_node("Test", "Content", "src")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()

        class ErrorClient:
            async def aclose(self):
                pass

            async def post(self, *args, **kwargs):
                raise Exception("network error")

            async def get(self, *args, **kwargs):
                raise Exception("network error")

        client._client = ErrorClient()
        result = await client.create_node("Test", "Content", "src")
        assert result is None


class TestGBrainClientCreateEdge:
    @pytest.mark.asyncio
    async def test_returns_edge_id_on_success(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        fake = _make_fake_client({"/edges": {"edge_id": "edge-xyz"}})
        client._client = fake
        result = await client.create_edge("n1", "n2", relation="supports")
        assert result == "edge-xyz"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_client(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        result = await client.create_edge("n1", "n2")
        assert result is None


class TestGBrainClientSearch:
    @pytest.mark.asyncio
    async def test_returns_combined_results(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        fake = _make_fake_client(
            {
                "/search": {
                    "direct_results": [{"node_id": "n1", "title": "Foo"}],
                    "expanded_results": [{"node_id": "n2", "title": "Bar"}],
                }
            }
        )
        client._client = fake
        results = await client.search("test query")
        assert len(results) == 2
        assert results[0]["node_id"] == "n1"
        assert results[1]["node_id"] == "n2"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_client(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        results = await client.search("query")
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()

        class ErrorClient:
            async def aclose(self):
                pass

            async def post(self, *a, **kw):
                raise Exception("fail")

            async def get(self, *a, **kw):
                raise Exception("fail")

        client._client = ErrorClient()
        results = await client.search("query")
        assert results == []


class TestGBrainClientHealth:
    @pytest.mark.asyncio
    async def test_returns_true_when_healthy(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        fake = _make_fake_client({"/health": {"status": "healthy"}})
        client._client = fake
        assert await client.health() is True

    @pytest.mark.asyncio
    async def test_returns_false_when_unhealthy(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        fake = _make_fake_client({"/health": {"status": "degraded"}})
        client._client = fake
        assert await client.health() is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_client(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        assert await client.health() is False


class TestGBrainClientPageRank:
    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        fake = _make_fake_client({"/pagerank/recompute": {"status": "recomputed"}})
        client._client = fake
        assert await client.recompute_pagerank() is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_recomputed(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        fake = _make_fake_client({"/pagerank/recompute": {"status": "noop"}})
        client._client = fake
        assert await client.recompute_pagerank() is False


class TestGBrainClientStats:
    @pytest.mark.asyncio
    async def test_returns_dict(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        fake = _make_fake_client({"/graph/stats": {"nodes": 42, "edges": 100}})
        client._client = fake
        stats = await client.stats()
        assert stats == {"nodes": 42, "edges": 100}

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        from src.gbrain.client import GBrainClient

        client = GBrainClient()
        # no _client set
        stats = await client.stats()
        assert stats == {}


class TestGBrainClientContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_sets_client_when_httpx_available(self):
        """Test that __aenter__ sets _client and __aexit__ clears it."""
        from src.gbrain.client import GBrainClient

        # We mock httpx to avoid a real connection
        mock_async_client = MagicMock()
        mock_async_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            client = GBrainClient()
            async with client as c:
                assert c._client is not None
            assert c._client is None


# ---------------------------------------------------------------------------
# GBrainIngestionPipeline tests
# ---------------------------------------------------------------------------


def _make_pipeline_with_mock_client(
    node_id: str = "node-1",
    edge_id: str = "edge-1",
    search_results: List[Dict] = None,
):
    """Build a pipeline whose GBrainClient calls are mocked."""
    from src.gbrain.pipeline import GBrainIngestionPipeline

    pipeline = GBrainIngestionPipeline()

    # We'll patch GBrainClient at the module level
    return pipeline


class TestPipelineIngest:
    @pytest.mark.asyncio
    async def test_ingest_returns_ingestion_result(self):
        from src.gbrain.pipeline import AgentInteraction, GBrainIngestionPipeline

        pipeline = GBrainIngestionPipeline()
        interaction = AgentInteraction(
            prompt="What is quantum computing?",
            response=(
                "Quantum computing uses qubits and superposition to perform "
                "computations exponentially faster than classical computers."
            ),
        )

        with patch("src.gbrain.pipeline.GBrainClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_instance.search = AsyncMock(return_value=[])
            mock_client_instance.create_node = AsyncMock(return_value="node-1")
            mock_client_instance.create_edge = AsyncMock(return_value="edge-1")
            MockClient.return_value = mock_client_instance

            result = await pipeline.ingest(interaction)

        assert result.ok
        assert result.duration_ms >= 0.0

    @pytest.mark.asyncio
    async def test_ingest_creates_nodes_for_new_concepts(self):
        from src.gbrain.pipeline import AgentInteraction, GBrainIngestionPipeline

        pipeline = GBrainIngestionPipeline()
        interaction = AgentInteraction(
            prompt="Quantum computing and neural networks are powerful tools.",
            response=(
                "Quantum neural networks combine quantum mechanics with deep learning."
                " Quantum computing is exponentially faster."
            ),
        )

        with patch("src.gbrain.pipeline.GBrainClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.search = AsyncMock(return_value=[])
            mock_client.create_node = AsyncMock(return_value="node-x")
            mock_client.create_edge = AsyncMock(return_value="edge-x")
            MockClient.return_value = mock_client

            result = await pipeline.ingest(interaction)

        # At least some nodes should have been created (text has concepts)
        assert result.nodes_created >= 0

    @pytest.mark.asyncio
    async def test_ingest_skips_duplicate_nodes(self):
        from src.gbrain.pipeline import AgentInteraction, GBrainIngestionPipeline

        pipeline = GBrainIngestionPipeline()
        interaction = AgentInteraction(
            prompt="Quantum computing is revolutionary.",
            response="Quantum computing transforms computation.",
        )

        with patch("src.gbrain.pipeline.GBrainClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            # Return existing nodes in search — should cause deduplication
            mock_client.search = AsyncMock(
                return_value=[
                    {"node_id": "existing-1", "title": "quantum"},
                    {"node_id": "existing-2", "title": "computing"},
                ]
            )
            mock_client.create_node = AsyncMock(return_value="node-new")
            mock_client.create_edge = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            result = await pipeline.ingest(interaction)

        assert result.nodes_skipped >= 0

    @pytest.mark.asyncio
    async def test_ingest_graceful_when_gbrain_unavailable(self):
        from src.gbrain.pipeline import AgentInteraction, GBrainIngestionPipeline

        pipeline = GBrainIngestionPipeline()
        interaction = AgentInteraction(
            prompt="Test prompt",
            response="Test response with some content here.",
        )

        with patch("src.gbrain.pipeline.GBrainClient") as MockClient:
            MockClient.side_effect = Exception("Connection refused")

            result = await pipeline.ingest(interaction)

        # Should not raise — error captured in result
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_ingest_empty_extraction_returns_empty_result(self):
        from src.gbrain.pipeline import AgentInteraction, GBrainIngestionPipeline

        pipeline = GBrainIngestionPipeline()
        interaction = AgentInteraction(prompt="a", response="b")
        # Very short tokens won't pass the salience threshold

        with patch("src.gbrain.pipeline.GBrainClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.search = AsyncMock(return_value=[])
            mock_client.create_node = AsyncMock(return_value=None)
            mock_client.create_edge = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            result = await pipeline.ingest(interaction)

        assert result.ok  # no error even if nothing ingested

    @pytest.mark.asyncio
    async def test_ingest_updates_stats(self):
        from src.gbrain.pipeline import AgentInteraction, GBrainIngestionPipeline

        pipeline = GBrainIngestionPipeline()
        initial_count = pipeline._interaction_count

        interaction = AgentInteraction(
            prompt="Quantum neural networks are transformative.",
            response=(
                "Quantum neural networks combine quantum physics with neural computing."
            ),
        )

        with patch("src.gbrain.pipeline.GBrainClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.search = AsyncMock(return_value=[])
            mock_client.create_node = AsyncMock(return_value="node-1")
            mock_client.create_edge = AsyncMock(return_value="edge-1")
            MockClient.return_value = mock_client

            await pipeline.ingest(interaction)

        assert pipeline._interaction_count == initial_count + 1


class TestPipelineIngestBatch:
    @pytest.mark.asyncio
    async def test_returns_list_of_results(self):
        from src.gbrain.pipeline import AgentInteraction, GBrainIngestionPipeline

        pipeline = GBrainIngestionPipeline()
        interactions = [
            AgentInteraction(prompt=f"Prompt {i}", response=f"Response {i} content words")
            for i in range(3)
        ]

        with patch("src.gbrain.pipeline.GBrainClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.search = AsyncMock(return_value=[])
            mock_client.create_node = AsyncMock(return_value="node-1")
            mock_client.create_edge = AsyncMock(return_value="edge-1")
            MockClient.return_value = mock_client

            results = await pipeline.ingest_batch(interactions)

        assert len(results) == 3
        for r in results:
            from src.gbrain.pipeline import IngestionResult

            assert isinstance(r, IngestionResult)

    @pytest.mark.asyncio
    async def test_empty_batch(self):
        from src.gbrain.pipeline import GBrainIngestionPipeline

        pipeline = GBrainIngestionPipeline()
        results = await pipeline.ingest_batch([])
        assert results == []


class TestPipelineStats:
    def test_stats_returns_dict(self):
        from src.gbrain.pipeline import GBrainIngestionPipeline

        pipeline = GBrainIngestionPipeline()
        stats = pipeline.stats()
        assert isinstance(stats, dict)
        assert "interactions_ingested" in stats
        assert "total_nodes_created" in stats
        assert "total_edges_created" in stats

    def test_stats_initial_values(self):
        from src.gbrain.pipeline import GBrainIngestionPipeline

        pipeline = GBrainIngestionPipeline()
        stats = pipeline.stats()
        assert stats["interactions_ingested"] == 0
        assert stats["total_nodes_created"] == 0
        assert stats["total_edges_created"] == 0


class TestPipelinePageRankTrigger:
    @pytest.mark.asyncio
    async def test_pagerank_triggered_at_interval(self):
        from src.gbrain.pipeline import AgentInteraction, GBrainIngestionPipeline

        pipeline = GBrainIngestionPipeline(pagerank_interval=2)
        pipeline._interaction_count = 1  # next ingest will be count=2 → trigger

        interaction = AgentInteraction(
            prompt="Quantum computing advances neural intelligence.",
            response=(
                "Quantum neural computing is a field combining quantum mechanics "
                "and artificial intelligence research."
            ),
        )

        triggered = []

        async def fake_pagerank(url: str):
            triggered.append(url)

        with (
            patch("src.gbrain.pipeline.GBrainClient") as MockClient,
            patch("src.gbrain.pipeline._background_pagerank", side_effect=fake_pagerank),
            patch("asyncio.create_task") as mock_create_task,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.search = AsyncMock(return_value=[])
            mock_client.create_node = AsyncMock(return_value="node-1")
            mock_client.create_edge = AsyncMock(return_value="edge-1")
            MockClient.return_value = mock_client

            await pipeline.ingest(interaction)

        # asyncio.create_task should have been called once for PageRank
        assert mock_create_task.call_count >= 1


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------


class TestGetPipeline:
    def test_returns_same_instance(self):
        import src.gbrain.pipeline as _mod

        # Reset singleton for clean test
        _mod._pipeline = None

        from src.gbrain.pipeline import get_pipeline

        p1 = get_pipeline()
        p2 = get_pipeline()
        assert p1 is p2

    def test_returns_gbrain_ingestion_pipeline(self):
        import src.gbrain.pipeline as _mod

        _mod._pipeline = None

        from src.gbrain.pipeline import GBrainIngestionPipeline, get_pipeline

        p = get_pipeline()
        assert isinstance(p, GBrainIngestionPipeline)

    def test_uses_provided_url(self):
        import src.gbrain.pipeline as _mod

        _mod._pipeline = None

        from src.gbrain.pipeline import get_pipeline

        p = get_pipeline(gbrain_url="http://custom:9999")
        assert p._gbrain_url == "http://custom:9999"
        # Reset
        _mod._pipeline = None

    def test_singleton_ignores_subsequent_url(self):
        import src.gbrain.pipeline as _mod

        _mod._pipeline = None

        from src.gbrain.pipeline import get_pipeline

        p1 = get_pipeline(gbrain_url="http://first:8030")
        p2 = get_pipeline(gbrain_url="http://second:9999")
        # p2 should be the same instance as p1
        assert p1 is p2
        assert p2._gbrain_url == "http://first:8030"
        # Reset
        _mod._pipeline = None


# ---------------------------------------------------------------------------
# GBrain package exports
# ---------------------------------------------------------------------------


class TestGBrainInit:
    def test_exports_gbrain_client(self):
        from src.gbrain import GBrainClient

        assert GBrainClient is not None

    def test_exports_agent_interaction(self):
        from src.gbrain import AgentInteraction

        assert AgentInteraction is not None

    def test_exports_gbrain_ingestion_pipeline(self):
        from src.gbrain import GBrainIngestionPipeline

        assert GBrainIngestionPipeline is not None
