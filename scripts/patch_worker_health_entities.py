#!/usr/bin/env python3
"""Inject health_entity_block() into worker /health responses (replace or add)."""

from __future__ import annotations

import re
from pathlib import Path

IMPORT_LINE = "from src.entities.health_metadata import health_entity_block\n"

NAME_RE = re.compile(r'^(?:WORKER_NAME|SERVICE_NAME)\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)

_PORT_PATTERNS = (
    re.compile(r"WORKER_PORT\s*=\s*int\(os\.environ\.get\([^,]+,\s*['\"](\d+)"),
    re.compile(r"WORKER_PORT\s*=\s*(\d+)"),
    re.compile(r"PORT\s*=\s*int\(os\.environ\.get\([^,]+,\s*['\"](\d+)"),
    re.compile(r"PORT\s*=\s*(\d+)"),
    re.compile(r"port\s*=\s*(\d+).*uvicorn\.run", re.DOTALL),
)


def _port_from_text(text: str) -> int | None:
    for pat in _PORT_PATTERNS:
        m = pat.search(text)
        if m:
            return int(m.group(1))
    return None


def _port_and_service(text: str) -> tuple[int | None, str]:
    port = _port_from_text(text)
    name_m = NAME_RE.search(text)
    if name_m:
        service = f'"{name_m.group(1)}"'
    elif "WORKER_NAME" in text:
        service = "WORKER_NAME"
    elif "SERVICE_NAME" in text:
        service = "SERVICE_NAME"
    else:
        service = '"unknown"'
    return port, service


def _add_import(text: str) -> str:
    if IMPORT_LINE.strip() in text:
        return text
    if "from __future__ import" in text:
        return re.sub(
            r"(from __future__ import[^\n]+\n)",
            r"\1" + IMPORT_LINE,
            text,
            count=1,
        )
    return IMPORT_LINE + text


def _inject_into_health_return(text: str, port: int, service: str) -> str:
    """Add entity key to the first dict returned by @app.get('/health')."""
    if '"entity":' in text and "health_entity_block" in text:
        return text

    health_fn = re.search(
        r'@app\.get\(["\']/health["\']\)\s*\nasync def health[^{]*\{',
        text,
    )
    if not health_fn:
        return text

    start = health_fn.end()
    # Find first `return {` after health function
    ret = re.search(r"\breturn\s*\{", text[start:])
    if not ret:
        return text

    ret_start = start + ret.start()
    brace = text.find("{", ret_start)
    if brace < 0:
        return text

    # Insert after opening brace of return dict
    insert = f'\n        "entity": health_entity_block({port}, {service}),'
    # Avoid double insert
    snippet = text[brace : brace + 400]
    if "health_entity_block" in snippet:
        return text

    return text[: brace + 1] + insert + text[brace + 1 :]


def patch_file(path: Path) -> bool:
    text = path.read_text()
    if '@app.get("/health")' not in text and "@app.get('/health')" not in text:
        return False

    port, service = _port_and_service(text)
    if port is None:
        print(f"  skip (no PORT): {path}")
        return False

    original = text
    text = _inject_into_health_return(text, port, service)

    if text == original:
        print(f"  skip (no change): {path}")
        return False

    text = _add_import(text)
    path.write_text(text)
    print(f"  patched: {path}")
    return True


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    workers = sorted((root / "workers").glob("*/worker.py"))
    count = 0
    for path in workers:
        if patch_file(path):
            count += 1
    print(f"Done. {count} files updated.")


if __name__ == "__main__":
    main()
