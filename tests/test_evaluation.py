"""
Tests for Tranc3 Model Evaluation Suite.
Validates BLEU, ROUGE-L, EM, Token-F1, hallucination detection, and EvalSuite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.model_eval import (
    EvalConfig,
    EvalResult,
    EvalSuite,
    bleu_score,
    exact_match,
    hallucination_score,
    rouge_l_score,
    token_f1,
)

# ---------------------------------------------------------------------------
# BLEU score
# ---------------------------------------------------------------------------

class TestBleuScore:
    def test_perfect_match(self) -> None:
        score = bleu_score("the cat sat on the mat", ["the cat sat on the mat"])
        assert score == pytest.approx(1.0, abs=0.01)

    def test_no_overlap(self) -> None:
        score = bleu_score("hello world", ["foo bar baz"], smooth=False)
        assert score == 0.0

    def test_partial_overlap(self) -> None:
        score = bleu_score("the cat sat", ["the cat sat on the mat"])
        assert 0.0 < score <= 1.0

    def test_multiple_references(self) -> None:
        score = bleu_score(
            "the quick brown fox",
            ["the quick brown fox", "a quick brown fox jumps"],
        )
        assert score > 0.5

    def test_empty_hypothesis(self) -> None:
        score = bleu_score("", ["the cat sat on the mat"])
        assert score == 0.0

    def test_single_word(self) -> None:
        score = bleu_score("cat", ["cat"])
        assert score > 0.0

    def test_smooth_flag(self) -> None:
        score_smooth = bleu_score("the cat", ["the cat sat"], smooth=True)
        score_no_smooth = bleu_score("the cat", ["the cat sat"], smooth=False)
        assert isinstance(score_smooth, float)
        assert isinstance(score_no_smooth, float)


# ---------------------------------------------------------------------------
# ROUGE-L score
# ---------------------------------------------------------------------------

class TestRougeLScore:
    def test_perfect_match(self) -> None:
        r = rouge_l_score("the cat sat on the mat", "the cat sat on the mat")
        assert r["f1"] == pytest.approx(1.0, abs=0.01)

    def test_no_overlap(self) -> None:
        r = rouge_l_score("hello world", "foo bar baz")
        assert r["f1"] == 0.0

    def test_partial_overlap(self) -> None:
        r = rouge_l_score("the cat sat", "the cat sat on the mat")
        assert 0.0 < r["f1"] < 1.0
        assert r["precision"] > 0.0
        assert r["recall"] > 0.0

    def test_empty_hypothesis(self) -> None:
        r = rouge_l_score("", "the cat sat on the mat")
        assert r["f1"] == 0.0

    def test_empty_reference(self) -> None:
        r = rouge_l_score("the cat sat", "")
        assert r["f1"] == 0.0

    def test_keys_present(self) -> None:
        r = rouge_l_score("hello", "hello world")
        assert "precision" in r
        assert "recall" in r
        assert "f1" in r


# ---------------------------------------------------------------------------
# Exact match
# ---------------------------------------------------------------------------

class TestExactMatch:
    def test_exact(self) -> None:
        assert exact_match("Hello World", "Hello World") is True

    def test_normalized_case(self) -> None:
        assert exact_match("Hello World", "hello world") is True

    def test_normalized_punctuation(self) -> None:
        assert exact_match("Hello, World!", "hello world") is True

    def test_mismatch(self) -> None:
        assert exact_match("cat", "dog") is False

    def test_empty(self) -> None:
        assert exact_match("", "") is True

    def test_whitespace_normalized(self) -> None:
        assert exact_match("  cat  ", "cat") is True


# ---------------------------------------------------------------------------
# Token F1
# ---------------------------------------------------------------------------

class TestTokenF1:
    def test_perfect_match(self) -> None:
        result = token_f1("the cat sat", "the cat sat")
        assert result["f1"] == pytest.approx(1.0, abs=0.01)

    def test_no_overlap(self) -> None:
        result = token_f1("foo bar", "baz qux")
        assert result["f1"] == 0.0

    def test_partial_overlap(self) -> None:
        result = token_f1("the cat sat", "the cat")
        assert 0.0 < result["f1"] < 1.0

    def test_keys_present(self) -> None:
        result = token_f1("hello world", "hello")
        assert "precision" in result
        assert "recall" in result
        assert "f1" in result

    def test_empty_hypothesis(self) -> None:
        result = token_f1("", "hello world")
        assert result["f1"] == 0.0


# ---------------------------------------------------------------------------
# Hallucination score
# ---------------------------------------------------------------------------

class TestHallucinationScore:
    def test_grounded_response(self) -> None:
        context = "The Eiffel Tower is located in Paris, France."
        hypothesis = "The Eiffel Tower is in Paris."
        score = hallucination_score(hypothesis, context)
        assert score < 0.5  # low hallucination

    def test_ungrounded_response(self) -> None:
        context = "The Eiffel Tower is located in Paris, France."
        hypothesis = "The Great Wall is located in China near Beijing."
        score = hallucination_score(hypothesis, context)
        assert score > 0.5  # high hallucination

    def test_empty_hypothesis(self) -> None:
        score = hallucination_score("", "some context")
        assert score == 1.0

    def test_empty_context(self) -> None:
        score = hallucination_score("some hypothesis", "")
        assert score == 1.0

    def test_returns_float(self) -> None:
        score = hallucination_score("hello", "hello world")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# EvalConfig and EvalResult
# ---------------------------------------------------------------------------

class TestEvalConfig:
    def test_defaults(self) -> None:
        config = EvalConfig(name="test")
        assert config.name == "test"
        assert config.max_new_tokens == 256
        assert config.temperature == 0.0

    def test_custom(self) -> None:
        config = EvalConfig(name="test", max_new_tokens=512, temperature=0.7)
        assert config.max_new_tokens == 512
        assert config.temperature == 0.7


class TestEvalResult:
    def test_to_dict(self) -> None:
        config = EvalConfig(name="test")
        result = EvalResult(run_id="r1", name="test", config=config)
        d = result.to_dict()
        assert "run_id" in d
        assert "name" in d
        assert "metrics" in d

    def test_summary(self) -> None:
        config = EvalConfig(name="test")
        result = EvalResult(run_id="r1", name="test", config=config)
        result.metrics["bleu"] = 0.75
        result.metrics["rouge_l"] = 0.80
        result.num_samples = 10
        s = result.summary()
        assert "test" in s
        assert "0.75" in s or "bleu" in s.lower()


# ---------------------------------------------------------------------------
# EvalSuite — async
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_eval_suite(tmp_path: Path) -> EvalSuite:
    return EvalSuite(results_dir=tmp_path / "eval")


class TestEvalSuiteBasic:
    @pytest.mark.asyncio
    async def test_evaluate_samples(self, tmp_eval_suite: EvalSuite) -> None:
        async def simple_generator(prompt: str) -> str:
            return "the cat sat on the mat"

        samples = [
            {"prompt": "describe the cat", "reference": "the cat sat on the mat"},
            {"prompt": "what did the cat do", "reference": "sat on the mat"},
        ]
        config = EvalConfig(name="basic-eval")
        result = await tmp_eval_suite.evaluate(config, simple_generator, samples)
        assert isinstance(result, EvalResult)
        assert result.num_samples == 2
        assert result.metrics["bleu"] >= 0.0
        assert result.metrics["rouge_l"] >= 0.0

    @pytest.mark.asyncio
    async def test_perfect_generator(self, tmp_eval_suite: EvalSuite) -> None:
        samples = [
            {"prompt": "q1", "reference": "answer one"},
            {"prompt": "q2", "reference": "answer two"},
        ]

        async def perfect_gen(prompt: str) -> str:
            idx = int(prompt[-1])
            return ["answer one", "answer two"][idx - 1]

        config = EvalConfig(name="perfect")
        result = await tmp_eval_suite.evaluate(config, perfect_gen, samples)
        assert result.metrics["exact_match"] == pytest.approx(1.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_result_saved_to_disk(
        self, tmp_eval_suite: EvalSuite, tmp_path: Path
    ) -> None:
        async def gen(prompt: str) -> str:
            return "output"

        samples = [{"prompt": "p", "reference": "output"}]
        config = EvalConfig(name="disk-test")
        await tmp_eval_suite.evaluate(config, gen, samples)
        saved = list((tmp_path / "eval").glob("disk-test_*.json"))
        assert len(saved) == 1

    @pytest.mark.asyncio
    async def test_metrics_keys_present(self, tmp_eval_suite: EvalSuite) -> None:
        async def gen(prompt: str) -> str:
            return "hello world"

        samples = [{"prompt": "p", "reference": "hello world"}]
        config = EvalConfig(name="keys-test")
        result = await tmp_eval_suite.evaluate(config, gen, samples)
        for key in ("bleu", "rouge_l", "exact_match", "token_f1", "hallucination"):
            assert key in result.metrics, f"Missing metric: {key}"


class TestEvalSuiteFromFile:
    @pytest.mark.asyncio
    async def test_evaluate_from_file(
        self, tmp_eval_suite: EvalSuite, tmp_path: Path
    ) -> None:
        jsonl_path = tmp_path / "samples.jsonl"
        lines = [
            json.dumps({"prompt": "p1", "reference": "r1"}),
            json.dumps({"prompt": "p2", "reference": "r2"}),
        ]
        jsonl_path.write_text("\n".join(lines))

        async def gen(prompt: str) -> str:
            return "r1" if prompt == "p1" else "r2"

        config = EvalConfig(name="from-file")
        result = await tmp_eval_suite.evaluate_from_file(
            config, gen, str(jsonl_path)
        )
        assert result.num_samples == 2
        assert result.metrics["exact_match"] == pytest.approx(1.0, abs=0.01)


class TestEvalSuiteLoraComparison:
    @pytest.mark.asyncio
    async def test_compare_base_vs_lora(self, tmp_eval_suite: EvalSuite) -> None:
        async def base_gen(prompt: str) -> str:
            return "generic response"

        async def lora_gen(prompt: str) -> str:
            return "specific answer"

        samples = [{"prompt": "q", "reference": "specific answer"}]
        config = EvalConfig(name="lora-compare")
        base_result, lora_result = await tmp_eval_suite.evaluate_lora_checkpoint(
            config, base_gen, lora_gen, samples
        )
        assert lora_result.metrics["exact_match"] > base_result.metrics["exact_match"]

    @pytest.mark.asyncio
    async def test_compare_returns_two_results(
        self, tmp_eval_suite: EvalSuite
    ) -> None:
        async def gen(prompt: str) -> str:
            return "x"

        samples = [{"prompt": "p", "reference": "x"}]
        config = EvalConfig(name="pair-test")
        pair = await tmp_eval_suite.evaluate_lora_checkpoint(
            config, gen, gen, samples
        )
        assert len(pair) == 2
        assert all(isinstance(r, EvalResult) for r in pair)
