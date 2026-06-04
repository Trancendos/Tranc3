"""Query Intent LLM — TranceX Phase 8

SHI-powered Natural Language to NRC DSL conversion. Translates user
intent expressed in natural language into Nested Relational Calculus
query definitions, with validation, explanation, and iterative refinement.

All dependencies are 0-cost (free/open-source).
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class IntentCategory(Enum):
    """Categories of user query intent."""

    SELECT = "select"  # Retrieve data
    AGGREGATE = "aggregate"  # Sum, count, avg
    FILTER = "filter"  # Where-like filtering
    JOIN = "join"  # Combine relations
    NEST = "nest"  # Nested collection construction
    UNNEST = "unnest"  # Flatten nested collections
    SHRED = "shred"  # Deep nested processing
    COMPARE = "compare"  # Comparative analysis
    TEMPORAL = "temporal"  # Time-based queries
    BIOMEDICAL = "biomedical"  # Genomic/clinical queries
    DRONE = "drone"  # Aerial/drone sensor queries
    EDGE = "edge"  # Edge computing queries


class ConversionStatus(Enum):
    """Status of NL→NRC conversion."""

    SUCCESS = "success"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"
    NEEDS_REFINEMENT = "needs_refinement"


@dataclass
class NRCQuery:
    """A parsed NRC query definition."""

    query_id: str = ""
    dsl: str = ""
    intent: IntentCategory = IntentCategory.SELECT
    relations: List[str] = field(default_factory=list)
    projections: List[str] = field(default_factory=list)
    filters: List[str] = field(default_factory=list)
    joins: List[Dict[str, str]] = field(default_factory=list)
    nesting: List[Dict[str, Any]] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    raw_intent: str = ""

    def __post_init__(self):
        if not self.query_id:
            self.query_id = f"nrc-{uuid.uuid4().hex[:8]}"

    def to_dsl_string(self) -> str:
        """Generate NRC DSL string from parsed components."""
        parts = []

        if self.projections:
            proj_str = ", ".join(self.projections)
            parts.append(f"{{ {proj_str} }}")

        if self.relations:
            parts.append(f"FROM {', '.join(self.relations)}")

        if self.filters:
            filter_str = " AND ".join(self.filters)
            parts.append(f"WHERE {filter_str}")

        if self.joins:
            for join in self.joins:
                parts.append(f"JOIN {join.get('relation', '')} ON {join.get('condition', '')}")

        if self.nesting:
            for nest in self.nesting:
                parts.append(f"NEST {nest.get('field', '')} AS {nest.get('alias', '')}")

        return " ".join(parts) if parts else self.dsl


@dataclass
class ConversionResult:
    """Result of NL→NRC conversion."""

    conversion_id: str = ""
    status: ConversionStatus = ConversionStatus.SUCCESS
    query: Optional[NRCQuery] = None
    alternative_queries: List[NRCQuery] = field(default_factory=list)
    explanation: str = ""
    confidence: float = 0.0
    ambiguities: List[str] = field(default_factory=list)
    refinement_suggestions: List[str] = field(default_factory=list)
    processing_time_ms: float = 0.0
    llm_model: str = ""
    fallback_used: bool = False

    def __post_init__(self):
        if not self.conversion_id:
            self.conversion_id = f"conv-{uuid.uuid4().hex[:8]}"


class IntentParser:
    """Parses natural language intent into structured NRC components.

    Uses pattern matching and heuristics to extract query semantics
    from natural language input. Works with or without LLM support.
    """

    # Keywords for intent classification
    INTENT_KEYWORDS = {
        IntentCategory.SELECT: ["show", "get", "find", "list", "retrieve", "fetch", "select"],
        IntentCategory.AGGREGATE: [
            "count",
            "sum",
            "average",
            "total",
            "min",
            "max",
            "aggregate",
            "how many",
        ],
        IntentCategory.FILTER: ["where", "filter", "only", "with", "having", "condition"],
        IntentCategory.JOIN: ["join", "combine", "merge", "link", "connect", "relate", "with"],
        IntentCategory.NEST: ["nest", "group", "collect", "bundle", "nested"],
        IntentCategory.UNNEST: ["unnest", "flatten", "expand", "spread", "unpack"],
        IntentCategory.SHRED: ["shred", "deep", "recursive", "traverse", "walk"],
        IntentCategory.COMPARE: ["compare", "versus", "difference", "contrast", "against"],
        IntentCategory.TEMPORAL: [
            "when",
            "timeline",
            "over time",
            "trend",
            "history",
            "before",
            "after",
        ],
        IntentCategory.BIOMEDICAL: [
            "genomic",
            "gene",
            "patient",
            "clinical",
            "sequence",
            "variant",
            "dna",
            "protein",
        ],
        IntentCategory.DRONE: [
            "drone",
            "sensor",
            "flight",
            "aerial",
            "altitude",
            "coordinates",
            "swarm",
        ],
        IntentCategory.EDGE: ["edge", "iot", "device", "wasm", "offline", "latency"],
    }

    # Relation name patterns
    RELATION_PATTERN = re.compile(r"\b(from|in|of)\s+(\w+)\b", re.IGNORECASE)

    # Projection patterns
    PROJECTION_PATTERN = re.compile(
        r"\b(show|select|get|display)\s+([\w\s,]+?)(?:\s+from|\s+where|\s+in|$)", re.IGNORECASE,
    )

    # Filter patterns
    FILTER_PATTERN = re.compile(
        r"\b(where|with|having|filter)\s+([\w\s<>=!]+?)(?:\s+and|\s+or|\s+join|$)", re.IGNORECASE,
    )

    def classify_intent(self, text: str) -> Tuple[IntentCategory, float]:
        """Classify the intent category of a natural language query."""
        text_lower = text.lower()
        scores: Dict[IntentCategory, float] = {}

        for category, keywords in self.INTENT_KEYWORDS.items():
            score = sum(1.0 for kw in keywords if kw in text_lower)
            if score > 0:
                # Weight by keyword rarity (longer keywords = more specific)
                weighted = sum(len(kw.split()) * 0.5 + 0.5 for kw in keywords if kw in text_lower)
                scores[category] = weighted

        if not scores:
            return IntentCategory.SELECT, 0.3

        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        total = sum(scores.values())
        confidence = scores[best] / total if total > 0 else 0.3
        return best, min(0.95, confidence)

    def extract_relations(self, text: str) -> List[str]:
        """Extract relation names from natural language text."""
        relations = []
        for match in self.RELATION_PATTERN.finditer(text):
            rel = match.group(2)
            if rel.lower() not in ("the", "a", "an", "this", "that", "all", "some"):
                relations.append(rel)
        return list(set(relations))

    def extract_projections(self, text: str) -> List[str]:
        """Extract projection fields from natural language text."""
        projections = []
        for match in self.PROJECTION_PATTERN.finditer(text):
            fields = match.group(2).strip()
            for f in fields.split(","):
                f = f.strip()
                if f and f.lower() not in ("the", "a", "an", "all"):
                    projections.append(f)
        return projections

    def extract_filters(self, text: str) -> List[str]:
        """Extract filter conditions from natural language text."""
        filters = []
        for match in self.FILTER_PATTERN.finditer(text):
            condition = match.group(2).strip()
            if condition:
                filters.append(condition)
        return filters


class LLMQueryConverter:
    """LLM-powered natural language to NRC query converter.

    Uses SHI gateway for inference with prompt engineering.
    Falls back to heuristic parsing when LLM is unavailable.
    """

    SYSTEM_PROMPT = """You are an expert NRC (Nested Relational Calculus) query translator for the TranceX ecosystem. 
