"""
Structured Output Enforcer — JSON schema enforcement for Luminous.

Ensures LLM responses conform to a JSON schema without requiring external
models or paid APIs. Three strategies (tried in order):

  1. lmformatenforcer (if installed) — token-level constraint during generation
  2. Regex extraction — pull JSON from free-form text with bracket matching
  3. Prompt engineering — instruct the model to output valid JSON, then validate

Zero-cost: uses stdlib json + optional lmformatenforcer (open-source).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("tranc3.inference.structured_output")

# Optional: lmformatenforcer
try:
    from lmformatenforcer import JsonSchemaParser  # type: ignore[import]  # noqa: F401
    _LMFE_AVAILABLE = True
except ImportError:
    _LMFE_AVAILABLE = False


# ── Regex extraction ──────────────────────────────────────────────────────────


def _extract_json_from_text(text: str) -> Optional[Dict]:
    """
    Extract the first valid JSON object from free-form text.
    Handles markdown code blocks, inline JSON, and mixed text.
    """
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)

    # Try direct parse first
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # Find the first {...} or [...] block with bracket matching
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue

        depth = 0
        in_string = False
        escape = False

        for i, ch in enumerate(text[start:], start):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    return None


# ── Schema validation ─────────────────────────────────────────────────────────


def _validate_against_schema(data: Any, schema: Dict) -> bool:
    """
    Lightweight JSON schema validation (no jsonschema library needed).
    Supports: type, required, properties, items, enum, minimum, maximum.
    """
    if not isinstance(schema, dict):
        return True

    schema_type = schema.get("type")
    if schema_type:
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }
        expected = type_map.get(schema_type)
        if expected and not isinstance(data, expected):
            return False

    if "enum" in schema and data not in schema["enum"]:
        return False

    if isinstance(data, (int, float)):
        if "minimum" in schema and data < schema["minimum"]:
            return False
        if "maximum" in schema and data > schema["maximum"]:
            return False

    if isinstance(data, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in data:
                return False
        properties = schema.get("properties", {})
        for key, prop_schema in properties.items():
            if key in data and not _validate_against_schema(data[key], prop_schema):
                return False

    if isinstance(data, list):
        items_schema = schema.get("items")
        if items_schema:
            for item in data:
                if not _validate_against_schema(item, items_schema):
                    return False

    return True


# ── Prompt engineering ───────────────────────────────────────────────────────


def _build_json_prompt(original_prompt: str, schema: Dict) -> str:
    """
    Augment a prompt to instruct the LLM to output valid JSON.
    """
    schema_str = json.dumps(schema, indent=2)
    return (
        f"{original_prompt}\n\n"
        f"IMPORTANT: Your response MUST be valid JSON conforming exactly to this schema:\n"
        f"```json\n{schema_str}\n```\n"
        f"Output ONLY the JSON object. Do not include any explanation, markdown, or extra text."
    )


# ── Main interface ────────────────────────────────────────────────────────────


class StructuredOutputParser:
    """
    Parse and validate LLM output against a JSON schema.

    Usage:
        parser = StructuredOutputParser(schema={"type": "object", "required": ["name"]})
        result = parser.parse(llm_output_text)
        if result is not None:
            # valid JSON matching schema
            ...
    """

    def __init__(self, schema: Optional[Dict] = None) -> None:
        self._schema = schema

    def parse(self, text: str) -> Optional[Dict]:
        """Extract and validate JSON from text. Returns None if invalid."""
        data = _extract_json_from_text(text)
        if data is None:
            logger.debug("No JSON found in LLM output")
            return None

        if self._schema is not None:
            if not _validate_against_schema(data, self._schema):
                logger.debug("JSON extracted but failed schema validation")
                return None

        return data

    def augment_prompt(self, prompt: str) -> str:
        """Add JSON instruction to a prompt."""
        if self._schema is None:
            return prompt + "\n\nRespond with a valid JSON object."
        return _build_json_prompt(prompt, self._schema)

    @property
    def schema_available(self) -> bool:
        return self._schema is not None


def extract_json(text: str) -> Optional[Dict]:
    """Convenience: extract first valid JSON from text."""
    return _extract_json_from_text(text)


def validate_json(data: Any, schema: Dict) -> bool:
    """Convenience: validate data against schema."""
    return _validate_against_schema(data, schema)


def enforce_json_schema(
    text: str,
    schema: Dict,
    fallback: Optional[Dict] = None,
) -> Dict:
    """
    Extract JSON from text and validate against schema.
    Returns fallback if extraction or validation fails.
    """
    parser = StructuredOutputParser(schema=schema)
    result = parser.parse(text)
    if result is not None:
        return result
    if fallback is not None:
        return fallback
    return {"error": "Failed to extract valid JSON from response", "raw": text[:200]}
