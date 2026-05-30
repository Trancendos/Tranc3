# src/core/multilingual_tokenizer.py
# TRANC3 Full Multilingual Engine
from __future__ import annotations

import logging
from typing import Dict, List

from Dimensional.sanitize import sanitize_for_log

try:
    import langdetect as langdetect

    _LANGDETECT_AVAILABLE = True
except ImportError:
    langdetect = None  # type: ignore[assignment]
    _LANGDETECT_AVAILABLE = False

try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:
    import types as _types

    torch = _types.SimpleNamespace()  # type: ignore[assignment]
    _TORCH_AVAILABLE = False

try:
    from transformers import AutoTokenizer

    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    AutoTokenizer = None  # type: ignore[assignment]
    _TRANSFORMERS_AVAILABLE = False

logger = logging.getLogger(__name__)

LANGUAGE_CODES = {
    "en": "english",
    "es": "spanish",
    "fr": "french",
    "de": "german",
    "zh": "chinese",
    "ja": "japanese",
    "ko": "korean",
    "ar": "arabic",
    "ru": "russian",
    "pt": "portuguese",
    "it": "italian",
    "nl": "dutch",
    "pl": "polish",
    "tr": "turkish",
    "vi": "vietnamese",
    "th": "thai",
    "hi": "hindi",
    "bn": "bengali",
    "ur": "urdu",
    "fa": "persian",
    "sv": "swedish",
    "da": "danish",
    "fi": "finnish",
    "no": "norwegian",
    "cs": "czech",
    "sk": "slovak",
    "ro": "romanian",
    "hu": "hungarian",
    "bg": "bulgarian",
    "hr": "croatian",
    "sr": "serbian",
    "uk": "ukrainian",
    "el": "greek",
    "he": "hebrew",
    "id": "indonesian",
    "ms": "malay",
    "tl": "tagalog",
    "sw": "swahili",
    "am": "amharic",
    "yo": "yoruba",
    "ha": "hausa",
    "ig": "igbo",
    "zu": "zulu",
    "af": "afrikaans",
    "ca": "catalan",
    "eu": "basque",
    "gl": "galician",
    "cy": "welsh",
    "is": "icelandic",
    "mt": "maltese",
    "sq": "albanian",
    "mk": "macedonian",
}


class MultilingualTokenizer:
    """
    Multilingual tokenizer supporting 50+ languages
    Uses mBERT/XLM-RoBERTa as backbone
    """

    def __init__(self, config):
        self.config = config
        self.supported_languages = list(LANGUAGE_CODES.keys())
        self.primary_language = getattr(config, "primary_language", "en")
        self.cache_dir = getattr(config, "cache_dir", "./cache")
        self.max_length = getattr(config, "max_sequence_length", 512)

        # Load tokenizer
        model_name = getattr(config, "tokenizer_model", "bert-base-multilingual-cased")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(  # nosec B615 — revision pinning via cache_dir; model pinned in config
                model_name, cache_dir=self.cache_dir
            )
            logger.info("Tokenizer loaded: %s", sanitize_for_log(model_name))
        except Exception as e:
            logger.warning("Tokenizer load failed: %s, using mock", sanitize_for_log(e))
            self.tokenizer = None

        # Language detection
        self.lang_detector = LanguageDetector()

        # Translation cache
        self._translation_cache: Dict[str, str] = {}

    def encode(self, text: str, language: str = "en", return_tensors: bool = True) -> Dict:
        """Encode text to token IDs"""
        if self.tokenizer is None:
            return self._mock_encode(text)

        encoded = self.tokenizer(
            text,
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt" if return_tensors else None,
        )
        return {
            "input_ids": encoded["input_ids"],
            "attention_mask": encoded["attention_mask"],
            "language": language,
            "token_count": encoded["input_ids"].shape[-1],
        }

    def decode(self, token_ids: torch.Tensor, skip_special_tokens: bool = True) -> str:
        """Decode token IDs to text"""
        if self.tokenizer is None:
            return "Mock decoded text"
        return self.tokenizer.decode(token_ids[0], skip_special_tokens=skip_special_tokens)

    def detect_language(self, text: str) -> str:
        """Detect language of input text"""
        return self.lang_detector.detect(text)

    def get_language_embedding_id(self, language: str) -> int:
        """Get language embedding ID"""
        langs = list(LANGUAGE_CODES.keys())
        return langs.index(language) if language in langs else 0

    def _mock_encode(self, text: str) -> Dict:
        """Mock encoding when tokenizer unavailable"""
        ids = torch.tensor([[ord(c) % 30000 for c in text[: self.max_length]]])
        mask = torch.ones_like(ids)
        return {
            "input_ids": ids,
            "attention_mask": mask,
            "language": "en",
            "token_count": len(text),
        }

    def batch_encode(self, texts: List[str], languages: List[str]) -> Dict:
        """Batch encode multiple texts"""
        results = [self.encode(t, lang) for t, lang in zip(texts, languages, strict=False)]
        return {
            "input_ids": torch.cat([r["input_ids"] for r in results]),
            "attention_mask": torch.cat([r["attention_mask"] for r in results]),
            "languages": languages,
        }


class LanguageDetector:
    def detect(self, text: str) -> str:
        try:
            return langdetect.detect(text)
        except Exception:
            return "en"

    def detect_with_confidence(self, text: str) -> List[Dict]:
        try:
            from langdetect import detect_langs

            results = detect_langs(text)
            return [
                {
                    "language": str(r).split(":")[0],
                    "confidence": float(str(r).split(":")[1]),
                }
                for r in results
            ]
        except Exception:
            return [{"language": "en", "confidence": 1.0}]
