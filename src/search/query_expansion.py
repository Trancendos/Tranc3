"""Query expansion — broaden recall by generating semantic query variants.

Strategies (in priority order, all zero-cost):
1. Synonym expansion via WordNet (nltk — free, local)
2. Paraphrase generation via a local T5 model (sentence-transformers)
3. Keyword extraction fallback (simple TF heuristic)

The expander returns the original query plus up to *n* expansions.
Callers should search with each variant and merge results before RRF.
"""

from __future__ import annotations

import logging
import re
from typing import List

logger = logging.getLogger("tranc3.search.query_expansion")


def _wordnet_synonyms(word: str) -> List[str]:
    try:
        from nltk.corpus import wordnet  # type: ignore

        synsets = wordnet.synsets(word)
        synonyms: List[str] = []
        for syn in synsets[:2]:
            for lemma in syn.lemmas()[:3]:
                name = lemma.name().replace("_", " ")
                if name.lower() != word.lower():
                    synonyms.append(name)
        return synonyms[:4]
    except Exception:  # noqa: BLE001
        return []


def _keywords(query: str) -> List[str]:
    """Extract non-stopword tokens as lightweight expansion candidates."""
    _STOP = {
        "a",
        "an",
        "the",
        "is",
        "in",
        "on",
        "at",
        "for",
        "to",
        "of",
        "and",
        "or",
        "but",
        "with",
        "by",
        "from",
        "as",
        "are",
        "was",
        "were",
        "be",
        "been",
        "has",
        "have",
        "had",
    }
    tokens = re.findall(r"\w+", query.lower())
    return [t for t in tokens if t not in _STOP and len(t) > 2]


class QueryExpander:
    """Generate expanded query variants from a single input query.

    expand() always returns the original query as the first element so
    callers can union-search without special-casing.
    """

    def expand(self, query: str, n: int = 3) -> List[str]:
        variants: List[str] = [query]
        if not query.strip():
            return variants

        # WordNet synonym substitution
        keywords = _keywords(query)
        for kw in keywords[:3]:
            synonyms = _wordnet_synonyms(kw)
            for syn in synonyms[:1]:
                candidate = re.sub(rf"\b{re.escape(kw)}\b", syn, query, count=1)
                if candidate not in variants:
                    variants.append(candidate)
                    if len(variants) >= n + 1:
                        return variants

        # Paraphrase via T5 (optional — requires transformers)
        if len(variants) < n + 1:
            try:
                from transformers import T5ForConditionalGeneration, T5Tokenizer  # type: ignore

                if not hasattr(self, "_t5_model"):
                    self._t5_tokenizer = T5Tokenizer.from_pretrained("t5-small")  # type: ignore
                    self._t5_model = T5ForConditionalGeneration.from_pretrained("t5-small")  # type: ignore

                prompt = f"paraphrase: {query} </s>"
                inputs = self._t5_tokenizer(
                    prompt, return_tensors="pt", max_length=64, truncation=True
                )  # type: ignore
                outputs = self._t5_model.generate(  # type: ignore
                    **inputs,
                    num_return_sequences=min(2, n + 1 - len(variants)),
                    num_beams=4,
                    max_length=64,
                )
                for out in outputs:
                    text = self._t5_tokenizer.decode(out, skip_special_tokens=True)  # type: ignore
                    if text not in variants:
                        variants.append(text)
            except Exception as exc:  # noqa: BLE001
                logger.debug("T5 paraphrase unavailable: %s", exc)

        return variants[: n + 1]
