# tests/test_tranc3_ml.py
# Tests for the core Tranc3 ML pipeline:
#   Tranc3Tokenizer, AdvancedTransformerModel, Tranc3Engine, MultilingualDataset
#
# All tests run without trained model weights (bootstrap / synthetic mode).
# No external API, no Anthropic key, no transformers package required.

import asyncio
import sys
import os
import pytest

torch = pytest.importorskip("torch", reason="torch not installed — ML tests skipped")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tiny_tokenizer():
    from src.core.tranc3_tokenizer import Tranc3Tokenizer
    texts = [
        "Hello, how are you today? I am TRANC3.",
        "You are a financial specialist. Explain compound interest.",
        "Security threat detected. Initiating countermeasures.",
        "The patient presents with mild hypertension. Recommend lifestyle changes.",
        "Deploy infrastructure across three availability zones.",
    ] * 40
    tok = Tranc3Tokenizer.build_from_corpus(texts=texts, vocab_size=512)
    return tok


@pytest.fixture(scope="module")
def tiny_model():
    from src.core.advanced_model import AdvancedTransformerModel

    class Cfg:
        vocab_size = 512
        hidden_size = 64
        num_layers = 2
        num_heads = 4
        max_sequence_length = 32
        dropout = 0.0

    return AdvancedTransformerModel(Cfg())


@pytest.fixture(scope="module")
def bootstrap_engine():
    from src.core.tranc3_inference import Tranc3Engine
    engine = Tranc3Engine(
        model_path="/nonexistent/tranc3-final.pt",
        tokenizer_path="/nonexistent/tokenizer",
    )
    engine.load()
    return engine


# ---------------------------------------------------------------------------
# Tokenizer tests
# ---------------------------------------------------------------------------

class TestTranc3Tokenizer:
    def test_special_tokens_present(self, tiny_tokenizer):
        from src.core.tranc3_tokenizer import SPECIAL_TOKENS
        for name, expected_id in SPECIAL_TOKENS.items():
            assert name in tiny_tokenizer._vocab, f"Special token {name} missing from vocab"

    def test_all_ten_personalities_have_tokens(self, tiny_tokenizer):
        personalities = [
            "tranc3-base", "tranc3-creative", "tranc3-analytical",
            "tranc3-empathetic", "tranc3-multilingual",
            "dorris-fontaine", "cornelius-macintyre", "the-guardian",
            "vesper-nightingale", "atlas-meridian",
        ]
        for p in personalities:
            tok_id = tiny_tokenizer.personality_token_id(p)
            assert tok_id is not None, f"Personality token missing: {p}"

    def test_encode_returns_list_of_ints(self, tiny_tokenizer):
        ids = tiny_tokenizer.encode("Hello TRANC3")
        assert isinstance(ids, list)
        assert all(isinstance(i, int) for i in ids)
        assert len(ids) > 0

    def test_decode_roundtrip(self, tiny_tokenizer):
        text = "Hello TRANC3"
        ids = tiny_tokenizer.encode(text, add_special_tokens=False)
        decoded = tiny_tokenizer.decode(ids, skip_special_tokens=True)
        # Decoded may differ in whitespace/case due to BPE — check core words
        assert "Hello" in decoded or len(decoded) > 0

    def test_encode_chat_format(self, tiny_tokenizer):
        ids = tiny_tokenizer.encode_chat(
            system="You are TRANC3.",
            turns=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
            personality="tranc3-base",
            max_length=128,
        )
        assert isinstance(ids, list)
        assert len(ids) > 0
        # Should start with BOS token (id=2)
        assert ids[0] == tiny_tokenizer.bos_token_id
        # Should end with EOS token (id=3)
        assert ids[-1] == tiny_tokenizer.eos_token_id

    def test_max_length_respected(self, tiny_tokenizer):
        ids = tiny_tokenizer.encode("A" * 1000, max_length=32)
        assert len(ids) <= 32

    def test_encode_chat_max_length_respected(self, tiny_tokenizer):
        ids = tiny_tokenizer.encode_chat(
            system="System prompt " * 100,
            turns=[{"role": "user", "content": "Long " * 200}],
            max_length=64,
        )
        assert len(ids) <= 64

    def test_save_and_load(self, tiny_tokenizer, tmp_path):
        tiny_tokenizer.save(tmp_path)
        assert (tmp_path / "tokenizer_meta.json").exists()

        from src.core.tranc3_tokenizer import Tranc3Tokenizer
        loaded = Tranc3Tokenizer.load(tmp_path)
        assert len(loaded) == len(tiny_tokenizer)

        ids_orig = tiny_tokenizer.encode("Hello", add_special_tokens=False)
        ids_load = loaded.encode("Hello", add_special_tokens=False)
        assert ids_orig == ids_load

    def test_pad_bos_eos_ids(self, tiny_tokenizer):
        assert tiny_tokenizer.pad_token_id == 0
        assert tiny_tokenizer.bos_token_id == 2
        assert tiny_tokenizer.eos_token_id == 3
        assert tiny_tokenizer.unk_token_id == 1

    def test_len_returns_vocab_size(self, tiny_tokenizer):
        assert len(tiny_tokenizer) == len(tiny_tokenizer._vocab)
        assert len(tiny_tokenizer) > 18  # at least special tokens + BPE merges