Convert natural language queries into valid NRC DSL format.

NRC DSL syntax:
- Selection: { field1, field2 } FROM relation WHERE condition
- Nesting: { field1, NEST inner_rel AS nested } FROM outer_rel
- Aggregation: AGG(COUNT, field) FROM relation WHERE condition GROUP BY field
- Shredding: SHRED nested_field FROM relation WHERE condition

Rules:
1. Always identify the primary relations mentioned
2. Preserve nested collection semantics
3. Use proper NRC operators (NEST, UNNEST, SHRED)
4. Include type annotations where possible
5. Return valid NRC DSL as a JSON object with keys: dsl, intent, relations, projections, filters, joins, nesting

Example input: "Show all patients with genomic variants in BRCA1 gene"
Example output:
{
  "dsl": "{ patient_id, NEST variants AS genomic_variants } FROM patients WHERE gene = 'BRCA1'",
  "intent": "biomedical",
  "relations": ["patients", "variants"],
  "projections": ["patient_id"],
  "filters": ["gene = 'BRCA1'"],
  "joins": [],
  "nesting": [{"field": "variants", "alias": "genomic_variants"}]
}
"""

    def __init__(self, shi_gateway=None, model: str = "trancex-nrc"):
        self.shi_gateway = shi_gateway
        self.model = model
        self.intent_parser = IntentParser()
        self._conversion_history: List[ConversionResult] = []

    async def convert(self, natural_language: str) -> ConversionResult:
        """Convert a natural language query to NRC DSL."""
        start = time.monotonic()

        # Try LLM conversion first
        if self.shi_gateway:
            try:
                result = await self._llm_convert(natural_language)
                if result and result.status in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL):
                    self._conversion_history.append(result)
                    return result
            except Exception as e:
                logger.warning(f"LLM conversion failed, using heuristic: {e}")

        # Fallback to heuristic parsing
        result = self._heuristic_convert(natural_language)
        result.fallback_used = True
        result.processing_time_ms = (time.monotonic() - start) * 1000
        self._conversion_history.append(result)
        return result

    async def _llm_convert(self, natural_language: str) -> Optional[ConversionResult]:
        """Use LLM to convert natural language to NRC."""
        prompt = f'{self.SYSTEM_PROMPT}\n\nConvert this query: "{natural_language}"'

        if self.shi_gateway and hasattr(self.shi_gateway, "infer"):
            response = await self.shi_gateway.infer(prompt)
            response_text = response if isinstance(response, str) else json.dumps(response)
        else:
            return None

        try:
            # Parse LLM response
            parsed = json.loads(response_text)
            query = NRCQuery(
                dsl=parsed.get("dsl", ""),
                intent=IntentCategory(parsed.get("intent", "select")),
                relations=parsed.get("relations", []),
                projections=parsed.get("projections", []),
                filters=parsed.get("filters", []),
                joins=parsed.get("joins", []),
                nesting=parsed.get("nesting", []),
                raw_intent=natural_language,
                confidence=0.9,
            )

            return ConversionResult(
                status=ConversionStatus.SUCCESS,
                query=query,
                explanation=f"Converted via LLM ({self.model})",
                confidence=0.9,
                llm_model=self.model,
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM NRC response: {e}")
            return None

    def _heuristic_convert(self, natural_language: str) -> ConversionResult:
        """Heuristic NL→NRC conversion when LLM is unavailable."""
        intent, confidence = self.intent_parser.classify_intent(natural_language)
        relations = self.intent_parser.extract_relations(natural_language)
        projections = self.intent_parser.extract_projections(natural_language)
        filters = self.intent_parser.extract_filters(natural_language)

        # Build NRC DSL from parsed components
        dsl_parts = []

        if projections:
            proj_str = ", ".join(projections)
            dsl_parts.append(f"{{ {proj_str} }}")
        else:
            dsl_parts.append("{ * }")

        if relations:
            dsl_parts.append(f"FROM {', '.join(relations)}")

        if filters:
            filter_str = " AND ".join(filters)
            dsl_parts.append(f"WHERE {filter_str}")

        dsl = " ".join(dsl_parts)

        # Detect nesting intent
        nesting = []
        if intent in (IntentCategory.NEST, IntentCategory.BIOMEDICAL):
            for rel in relations[1:] if len(relations) > 1 else []:
                nesting.append({"field": rel, "alias": f"nested_{rel}"})
                dsl = dsl.replace(f", {rel}", f", NEST {rel} AS nested_{rel}")

        # Detect ambiguities
        ambiguities = []
        if len(relations) > 2:
            ambiguities.append("Multiple relations detected; join conditions may be ambiguous")
        if confidence < 0.5:
            ambiguities.append("Low confidence in intent classification")

        query = NRCQuery(
            dsl=dsl,
            intent=intent,
            relations=relations,
            projections=projections,
            filters=filters,
            nesting=nesting,
            raw_intent=natural_language,
            confidence=confidence,
        )

        status = ConversionStatus.SUCCESS
        if ambiguities:
            status = ConversionStatus.AMBIGUOUS
        elif confidence < 0.5:
            status = ConversionStatus.NEEDS_REFINEMENT

        return ConversionResult(
            status=status,
            query=query,
            explanation=f"Heuristic conversion with {confidence:.0%} confidence",
            confidence=confidence,
            ambiguities=ambiguities,
            refinement_suggestions=self._generate_refinement_suggestions(query)
            if ambiguities
            else [],
            fallback_used=True,
        )

    def _generate_refinement_suggestions(self, query: NRCQuery) -> List[str]:
        """Generate suggestions for refining an ambiguous query."""
        suggestions = []
        if not query.relations:
            suggestions.append(
                "Specify which data relations to query (e.g., 'FROM patients, variants')",
            )
        if len(query.relations) > 1 and not query.joins:
            suggestions.append("Specify join conditions between relations (e.g., 'ON patient_id')")
        if not query.filters and query.intent == IntentCategory.FILTER:
            suggestions.append("Add filter conditions (e.g., 'WHERE gene = BRCA1')")
        if query.intent == IntentCategory.BIOMEDICAL and not query.nesting:
            suggestions.append("Consider using NEST for genomic variant collections")
        return suggestions

    def get_conversion_history(self) -> List[ConversionResult]:
        """Get history of all conversions."""
        return self._conversion_history.copy()

    def get_stats(self) -> Dict[str, Any]:
        """Get converter statistics."""
        if not self._conversion_history:
            return {"total_conversions": 0}

        success = sum(1 for r in self._conversion_history if r.status == ConversionStatus.SUCCESS)
        fallback = sum(1 for r in self._conversion_history if r.fallback_used)
        total = len(self._conversion_history)

        return {
            "total_conversions": total,
            "success_rate": success / total if total > 0 else 0,
            "fallback_rate": fallback / total if total > 0 else 0,
            "avg_confidence": sum(r.confidence for r in self._conversion_history) / total,
            "avg_processing_time_ms": sum(r.processing_time_ms for r in self._conversion_history)
            / total,
        }


class QueryIntentService:
    """High-level query intent service for the TranceX ecosystem.

    Integrates NL→NRC conversion with the genetic optimizer, vector
    plan cache, and adaptive loop for end-to-end query optimization.
    """

    def __init__(self, shi_gateway=None, vector_cache=None):
        self.converter = LLMQueryConverter(shi_gateway=shi_gateway)
        self.vector_cache = vector_cache
        self._query_history: List[Dict[str, Any]] = []

    async def process_natural_language_query(
        self, natural_language: str, context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process a natural language query end-to-end.

        1. Convert NL → NRC DSL
        2. Check vector plan cache for similar queries
        3. If cached plan found, return it
        4. Otherwise, trigger genetic optimization
        """
        # Convert NL to NRC
        conversion = await self.converter.convert(natural_language)

        if not conversion.query:
            return {
                "status": "failed",
                "error": "Could not convert natural language to NRC",
                "conversion": conversion.__dict__,
            }

        query = conversion.query
        result = {
            "conversion": {
                "id": conversion.conversion_id,
                "status": conversion.status.value,
                "confidence": conversion.confidence,
                "explanation": conversion.explanation,
            },
            "nrc_query": {
                "id": query.query_id,
                "dsl": query.to_dsl_string(),
                "intent": query.intent.value,
                "relations": query.relations,
            },
        }

        # Check vector plan cache
        if self.vector_cache:
            similar = self.vector_cache.search_similar(query.dsl, top_k=3)
            if similar and similar[0].similarity_score >= 0.85:
                best = similar[0]
                result["cached_plan"] = {
                    "plan_id": best.cached_plan.plan_id,
                    "similarity": best.similarity_score,
                    "fitness": best.cached_plan.fitness,
                    "exact_match": best.exact_match,
                }
                result["status"] = "cached"
                self._query_history.append(result)
                return result

        result["status"] = "new_query"
        result["optimization_required"] = True
        self._query_history.append(result)
        return result

    def get_service_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "converter_stats": self.converter.get_stats(),
            "total_queries": len(self._query_history),
            "cache_enabled": self.vector_cache is not None,
        }
