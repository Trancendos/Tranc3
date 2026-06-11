#!/usr/bin/env python3
"""Preserve-formatting CWE-117 remediation via libcst."""

from __future__ import annotations

import sys
from pathlib import Path

import libcst as cst

REPO = Path(__file__).resolve().parents[1]

FLAGGED_FILES = """
workers/blender-worker/worker.py
src/workflow/routes.py
Dimensional/error_handlers.py
shared_core/error_handlers.py
archive/api_enhanced.py
src/mcp/server.py
workers/infinity-one-service/worker.py
workers/sentinel-station-service/worker.py
workers/analytics-service/worker.py
workers/gateway-service/worker.py
workers/notifications/worker.py
src/compliance/ai_governance.py
workers/users-service/worker.py
workers/infinity-auth/worker.py
src/database/vector_store.py
t2ance/tier_relay.py
trance_one/sovereign_controller.py
src/master_worker/zero_cost_enforcer.py
workers/infinity-ws/worker.py
workers/api-gateway/worker.py
src/cryptex/threat_detector.py
src/observability/routes.py
src/library/knowledge_base.py
src/nexus/hub.py
src/workflow/executor.py
src/resonate/empathy.py
src/taimra/digital_twin.py
workers/ffmpeg-worker/worker.py
Dimensional/infinity/sentinel_station.py
Dimensional/security_automation/defense_engine.py
Dimensional/infinity/abac.py
Dimensional/hive/hive_core.py
src/compliance/magna_carta.py
src/security/ip_protection.py
src/citadel/routes.py
src/artifactory/registry.py
src/devocity/portal.py
src/observability/observatory.py
src/apimarket/marketplace.py
src/registry/file_registry.py
src/citadel/devops_hub.py
src/lab/code_lab.py
src/chronos/scheduler.py
src/deepmind/planning.py
src/auth/db_user_manager.py
src/personality/spawner.py
""".strip().splitlines()

LOGGER_LEVELS = {"debug", "info", "warning", "error", "exception", "critical", "log"}
IMPORT_DIMENSIONAL = "from Dimensional.sanitize import sanitize_for_log\n"
IMPORT_SHARED = "from shared_core.sanitize import sanitize_for_log\n"


def _LOGGER_NAMES() -> set[str]:
    return {"logger", "log", "safe_log", "_log", "log_fn"}


def _is_logger_call(node: cst.Call) -> bool:
    func = node.func
    if isinstance(func, cst.Attribute) and func.attr.value in LOGGER_LEVELS:
        if isinstance(func.value, cst.Name) and func.value.value in _LOGGER_NAMES():
            return True
    if isinstance(func, cst.Name) and func.value in _LOGGER_NAMES():
        return True
    return False


def _is_sanitize_call(node: cst.BaseExpression) -> bool:
    return (
        isinstance(node, cst.Call)
        and isinstance(node.func, cst.Name)
        and node.func.value == "sanitize_for_log"
    )


def _is_safe_literal(node: cst.BaseExpression) -> bool:
    return isinstance(node, (cst.SimpleString, cst.Integer, cst.Float, cst.Name)) and (
        not isinstance(node, cst.Name) or node.value in ("True", "False", "None")
    )


def _wrap(expr: cst.BaseExpression) -> cst.BaseExpression:
    if _is_sanitize_call(expr):
        return expr
    if isinstance(expr, cst.Name) and expr.value in ("ref_id", "status_code"):
        return expr
    if isinstance(expr, cst.Attribute) and expr.attr.value == "status_code":
        return expr
    if _is_safe_literal(expr):
        return expr
    return cst.Call(func=cst.Name("sanitize_for_log"), args=[cst.Arg(expr)])


class SanitizeLoggerCalls(cst.CSTTransformer):
    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.Call:
        if not _is_logger_call(updated_node):
            return updated_node

        if not updated_node.args:
            return updated_node

        first = updated_node.args[0].value
        new_args: list[cst.Arg] = []

        if isinstance(first, cst.FormattedString):
            # Convert f-string to %-style
            parts: list[str] = []
            fmt_exprs: list[cst.BaseExpression] = []
            for part in first.parts:
                if isinstance(part, cst.FormattedStringText):
                    parts.append(part.value.replace("%", "%%"))
                elif isinstance(part, cst.FormattedStringExpression):
                    parts.append("%s")
                    fmt_exprs.append(_wrap(part.expression))
            fmt = cst.SimpleString('"' + "".join(parts) + '"')
            new_args = [cst.Arg(fmt), *[cst.Arg(e) for e in fmt_exprs]]
        elif isinstance(first, cst.SimpleString):
            new_args = [updated_node.args[0]]
            for arg in updated_node.args[1:]:
                if arg.star:  # libcst uses '' for positional, '*' for *args
                    new_args.append(arg)
                elif arg.keyword is None:
                    new_args.append(arg.with_changes(value=_wrap(arg.value)))
                else:
                    if arg.keyword.value in ("exc_info", "stacklevel", "extra", "stack_info"):
                        new_args.append(arg)
                    else:
                        new_args.append(arg.with_changes(value=_wrap(arg.value)))
        else:
            new_args = [cst.Arg(_wrap(a.value)) for a in updated_node.args]

        return updated_node.with_changes(args=new_args)


def _ensure_import(content: str, rel_path: str) -> str:
    imp = IMPORT_SHARED if rel_path.startswith("shared_core/") else IMPORT_DIMENSIONAL
    if "sanitize_for_log" in content:
        return content
    lines = content.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith(("import ", "from ")):
            insert_at = i + 1
    lines.insert(insert_at, imp)
    return "".join(lines)


def fix_file(path: Path, rel_path: str) -> bool:
    original = path.read_text(encoding="utf-8")
    module = cst.parse_module(original)
    new_content = module.visit(SanitizeLoggerCalls()).code
    if new_content == original:
        return False
    new_content = _ensure_import(new_content, rel_path)
    path.write_text(new_content, encoding="utf-8")
    print(f"FIXED: {rel_path}")
    return True


def main() -> int:
    changed = 0
    for rel in FLAGGED_FILES:
        path = REPO / rel
        if not path.exists():
            print(f"SKIP missing: {rel}")
            continue
        if fix_file(path, rel):
            changed += 1
    print(f"\n=== Updated {changed} files ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
