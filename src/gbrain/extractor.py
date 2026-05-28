# FID: TRANC3-GBRAIN-003 | Version: 1.0.0 | Module: gbrain
"""
src/gbrain/extractor.py — Zero-cost knowledge extraction from agent interactions.

Extracts concepts, entities, and relationships from plaintext using
pure-Python techniques (no external NLP models required).

Techniques:
  - TF-IDF-style term salience scoring (no corpus required, uses IDF approximation)
  - Regex-based named entity detection (capitalized n-grams, quoted phrases)
  - Co-occurrence window edges (concepts that appear near each other are related)
  - Sentence boundary detection for context chunking
"""
from __future__ import annotations

import re
import string
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Tuple

# ---------------------------------------------------------------------------
# Common English stopwords (inline, zero-dependency)
# ---------------------------------------------------------------------------

_STOPWORDS: FrozenSet[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "during",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "shall", "can", "that", "this", "these", "those", "it", "its", "i", "you",
    "he", "she", "we", "they", "what", "which", "who", "when", "where", "how",
    "if", "then", "so", "not", "no", "as", "also", "more", "very", "just",
    "there", "here", "their", "our", "your", "my", "any", "all", "both",
    "each", "than", "too", "only", "other", "such", "same", "over", "after",
    "before", "between", "under", "while", "because", "however", "therefore",
})

# Minimum character length for a term to be considered a concept
_MIN_CONCEPT_LEN = 3

# Sliding window size for co-occurrence edge extraction
_CO_OCCUR_WINDOW = 5


@dataclass
class ExtractedConcept:
    """A single concept extracted from text."""

    text: str
    score: float  # 0.0–1.0 salience
    is_entity: bool  # True if looks like a named entity
    sentences: List[int] = field(default_factory=list)  # sentence indices containing this concept


@dataclass
class ExtractedEdge:
    """A directed relationship between two concepts."""

    source: str
    target: str
    relation: str = "co_occurs_with"
    weight: float = 1.0


@dataclass
class ExtractionResult:
    """Full result of knowledge extraction from a text pair."""

    concepts: List[ExtractedConcept]
    edges: List[ExtractedEdge]
    summary: str  # short extractive summary (first significant sentence)
    tags: List[str]


# ---------------------------------------------------------------------------
# Core extraction logic
# ---------------------------------------------------------------------------


