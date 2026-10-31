"""Strict, side-effect-free validation for Marketplace catalogue declarations.

This does not authorise outbound network access.
"""
from __future__ import annotations

import re
from typing import Any

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


def validate_connector_metadata(
    name: Any, slug: Any, tags: Any, rate_limit_per_min: Any
) -> None:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ValueError("name must be a non-empty string of at most 120 characters")
    if not isinstance(slug, str) or len(slug) > 80 or not _SLUG.fullmatch(slug):
        raise ValueError("slug must be lowercase alphanumeric with optional hyphens")
    if not isinstance(tags, list) or len(tags) > 32 or any(
        not isinstance(tag, str) or not 1 <= len(tag) <= 64 for tag in tags
    ):
        raise ValueError("tags must be a list of short strings")
    if (
        isinstance(rate_limit_per_min, bool)
        or not isinstance(rate_limit_per_min, int)
        or not 1 <= rate_limit_per_min <= 100000
    ):
        raise ValueError("rate_limit_per_min must be an integer between 1 and 100000")


def validate_endpoint_declaration(method: Any, path: Any) -> None:
    if not isinstance(method, str) or method.upper() not in _ALLOWED_METHODS:
        raise ValueError("Unsupported endpoint method")
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or path.startswith("//")
        or "?" in path
        or "#" in path
        or ".." in path
        or "\\" in path
        or any(ord(c) < 32 for c in path)
        or len(path) > 1024
    ):
        raise ValueError("Invalid endpoint path")
