# src/core/tranc3_tokenizer.py
# TRANC3's own BPE tokenizer — zero dependency on any pretrained model.
# Trains from raw text, saves vocab + merges to disk, reloads for inference.
# Uses HuggingFace `tokenizers` (Rust BPE algorithm — not a model, just math).

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ─── Special tokens ────────────────────────────────────────────────────────────

SPECIAL_TOKENS = {
    "<pad>": 0,
    "<unk>": 1,
    "<bos>": 2,  # beginning of sequence
    "<eos>": 3,  # end of sequence
    "<sep>": 4,  # turn separator
    "<sys>": 5,  # system prompt marker
    "<usr>": 6,  # user turn marker
    "<ast>": 7,  # assistant turn marker
    # Personality tokens — one per named personality
    "<p:tranc3-base>": 8,
    "<p:tranc3-creative>": 9,
    "<p:tranc3-analytical>": 10,
    "<p:tranc3-empathetic>": 11,
    "<p:tranc3-multilingual>": 12,
    "<p:dorris-fontaine>": 13,
    "<p:cornelius-macintyre>": 14,
    "<p:the-guardian>": 15,
    "<p:vesper-nightingale>": 16,
    "<p:atlas-meridian>": 17,
}

PAD_ID = SPECIAL_TOKENS["<pad>"]
UNK_ID = SPECIAL_TOKENS["<unk>"]
BOS_ID = SPECIAL_TOKENS["<bos>"]
EOS_ID = SPECIAL_TOKENS["<eos>"]
SEP_ID = SPECIAL_TOKENS["<sep>"]

_SPECIAL_COUNT = max(SPECIAL_TOKENS.values()) + 1  # 18


