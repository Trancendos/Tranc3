#!/usr/bin/env python3
"""Emit a CycloneDX ML-BOM for consumed AI models, and catch undeclared ones.

WHY THIS EXISTS

The 2026 OSSRA report identifies AI models as an emerging attack and compliance
surface with a specific property that makes it awkward: models are frequently
present in a codebase in ways that ordinary dependency scanning cannot see. They
are not declared in a manifest. They arrive as bare strings -- an env default, an
adapter constant, a provider's capability list -- and a package-manager scan walks
straight past them. Black Duck reports 49% of organisations ship open source AI/ML
models in their products, and that models may be embedded, undeclared, or modified
from origin.

This estate is a live example. Nothing in `requirements.txt` or any `package.json`
mentions `llama3.2:1b`, `all-MiniLM-L6-v2` or `t5-small`, yet all three are models
the platform depends on at runtime, each with its own licence.

THE FINDING THAT MOTIVATED THE LICENCE COLUMN

Of the models this estate consumes, four are Apache-2.0 and two are not: the Llama
family carries Meta's **Community Licence**, which is not an OSI-approved open
source licence. It imposes an acceptable use policy, a monthly-active-user
threshold above which a separate licence must be negotiated, and an attribution
requirement -- "Built with Llama" -- that applies to products built with it.

None of those obligations follow from Apache-2.0 habits, and nothing in the
codebase signalled the difference. That is precisely OSSRA's point about model
licences being "unclear or misunderstood", and it is why the inventory records a
verified licence per model rather than an assumption.

WHY DECLARED INVENTORY + DRIFT CHECK, RATHER THAN PURE DETECTION

Pure detection cannot distinguish a model the platform depends on from one merely
named in a comment, a docstring, or a provider's advertised capability list. It
would produce a noisy BOM that nobody trusts.

Pure declaration rots the moment someone adds a model and forgets the file.

So: the inventory is declared and reviewed in `config/ai_models.yaml`, and this
script checks the code against it. A model identifier appearing in code but not in
the inventory is reported as drift. That is the same reviewed-versus-unexamined
split already used by `SECURITY_ALERT_REGISTER.md` for vulnerabilities and
`OBSOLESCENCE-ACCEPTED.md` for dormant dependencies, applied to a third surface.

RELATIONSHIP TO BOM-MATRIX.md

`docs/governance/BOM-MATRIX.md` assessed AI-BOM on 2026-07-31 as "a genuine gap --
and premature", because an AI-BOM describing training-data provenance and
foundational-model lineage would document a model that does not exist: Tranc3Engine
runs in bootstrap mode with no trained weights.

That judgement is not reversed here. It was right about models we *train*, and
incomplete about models we *consume*. A consumed model still has a licence, an
origin, and an execution location, and the EU AI Act asks about all three
regardless of whether anyone fine-tuned anything.

USAGE

    python scripts/ai_bom.py                 # write the ML-BOM
    python scripts/ai_bom.py --check         # CI: fail on undeclared model drift

Output is CycloneDX 1.6 JSON at `logs/ai-bom.cyclonedx.json`, the same format
`.forgejo/workflows/security-scan.yml` already produces via syft, so it lands in
the existing SBOM pipeline and Dependency-Track upload rather than beside it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INVENTORY = REPO / "config" / "ai_models.yaml"
OUTPUT = REPO / "logs" / "ai-bom.cyclonedx.json"

# Directories worth scanning for model references.
SCAN_DIRS = ("src", "workers", "api.py")

# Patterns for model identifiers this estate could plausibly depend on. Deliberately
# narrow -- broad matching against a codebase this size produces mostly prose.
# Test trees are excluded. A model named in a fixture is not a dependency, and
# treating it as one is how the drift check becomes noise people learn to ignore.
# (A first pass claimed this in a comment while scanning tests anyway, which is
# how `llama3.2:user` -- a colon-delimited cache key in a test string -- surfaced
# as a model.)
EXCLUDED_PARTS = ("tests", "test", "__pycache__", "node_modules")

MODEL_PATTERNS = (
    # Ollama-style tags: llama3.2:1b, mistral:7b, qwen2.5:0.5b, llama3:70b.
    # The tag must look like a parameter size, which is what an Ollama tag
    # actually is. Accepting any `word:word` matched two things that are not
    # models: f-string format specs (`{phi:.2f}`) and delimited cache keys
    # (`default:llama3.2:user:...`).
    re.compile(r"\b((?:llama|mistral|qwen|phi|gemma|deepseek)[\w.]*:[\d.]+[bBmM])\b", re.I),
    # Hugging Face repo ids under known model orgs
    re.compile(r"\b((?:sentence-transformers|meta-llama|google-t5|nomic-ai)/[\w.-]+)\b"),
    # Bare well-known model names used as defaults
    re.compile(r"\b(all-MiniLM-L6-v2|nomic-embed-text|t5-small)\b"),
)


def _load_inventory() -> dict:
    """Parse config/ai_models.yaml, preferring PyYAML and degrading loudly."""
    try:
        import yaml
    except ImportError:
        raise SystemExit(
            "[ERROR] PyYAML is required to read the model inventory.\n"
            "        Install it, or run this from an environment that has it."
        ) from None
    if not INVENTORY.is_file():
        raise SystemExit(f"[ERROR] model inventory not found: {INVENTORY}")
    data = yaml.safe_load(INVENTORY.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise SystemExit(f"[ERROR] {INVENTORY} has no 'models' list")
    return data


def _declared_names(inventory: dict) -> set[str]:
    """Every id and alias in the inventory, lowercased for comparison."""
    names: set[str] = set()
    for block in ("models", "hosted_providers"):
        for entry in inventory.get(block) or []:
            if entry.get("id"):
                names.add(str(entry["id"]).lower())
            for alias in entry.get("aliases") or []:
                names.add(str(alias).lower())
    return names


def _scan_for_models() -> dict[str, list[str]]:
    """Model identifier -> the files mentioning it, across the scanned tree."""
    found: dict[str, set[str]] = {}
    targets = [REPO / d for d in SCAN_DIRS]
    for target in targets:
        if not target.exists():
            continue
        files = [target] if target.is_file() else sorted(target.rglob("*.py"))
        for path in files:
            if any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            for pattern in MODEL_PATTERNS:
                for match in pattern.findall(text):
                    found.setdefault(match, set()).add(str(path.relative_to(REPO)))
    return {name: sorted(paths) for name, paths in sorted(found.items())}


def _git_describe() -> str:
    """Best-effort version label; 'unknown' rather than a guess when git is absent."""
    try:
        proc = (
            subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                ["git", "describe", "--tags", "--always", "--dirty"],
                capture_output=True,
                text=True,
                cwd=REPO,
                timeout=30,
            )
        )
        return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def build_bom(inventory: dict) -> dict:
    """Render the inventory as a CycloneDX 1.6 ML-BOM document."""
    components = []
    for entry in inventory.get("models") or []:
        licence = str(entry.get("licence", "")).strip()
        # CycloneDX distinguishes a recognised SPDX id from a named licence. The
        # Llama community licences are not SPDX ids, and expressing them as one
        # would misrepresent them as standard open source -- the exact confusion
        # this file exists to prevent.
        spdx_like = (
            bool(re.fullmatch(r"[A-Za-z0-9.\-+]+", licence))
            and entry.get("licence_class") == "permissive"
        )
        licence_node = {"license": ({"id": licence} if spdx_like else {"name": licence})}

        components.append(
            {
                "type": "machine-learning-model",
                "bom-ref": f"model:{entry['id']}",
                "name": entry["id"],
                "licenses": [licence_node],
                "description": entry.get("role", ""),
                "properties": [
                    {
                        "name": "trancendos:licence_class",
                        "value": str(entry.get("licence_class", "")),
                    },
                    {
                        "name": "trancendos:obligations",
                        "value": str(entry.get("obligations", "")).strip(),
                    },
                    {"name": "trancendos:execution", "value": str(entry.get("execution", ""))},
                    {"name": "trancendos:data_egress", "value": str(entry.get("data_egress", ""))},
                    {"name": "trancendos:disposition", "value": str(entry.get("disposition", ""))},
                    {"name": "trancendos:used_by", "value": ", ".join(entry.get("used_by") or [])},
                ],
            }
        )

    for entry in inventory.get("hosted_providers") or []:
        components.append(
            {
                "type": "service",
                "bom-ref": f"provider:{entry['id']}",
                "name": entry["id"],
                "description": entry.get("role", ""),
                "properties": [
                    {"name": "trancendos:terms", "value": str(entry.get("terms", ""))},
                    {"name": "trancendos:execution", "value": str(entry.get("execution", ""))},
                    {"name": "trancendos:data_egress", "value": str(entry.get("data_egress", ""))},
                    {"name": "trancendos:disposition", "value": str(entry.get("disposition", ""))},
                ],
            }
        )

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": {
                "type": "application",
                "name": "trancendos",
                "version": _git_describe(),
            },
            "properties": [
                {
                    "name": "trancendos:scope",
                    "value": (
                        "Models CONSUMED from third parties. Trancendos trains no models; "
                        "Tranc3Engine runs in bootstrap mode with no weights."
                    ),
                },
                {
                    "name": "trancendos:inventory_verified",
                    "value": str((inventory.get("meta") or {}).get("last_verified", "")),
                },
            ],
        },
        "components": components,
    }


def main() -> int:
    """Write the ML-BOM; with --check, fail when code references an undeclared model."""
    ap = argparse.ArgumentParser(description="Generate the AI-BOM for consumed models.")
    ap.add_argument("--check", action="store_true", help="fail on undeclared model drift")
    args = ap.parse_args()

    inventory = _load_inventory()
    declared = _declared_names(inventory)
    referenced = _scan_for_models()

    undeclared = {name: paths for name, paths in referenced.items() if name.lower() not in declared}

    bom = build_bom(inventory)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(bom, indent=2) + "\n")

    models = [c for c in bom["components"] if c["type"] == "machine-learning-model"]
    providers = [c for c in bom["components"] if c["type"] == "service"]
    print(f"AI-BOM written: {OUTPUT.relative_to(REPO)}")
    print(f"  models declared    : {len(models)}")
    print(f"  hosted providers   : {len(providers)}")
    print(f"  model refs in code : {len(referenced)}")

    non_permissive = [
        e
        for e in (inventory.get("models") or [])
        if e.get("licence_class") and e["licence_class"] != "permissive"
    ]
    if non_permissive:
        print("\n  Non-permissive model licences (obligations beyond attribution):")
        for entry in non_permissive:
            print(f"    {entry['id']:<34} {entry['licence']}  [{entry.get('disposition', '?')}]")

    if undeclared:
        print(
            f"\n[{'FAIL' if args.check else 'WARN'}] {len(undeclared)} model reference(s) not in the inventory:",
            file=sys.stderr,
        )
        for name, paths in undeclared.items():
            print(f"        {name}  ({', '.join(paths[:3])})", file=sys.stderr)
        print(
            f"\n        A model in code but not in {INVENTORY.relative_to(REPO)} has no recorded\n"
            "        licence, execution location, or egress answer. Add it there, with those\n"
            "        three facts, or remove the reference.",
            file=sys.stderr,
        )
        return 1 if args.check else 0

    if args.check:
        print("\nAI-BOM drift check: PASSED (every model referenced in code is declared)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