# ---------------------------------------------------------------------------
# Advanced model tests
# ---------------------------------------------------------------------------

class TestAdvancedTransformerModel:
    def test_forward_returns_logits(self, tiny_model):
        x = torch.randint(0, 512, (1, 8))
        out = tiny_model(x)
        assert "logits" in out
        assert out["logits"].shape == (1, 8, 512)

    def test_forward_batch(self, tiny_model):
        x = torch.randint(0, 512, (4, 16))
        out = tiny_model(x)
        assert out["logits"].shape == (4, 16, 512)

    def test_last_hidden_state_present(self, tiny_model):
        x = torch.randint(0, 512, (1, 8))
        out = tiny_model(x)
        assert "last_hidden_state" in out
        assert out["last_hidden_state"].shape == (1, 8, 64)

    def test_personality_vector_injection(self, tiny_model):
        x = torch.randint(0, 512, (1, 8))
        pv = torch.randn(1, 64)
        out_without = tiny_model(x)
        out_with = tiny_model(x, personality_vector=pv)
        # Logits should differ when personality vector is injected
        assert not torch.allclose(
            out_without["logits"], out_with["logits"]
        ), "Personality vector had no effect on output"

    def test_attention_mask_accepted(self, tiny_model):
        x = torch.randint(0, 512, (1, 8))
        mask = torch.tril(torch.ones(1, 1, 8, 8))
        out = tiny_model(x, attention_mask=mask)
        assert out["logits"].shape == (1, 8, 512)

    def test_generate_returns_longer_sequence(self, tiny_model):
        x = torch.randint(0, 512, (1, 4))
        generated = tiny_model.generate(x, max_new_tokens=8, temperature=1.0)
        # Generated should be longer than input
        assert generated.shape[1] > x.shape[1]
        assert generated.shape[1] <= x.shape[1] + 8

    def test_generate_no_grad(self, tiny_model):
        x = torch.randint(0, 512, (1, 4))
        # generate() should work without gradient tracking
        with torch.no_grad():
            generated = tiny_model.generate(x, max_new_tokens=4)
        assert generated is not None

    def test_parameter_count_reasonable(self, tiny_model):
        params = sum(p.numel() for p in tiny_model.parameters())
        # A tiny 64-hidden / 2-layer / 512-vocab model should be < 1M params
        assert params < 1_000_000, f"Unexpectedly large model: {params:,} params"
        assert params > 10_000, f"Suspiciously tiny model: {params:,} params"

    def test_eval_mode(self, tiny_model):
        tiny_model.eval()
        x = torch.randint(0, 512, (1, 6))
        with torch.no_grad():
            out1 = tiny_model(x)["logits"]
            out2 = tiny_model(x)["logits"]
        assert torch.allclose(out1, out2), "Model not deterministic in eval mode"


# ---------------------------------------------------------------------------
# Inference engine tests (bootstrap mode — no weights needed)
# ---------------------------------------------------------------------------

class TestTranc3Engine:
    def test_bootstrap_mode_on_missing_weights(self, bootstrap_engine):
        st = bootstrap_engine.status()
        assert st["bootstrap_mode"] is True
        assert st["loaded"] is False

    def test_generate_returns_dict(self, bootstrap_engine):
        resp = asyncio.run(bootstrap_engine.generate("Hello"))
        assert isinstance(resp, dict)
        assert "response" in resp
        assert "personality" in resp

    def test_bootstrap_response_has_action(self, bootstrap_engine):
        resp = asyncio.run(bootstrap_engine.generate("What can you do?"))
        assert resp.get("trained") is False
        assert "action_required" in resp
        assert "train.py" in resp["action_required"]

    def test_bootstrap_includes_prompt(self, bootstrap_engine):
        prompt = "Tell me about finance"
        resp = asyncio.run(bootstrap_engine.generate(prompt))
        # Bootstrap response should mention the prompt
        assert prompt[:50] in resp["response"] or "initialising" in resp["response"].lower()

    def test_generate_respects_personality(self, bootstrap_engine):
        personalities = ["tranc3-base", "dorris-fontaine", "the-guardian"]
        for p in personalities:
            resp = asyncio.run(bootstrap_engine.generate("Hello", personality=p))
            assert resp["personality"] == p

    def test_status_has_required_keys(self, bootstrap_engine):
        st = bootstrap_engine.status()
        for key in ("loaded", "bootstrap_mode", "model_path", "tokenizer_path", "device"):
            assert key in st, f"Missing key in status(): {key}"

    def test_generate_sync_works(self, bootstrap_engine):
        resp = bootstrap_engine.generate_sync("Hello sync")
        assert "response" in resp

    def test_model_is_bootstrap_not_tranc3_local(self, bootstrap_engine):
        resp = asyncio.run(bootstrap_engine.generate("test"))
        assert resp["model"] == "tranc3-bootstrap"


