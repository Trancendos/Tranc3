#!/usr/bin/env python3
"""Assert that the code-grounded claims in Magna-Carta's compliance matrices
(Security MC-015, Encryption MC-014, Knowledge MC-018) still hold.

Unlike a generic security scanner, this script checks the *specific* findings
those matrices assert are fixed — so a regression shows up as a CI failure
instead of the matrices silently drifting out of sync with the code again.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WILDCARD_CORS_RE = re.compile(r"""allow_origins\s*=\s*\[\s*["']\*["']\s*\]""")
DEV_SECRET_DEFAULT_RE = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*["']INTERNAL_SECRET["']\s*,\s*["']dev-secret["']\s*\)"""
)


_EXCLUDED_DIR_PARTS = {"node_modules", "__pycache__", ".venv", "venv", "site-packages"}


def _iter_worker_source_files() -> list[Path]:
    """Every worker's Python source, not just its worker.py/main.py entrypoint —
    CORS/secret-fallback regressions can just as easily live in an imported
    config.py, app.py, or router.py sibling module."""
    workers_dir = ROOT / "workers"
    files = workers_dir.rglob("*.py")
    return sorted(f for f in files if not _EXCLUDED_DIR_PARTS & set(f.parts))


def check_no_wildcard_cors() -> list[str]:
    """MC-015 security.cors.standalone_workers: no worker should pass a
    literal wildcard to allow_origins anymore."""
    violations = []
    for f in _iter_worker_source_files():
        text = f.read_text(errors="ignore")
        if WILDCARD_CORS_RE.search(text):
            violations.append(f"{f.relative_to(ROOT)}: wildcard allow_origins=['*']")
    return violations


def check_no_dev_secret_default() -> list[str]:
    """MC-014 encryption.secrets_and_signing.internal_secret_dev_fallback:
    no worker should use "dev-secret" as an os.getenv default — the fixed
    pattern always fails fast instead of defaulting to a known string."""
    violations = []
    for f in _iter_worker_source_files():
        text = f.read_text(errors="ignore")
        if DEV_SECRET_DEFAULT_RE.search(text):
            violations.append(
                f"{f.relative_to(ROOT)}: os.getenv(...) defaults INTERNAL_SECRET to 'dev-secret'"
            )
    return violations


def check_websecure_tls_labels() -> list[str]:
    """MC-014 encryption.in_transit: every router using entrypoints=websecure
    must also carry a tls=true/certresolver label for the same router name.

    This check only covers the tls/certresolver label itself — the separate
    Host() matcher requirement (needed for Traefik's ACME resolver to have a
    real domain to issue a cert against) is asserted by
    check_tls_routers_have_host_matcher()."""
    compose = ROOT / "docker-compose.production.yml"
    if not compose.is_file():
        return [f"{compose.relative_to(ROOT)} not found"]
    text = compose.read_text(errors="ignore")

    websecure_routers = set(
        re.findall(r"traefik\.http\.routers\.([\w-]+)\.entrypoints=websecure", text)
    )
    tls_routers = set(
        re.findall(r"traefik\.http\.routers\.([\w-]+)\.tls(?:\.certresolver)?=", text)
    )

    missing = sorted(websecure_routers - tls_routers)
    return [
        f"router '{r}' uses entrypoints=websecure with no tls=true/certresolver label"
        for r in missing
    ]


def check_tls_routers_have_host_matcher() -> list[str]:
    """MC-014 encryption.in_transit: every router with a tls=true label must also
    carry a Host() matcher in its rule, so Traefik's ACME resolver has a real
    domain to request a certificate against. A PathPrefix-only rule gives ACME
    nothing to issue a cert for."""
    compose = ROOT / "docker-compose.production.yml"
    if not compose.is_file():
        return [f"{compose.relative_to(ROOT)} not found"]
    text = compose.read_text(errors="ignore")

    tls_routers = set(re.findall(r"traefik\.http\.routers\.([\w-]+)\.tls=true", text))
    rules = dict(re.findall(r"traefik\.http\.routers\.([\w-]+)\.rule=(.+)", text))

    missing = sorted(r for r in tls_routers if "Host(" not in rules.get(r, ""))
    return [f"router '{r}' has tls=true but no Host() matcher in its rule" for r in missing]


def check_db_user_manager_uses_consolidated_hashing() -> list[str]:
    """MC-014 encryption.secrets_and_signing.password_hashing: db_user_manager.py
    must hash new passwords through src.auth.passwords (argon2id-preferred),
    not a standalone bcrypt-only context — the consolidation fixed 2026-07-25."""
    db_mgr = ROOT / "src" / "auth" / "db_user_manager.py"
    if not db_mgr.is_file():
        return [f"{db_mgr.relative_to(ROOT)} not found"]
    text = db_mgr.read_text(errors="ignore")
    violations = []
    if "from src.auth.passwords import hash_password" not in text:
        violations.append(
            "db_user_manager.py no longer imports hash_password from src.auth.passwords"
        )
    if "class _BcryptContext" in text:
        violations.append(
            "db_user_manager.py still defines a bcrypt-only _BcryptContext — "
            "consolidation to _PasswordContext was reverted"
        )
    return violations


def check_library_classification() -> list[str]:
    """MC-018 knowledge.central_finding: The Library's Article dataclass
    must carry a classification field typed as DataClassification, not just
    status/tags.

    Parses the module's AST rather than grepping raw text, so a stray
    comment, docstring, or unrelated symbol named "classification" can't
    make this pass while the Article dataclass itself lacks the field.
    """
    kb = ROOT / "src" / "library" / "knowledge_base.py"
    if not kb.is_file():
        return [f"{kb.relative_to(ROOT)} not found"]
    text = kb.read_text(errors="ignore")

    try:
        tree = ast.parse(text, filename=str(kb))
    except SyntaxError as exc:
        return [f"knowledge_base.py failed to parse: {exc}"]

    article_cls = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "Article"),
        None,
    )
    if article_cls is None:
        return ["knowledge_base.py has no Article class"]

    classification_field = next(
        (
            n
            for n in article_cls.body
            if isinstance(n, ast.AnnAssign)
            and isinstance(n.target, ast.Name)
            and n.target.id == "classification"
        ),
        None,
    )
    if classification_field is None:
        return ["Article dataclass has no classification field"]

    annotation = ast.unparse(classification_field.annotation)
    if "DataClassification" not in annotation:
        return [f"Article.classification is annotated '{annotation}', not DataClassification"]
    return []


CHECKS = {
    "no_wildcard_cors": check_no_wildcard_cors,
    "no_dev_secret_default": check_no_dev_secret_default,
    "websecure_tls_labels": check_websecure_tls_labels,
    "tls_routers_have_host_matcher": check_tls_routers_have_host_matcher,
    "db_user_manager_consolidated_hashing": check_db_user_manager_uses_consolidated_hashing,
    "library_classification": check_library_classification,
}


def main() -> int:
    results = {}
    all_violations: list[str] = []
    for name, check in CHECKS.items():
        violations = check()
        results[name] = {
            "status": "PASS" if not violations else "FAIL",
            "violations": violations,
        }
        all_violations.extend(violations)

    report = {
        "checks": results,
        "total_violations": len(all_violations),
        "status": "PASS" if not all_violations else "FAIL",
    }
    print(json.dumps(report, indent=2))
    return 0 if not all_violations else 1


if __name__ == "__main__":
    sys.exit(main())