class Tranc3Tokenizer:
    """
    TRANC3's own BPE tokenizer.

    Training (one-time):
        tok = Tranc3Tokenizer()
        tok.train(texts=["...", "..."], vocab_size=8000)
        tok.save("./models/tokenizer")

    Loading for inference:
        tok = Tranc3Tokenizer.load("./models/tokenizer")

    Encoding / decoding:
        ids = tok.encode("Hello TRANC3")
        text = tok.decode(ids)
    """

    def __init__(self, vocab_size: int = 8192):
        self.vocab_size = vocab_size
        self._vocab: Dict[str, int] = dict(SPECIAL_TOKENS)  # token → id
        self._id_to_token: Dict[int, str] = {v: k for k, v in self._vocab.items()}
        self._merges: List[Tuple[str, str]] = []
        self._trained = False

    # ─── Training ──────────────────────────────────────────────────────────────

    def train(self, texts: List[str], vocab_size: Optional[int] = None) -> "Tranc3Tokenizer":
        """Train BPE on a list of strings. Uses HuggingFace tokenizers (Rust) if available,
        falls back to pure-Python implementation."""
        if vocab_size:
            self.vocab_size = vocab_size

        try:
            return self._train_with_hf(texts)
        except ImportError:
            logger.info("tokenizers library not installed — using pure-Python BPE trainer")
            return self._train_python_bpe(texts)

    def _train_with_hf(self, texts: List[str]) -> "Tranc3Tokenizer":
        from tokenizers import Tokenizer
        from tokenizers.models import BPE
        from tokenizers.pre_tokenizers import ByteLevel
        from tokenizers.trainers import BpeTrainer

        special_list = list(SPECIAL_TOKENS.keys())

        tokenizer = Tokenizer(BPE(unk_token="<unk>"))  # nosec B106  # noqa: S106 — <unk> is a tokenizer sentinel, not a password

        tokenizer.pre_tokenizer = ByteLevel(add_prefix_space=False)

        trainer = BpeTrainer(
            vocab_size=self.vocab_size,
            special_tokens=special_list,
            min_frequency=2,
            show_progress=False,
        )

        tokenizer.train_from_iterator(texts, trainer=trainer)

        # Rebuild our internal vocab from HF tokenizer
        vocab = tokenizer.get_vocab()
        self._vocab = vocab
        self._id_to_token = {v: k for k, v in vocab.items()}

        # Ensure special tokens have correct IDs
        for tok, expected_id in SPECIAL_TOKENS.items():
            actual_id = vocab.get(tok)
            if actual_id != expected_id:
                logger.warning(
                    "Special token %s has id=%s (expected %s)",
                    tok,
                    actual_id,
                    expected_id,
                )

        self._hf_tokenizer = tokenizer
        self._trained = True
        logger.info("Tranc3Tokenizer trained via HF (vocab=%d)", len(vocab))
        return self

    def _train_python_bpe(self, texts: List[str]) -> "Tranc3Tokenizer":
        """Pure-Python byte-level BPE — no dependencies."""
        # Start with byte-level vocab (256 bytes) offset by special token count
        vocab: Dict[str, int] = dict(SPECIAL_TOKENS)
        for b in range(256):
            ch = chr(b)
            if ch not in vocab:
                vocab[ch] = len(vocab)

        # Tokenise corpus into byte-sequences
        corpus: List[List[str]] = []
        for text in texts:
            words = re.findall(r"\S+|\s", text)
            for word in words:
                corpus.append(list(word))

        merges: List[Tuple[str, str]] = []

        target = min(self.vocab_size, 32000)
        while len(vocab) < target:
            # Count pairs
            pair_freq: Dict[Tuple[str, str], int] = {}
            for word in corpus:
                for a, b in zip(word, word[1:], strict=False):  # type: ignore[assignment,index,arg-type]
                    pair_freq[(a, b)] = pair_freq.get((a, b), 0) + 1  # type: ignore[assignment,index,arg-type]

            if not pair_freq:
                break

            best = max(pair_freq, key=pair_freq.__getitem__)
            if pair_freq[best] < 2:
                break

            new_token = best[0] + best[1]
            vocab[new_token] = len(vocab)
            merges.append(best)

            # Apply merge
            new_corpus = []
            for word in corpus:
                new_word: List[str] = []
                i = 0
                while i < len(word):
                    if i < len(word) - 1 and word[i] == best[0] and word[i + 1] == best[1]:
                        new_word.append(new_token)
                        i += 2
                    else:
                        new_word.append(word[i])
                        i += 1
                new_corpus.append(new_word)
            corpus = new_corpus

        self._vocab = vocab
        self._id_to_token = {v: k for k, v in vocab.items()}
        self._merges = merges
        self._trained = True
        logger.info(
            "Tranc3Tokenizer trained via Python BPE (vocab=%d, merges=%d)",
            len(vocab),
            len(merges),
        )
        return self

    # ─── Encoding / decoding ───────────────────────────────────────────────────

    def encode(
        self,
        text: str,
        add_special_tokens: bool = True,
        personality: Optional[str] = None,
        max_length: Optional[int] = None,
        truncation: bool = True,
    ) -> List[int]:
        """Encode text to token IDs."""
        if hasattr(self, "_hf_tokenizer"):
            ids = self._hf_tokenizer.encode(text, add_special_tokens=False).ids
        else:
            ids = self._python_encode(text)

        if add_special_tokens:
            prefix = [BOS_ID]
            if personality:
                key = f"<p:{personality}>"
                if key in self._vocab:
                    prefix.append(self._vocab[key])
            ids = prefix + ids + [EOS_ID]

        if max_length and truncation and len(ids) > max_length:
            # Keep BOS and EOS, truncate middle
            if add_special_tokens:
                ids = ids[: max_length - 1] + [EOS_ID]
            else:
                ids = ids[:max_length]

        return ids

    def _python_encode(self, text: str) -> List[int]:
        """Apply BPE merges to encode text."""
        # Start with character/byte tokens
        tokens = list(text)

        for a, b in self._merges:
            merged = a + b
            new_tokens: List[str] = []
            i = 0
            while i < len(tokens):
                if i < len(tokens) - 1 and tokens[i] == a and tokens[i + 1] == b:
                    new_tokens.append(merged)
                    i += 2
                else:
                    new_tokens.append(tokens[i])
                    i += 1
            tokens = new_tokens

        return [self._vocab.get(t, UNK_ID) for t in tokens]

    def decode(self, ids: List[int], skip_special_tokens: bool = True) -> str:
        """Decode token IDs back to text."""
        if hasattr(self, "_hf_tokenizer"):
            return self._hf_tokenizer.decode(ids, skip_special_tokens=skip_special_tokens)

        tokens = []
        for i in ids:
            tok = self._id_to_token.get(i, "<unk>")
            if skip_special_tokens and tok in SPECIAL_TOKENS:
                continue
            tokens.append(tok)
        return "".join(tokens)

    def encode_chat(
        self,
        system: str,
        turns: List[Dict[str, str]],
        personality: Optional[str] = None,
        max_length: int = 512,
    ) -> List[int]:
        """Encode a chat conversation into the TRANC3 chat format.

        Format:  <bos> <p:personality> <sys> system <sep> <usr> user <sep> <ast> assistant <eos>
        """
        ids: List[int] = [BOS_ID]

        if personality:
            key = f"<p:{personality}>"
            if key in self._vocab:
                ids.append(self._vocab[key])

        sys_id = self._vocab.get("<sys>", SEP_ID)
        usr_id = self._vocab.get("<usr>", SEP_ID)
        ast_id = self._vocab.get("<ast>", SEP_ID)

        ids.append(sys_id)
        ids.extend(
            self._python_encode(system)
            if not hasattr(self, "_hf_tokenizer")
            else self._hf_tokenizer.encode(system, add_special_tokens=False).ids
        )
        ids.append(SEP_ID)

        for turn in turns:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            role_token = usr_id if role == "user" else ast_id
            ids.append(role_token)
            encoded = (
                self._python_encode(content)
                if not hasattr(self, "_hf_tokenizer")
                else self._hf_tokenizer.encode(content, add_special_tokens=False).ids
            )
            ids.extend(encoded)
            ids.append(SEP_ID)

        ids.append(EOS_ID)

        if len(ids) > max_length:
            ids = ids[: max_length - 1] + [EOS_ID]

        return ids

    # ─── Persistence ───────────────────────────────────────────────────────────

    def save(self, directory: Union[str, Path]) -> None:
        """Save tokenizer to directory."""
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)

        if hasattr(self, "_hf_tokenizer"):
            self._hf_tokenizer.save(str(path / "tokenizer.json"))

        meta = {
            "vocab_size": self.vocab_size,
            "vocab": self._vocab,
            "merges": self._merges,
            "special_tokens": SPECIAL_TOKENS,
        }
        (path / "tokenizer_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        logger.info("Tokenizer saved to %s", path)

    @classmethod
    def load(cls, directory: Union[str, Path]) -> "Tranc3Tokenizer":
        """Load tokenizer from directory."""
        path = Path(directory)

        meta_path = path / "tokenizer_meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"No tokenizer_meta.json in {path}")

        meta = json.loads(meta_path.read_text())
        tok = cls(vocab_size=meta["vocab_size"])
        tok._vocab = {k: int(v) for k, v in meta["vocab"].items()}
        tok._id_to_token = {v: k for k, v in tok._vocab.items()}
        tok._merges = [tuple(m) for m in meta["merges"]]
        tok._trained = True

        hf_path = path / "tokenizer.json"
        if hf_path.exists():
            try:
                from tokenizers import Tokenizer

                tok._hf_tokenizer = Tokenizer.from_file(str(hf_path))
                logger.info("Loaded HF tokenizer from %s", hf_path)
            except ImportError:
                logger.info("tokenizers not installed — using Python BPE")

        logger.info("Tranc3Tokenizer loaded (vocab=%d)", len(tok._vocab))
        return tok

    @classmethod
    def build_from_corpus(
        cls,
        corpus_paths: Optional[List[Union[str, Path]]] = None,
        texts: Optional[List[str]] = None,
        vocab_size: int = 8192,
        save_dir: Optional[Union[str, Path]] = None,
    ) -> "Tranc3Tokenizer":
        """Convenience: build tokenizer from file paths or text list, optionally save."""
        all_texts: List[str] = list(texts or [])

        for cp in corpus_paths or []:
            p = Path(cp)
            if p.exists():
                all_texts.append(p.read_text(encoding="utf-8", errors="replace"))

        if not all_texts:
            # Bootstrap with Tranc3 personality prompts so we have SOMETHING
            from src.core.dataset import PERSONALITY_SYSTEM_PROMPTS

            all_texts = list(PERSONALITY_SYSTEM_PROMPTS.values()) * 100

        tok = cls(vocab_size=vocab_size)
        tok.train(all_texts)

        if save_dir:
            tok.save(save_dir)

        return tok

    # ─── Properties ────────────────────────────────────────────────────────────

    @property
    def pad_token_id(self) -> int:
        return PAD_ID

    @property
    def bos_token_id(self) -> int:
        return BOS_ID

    @property
    def eos_token_id(self) -> int:
        return EOS_ID

    @property
    def unk_token_id(self) -> int:
        return UNK_ID

    def __len__(self) -> int:
        return len(self._vocab)

    def personality_token_id(self, personality: str) -> Optional[int]:
        return self._vocab.get(f"<p:{personality}>")