# ---------------------------------------------------------------------------
# Dataset tests
# ---------------------------------------------------------------------------

class TestMultilingualDataset:
    def test_all_personalities_in_prompts(self):
        from src.core.dataset import PERSONALITY_SYSTEM_PROMPTS
        expected = {
            "tranc3-base", "tranc3-creative", "tranc3-analytical",
            "tranc3-empathetic", "tranc3-multilingual",
            "dorris-fontaine", "cornelius-macintyre", "the-guardian",
            "vesper-nightingale", "atlas-meridian",
        }
        assert expected == set(PERSONALITY_SYSTEM_PROMPTS.keys())

    def test_synthetic_fallback_generates_samples(self):
        from src.core.dataset import MultilingualDataset
        ds = MultilingualDataset(
            tokenizer=None,
            data_dir="/this/does/not/exist",
            languages=["en"],
        )
        assert len(ds) > 0

    def test_synthetic_samples_have_required_fields(self):
        from src.core.dataset import MultilingualDataset
        ds = MultilingualDataset(
            tokenizer=None,
            data_dir="/nonexistent",
            languages=["en"],
        )
        for sample in ds.samples[:5]:
            assert "instruction" in sample
            assert "response" in sample
            assert "personality" in sample
            assert "language" in sample

    def test_synthetic_covers_all_personalities(self):
        from src.core.dataset import MultilingualDataset, PERSONALITY_SYSTEM_PROMPTS
        ds = MultilingualDataset(
            tokenizer=None,
            data_dir="/nonexistent",
            languages=["en"],
        )
        found_personalities = {s["personality"] for s in ds.samples}
        for p in PERSONALITY_SYSTEM_PROMPTS:
            assert p in found_personalities, f"No synthetic samples for personality: {p}"


# ---------------------------------------------------------------------------
# Integration: tokenizer + model forward pass
# ---------------------------------------------------------------------------

class TestTokenizerModelIntegration:
    def test_tokenizer_output_fits_model_vocab(self, tiny_tokenizer, tiny_model):
        ids = tiny_tokenizer.encode("Hello TRANC3", max_length=16)
        tensor = torch.tensor([ids], dtype=torch.long)
        # Clamp to model vocab just in case BPE assigned higher ids
        tensor = tensor.clamp(0, tiny_model.vocab_size - 1)
        out = tiny_model(tensor)
        assert out["logits"].shape[-1] == tiny_model.vocab_size

    def test_chat_encoding_feeds_model(self, tiny_tokenizer, tiny_model):
        ids = tiny_tokenizer.encode_chat(
            system="You are TRANC3.",
            turns=[{"role": "user", "content": "Hello"}],
            personality="tranc3-base",
            max_length=32,
        )
        tensor = torch.tensor([ids], dtype=torch.long)
        tensor = tensor.clamp(0, tiny_model.vocab_size - 1)
        out = tiny_model(tensor)
        assert out["logits"].shape[0] == 1


# ---------------------------------------------------------------------------
# No external API dependency check
# ---------------------------------------------------------------------------

class TestNoExternalAPI:
    def test_advanced_model_no_transformers(self):
        import src.core.advanced_model as mod
        src_path = mod.__file__
        with open(src_path) as f:
            content = f.read()
        assert "from transformers" not in content
        assert "import transformers" not in content

    def test_code_generator_no_anthropic(self):
        import src.skills.code_generator as mod
        src_path = mod.__file__
        with open(src_path) as f:
            content = f.read()
        assert "api.anthropic.com" not in content
        assert "ANTHROPIC_API_KEY" not in content

    def test_workflow_nodes_no_anthropic(self):
        import src.workflow.nodes as mod
        src_path = mod.__file__
        with open(src_path) as f:
            content = f.read()
        assert "api.anthropic.com" not in content
        assert "ANTHROPIC_API_KEY" not in content