def _sentence_tokenize(text: str) -> List[str]:
    """Split text into sentences using punctuation heuristics."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in parts if s.strip()]


def _tokenize(text: str) -> List[str]:
    """Lowercase word tokenizer, strips punctuation."""
    return [
        w.lower().strip(string.punctuation)
        for w in re.split(r"\s+", text)
        if w.strip(string.punctuation) and len(w.strip(string.punctuation)) >= _MIN_CONCEPT_LEN
    ]


def _is_entity_candidate(token: str) -> bool:
    """Heuristic: capitalized words or quoted phrases look like named entities."""
    return bool(re.match(r"^[A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)*$", token))


def _extract_capitalized_ngrams(text: str, max_n: int = 3) -> List[Tuple[str, bool]]:
    """Extract capitalized n-grams as named entity candidates."""
    words = text.split()
    entities: List[Tuple[str, bool]] = []
    i = 0
    while i < len(words):
        clean = words[i].strip(string.punctuation)
        if clean and _is_entity_candidate(clean):
            # Try to extend into a multi-word entity
            phrase_words = [clean]
            j = i + 1
            while j < len(words) and j < i + max_n:
                nxt = words[j].strip(string.punctuation)
                if nxt and _is_entity_candidate(nxt):
                    phrase_words.append(nxt)
                    j += 1
                else:
                    break
            # Take the longest match ≥ 1 word
            for length in range(len(phrase_words), 0, -1):
                phrase = " ".join(phrase_words[:length])
                if phrase.lower() not in _STOPWORDS:
                    entities.append((phrase, True))
                    break
            i = j if j > i + 1 else i + 1
        else:
            i += 1
    return entities


def _term_salience(tokens: List[str]) -> Dict[str, float]:
    """
    Compute per-term salience using TF × log(1 + len/df_proxy).

    No corpus needed — we use term length as a proxy for IDF
    (longer terms are rarer and more specific).
    """
    tf = Counter(t for t in tokens if t not in _STOPWORDS)
    if not tf:
        return {}
    max_tf = max(tf.values())
    salience = {}
    for term, count in tf.items():
        tf_norm = count / max_tf
        # Proxy IDF: longer terms are treated as more specific
        idf_proxy = math.log(1 + len(term))
        salience[term] = round(tf_norm * idf_proxy, 4)
    # Normalise to 0–1
    max_sal = max(salience.values(), default=1.0)
    return {t: v / max_sal for t, v in salience.items()} if max_sal > 0 else salience


def _co_occurrence_edges(
    tokens: List[str], window: int = _CO_OCCUR_WINDOW
) -> List[ExtractedEdge]:
    """Build edges from co-occurrence within a sliding window."""
    meaningful = [t for t in tokens if t not in _STOPWORDS and len(t) >= _MIN_CONCEPT_LEN]
    edges: Dict[Tuple[str, str], float] = {}
    for i, term in enumerate(meaningful):
        for j in range(i + 1, min(i + window, len(meaningful))):
            pair = (min(term, meaningful[j]), max(term, meaningful[j]))
            edges[pair] = edges.get(pair, 0.0) + 1.0
    max_w = max(edges.values(), default=1.0)
    return [
        ExtractedEdge(
            source=src, target=tgt, relation="co_occurs_with", weight=round(w / max_w, 4)
        )
        for (src, tgt), w in edges.items()
        if w >= 2  # require at least 2 co-occurrences
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


import math  # noqa: E402 — placed after pure-function definitions intentionally


def extract(prompt: str, response: str) -> ExtractionResult:
    """
    Extract concepts, entities, and relationships from a prompt+response pair.

    Returns an ExtractionResult with ranked concepts and co-occurrence edges.
    """
    combined = f"{prompt}\n{response}"
    sentences = _sentence_tokenize(combined)

    # All tokens for TF-IDF salience
    all_tokens = _tokenize(combined)
    salience_map = _term_salience(all_tokens)

    # Named entity candidates
    entity_pairs = _extract_capitalized_ngrams(combined)
    entity_set = {e.lower(): is_ent for e, is_ent in entity_pairs}

    # Build concept list from top-salience terms + all entities
    seen: set = set()
    concept_list: List[ExtractedConcept] = []

    # Add entities first (higher priority)
    for entity_text, is_ent in entity_pairs:
        key = entity_text.lower()
        if key in seen or key in _STOPWORDS or len(key) < _MIN_CONCEPT_LEN:
            continue
        seen.add(key)
        score = salience_map.get(key, 0.5)
        # Find which sentences contain this entity
        containing = [
            i for i, s in enumerate(sentences) if entity_text.lower() in s.lower()
        ]
        concept_list.append(
            ExtractedConcept(text=entity_text, score=max(score, 0.6), is_entity=True, sentences=containing)
        )

    # Add high-salience regular terms
    for term, score in sorted(salience_map.items(), key=lambda x: -x[1]):
        if term in seen or term in _STOPWORDS or len(term) < _MIN_CONCEPT_LEN:
            continue
        if score < 0.3:
            break
        seen.add(term)
        containing = [i for i, s in enumerate(sentences) if term in s.lower()]
        concept_list.append(
            ExtractedConcept(
                text=term,
                score=score,
                is_entity=entity_set.get(term, False),
                sentences=containing,
            )
        )

    # Co-occurrence edges on the token sequence
    edges = _co_occurrence_edges(all_tokens)

    # Extractive summary: first sentence with the highest concept density
    best_sent = sentences[0] if sentences else combined[:200]
    if len(sentences) > 1:
        def _density(s: str) -> int:
            sl = s.lower()
            return sum(1 for c in concept_list if c.text.lower() in sl)
        best_sent = max(sentences, key=_density)

    # Tags: top-5 entity names
    tags = [c.text for c in concept_list if c.is_entity][:5]

    return ExtractionResult(
        concepts=concept_list[:20],  # cap at 20 concepts per interaction
        edges=edges[:30],            # cap at 30 edges
        summary=best_sent[:500],
        tags=tags,
    )
