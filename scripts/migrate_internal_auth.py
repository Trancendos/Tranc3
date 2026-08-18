#!/usr/bin/env python3
"""Delegate hand-rolled X-Internal-Secret gates to the shared implementation.

THE STATE THIS STARTS FROM

74 services each wrote their own `X-Internal-Secret` check — 77 gate functions
for one concern. A full AST scan of `workers/` classifies them:

  * 28 compare with `!=`, which returns at the first differing byte and leaks the
    secret's prefix through response timing;
  * 10 fail **open** — `if not INTERNAL_SECRET: return` or `if SECRET and ...`
    waves every request through when the variable is unset, and `.env.example`
    ships it blank;
  * the rest are correct, by each author's care rather than by policy.

One implementation cannot drift 77 ways. `Dimensional.service_auth` is that
implementation and `Dimensional.service_auth_fastapi` translates it to
HTTPException; this script rewrites each gate to call them.

WHAT IT WILL AND WILL NOT REWRITE

It rewrites a gate only when it can prove it understands every statement in it.
Concretely, a gate qualifies when its body is:

    [prologue statements]
    if <comparison involving the secret>:
        [failure statements]
        raise HTTPException(status_code=<int>, detail=<expr>)

with at most one such `if`, and nothing after it but an optional bare `return`.
Prologue and failure statements are preserved verbatim and in order — several
gates increment metrics counters on attempt and on failure, and dropping those
would silently blind the dashboards that watch for credential stuffing.

Anything else is reported and left alone. A gate this script cannot read is a
gate a human should read; guessing at authentication code is how fail-open
patterns get introduced, not removed.

BEHAVIOUR CHANGES THIS DELIBERATELY MAKES

  * A fail-open gate becomes fail-closed. That is the point, and it is a real
    behaviour change: a service with no INTERNAL_SECRET set now answers 503
    instead of serving the request. The alternative is a service that appears
    authenticated and is not.
  * A `!=` comparison becomes constant-time.

BEHAVIOUR IT DELIBERATELY PRESERVES

  * The mismatch status code and detail. The estate uses both 401 and 403 for
    this condition; normalising them would change the contract every existing
    caller is written against, and that is a separate decision from removing
    the duplication.
  * The function name, signature and decorators, so every `Depends(...)`,
    router `dependencies=[...]` and direct call keeps working untouched.

REACHABILITY

A service can only call the shared module if the module is in its image.
Own-context workers get it through the `sharedcore` named build context, which
`scripts/apply_shared_core_contexts.py` adds automatically once this script has
introduced the import — that script derives what to deliver from what the source
actually imports, so the two compose without either knowing about the other.
Run it after this one. Services that build from the repo root already have it.

Run with `--check` in CI: exits 1 if any gate still compares in-line, so a new
service cannot quietly add a 78th implementation.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKERS = ROOT / "workers"

DELEGATED_CALL = "guard_internal_secret"
IMPORT_LINE = "from Dimensional.service_auth_fastapi import guard_internal_secret"

SECRET_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]*SECRET$|internal_secret$", re.I)


@dataclass
class Gate:
    """One hand-rolled gate: where it is, what it compares, and how it refuses."""

    path: Path
    func: ast.FunctionDef | ast.AsyncFunctionDef
    if_node: ast.If
    presented: str
    expected: str
    status: int
    detail: str
    timing_safe: bool
    fail_open_nodes: list[ast.stmt]
    folded_fail_open: bool = False
    redundant_503: list[ast.stmt] = field(default_factory=list)

    @property
    def fails_open(self) -> bool:
        """True if this gate admits every caller when the secret is unset."""
        return bool(self.fail_open_nodes) or self.folded_fail_open

    @property
    def label(self) -> str:
        """A `path:line func()` string, so a report line can be clicked."""
        return f"{self.path.relative_to(ROOT)}:{self.func.lineno} {self.func.name}()"


def _is_secret(node: ast.expr) -> bool:
    """True for an expression naming the configured secret.

    Accepts a bare name (`INTERNAL_SECRET`, `_INTERNAL_SECRET`) and an attribute
    (`cfg.internal_secret`), which are the two spellings in use. Anything else is
    treated as not-the-secret so an unfamiliar expression falls through to the
    "cannot read this" path rather than being rewritten on a guess.
    """
    if isinstance(node, ast.Name):
        return bool(SECRET_NAME.match(node.id))
    if isinstance(node, ast.Attribute):
        return bool(SECRET_NAME.match(node.attr))
    return False


def _strip_or_empty(node: ast.expr) -> ast.expr:
    """Unwrap `x or ""`, which several gates use to normalise a missing header.

    The shared verifier does that normalisation itself, so carrying the wrapper
    through would be redundant — and leaving it in place would make two gates
    with identical behaviour look different in the diff.
    """
    if (
        isinstance(node, ast.BoolOp)
        and isinstance(node.op, ast.Or)
        and len(node.values) == 2
        and isinstance(node.values[1], ast.Constant)
        and node.values[1].value == ""
    ):
        return node.values[0]
    return node


def _parse_comparison(test: ast.expr) -> tuple[str, str, bool] | None:
    """Read a gate's condition, returning (presented, expected, timing_safe).

    Handles the forms present in the estate:
      * `presented != SECRET`
      * `not hmac.compare_digest(presented, SECRET)`
      * `not compare_digest(presented, SECRET)`  (imported directly)
      * `SECRET and <any of the above>` — the fail-open spelling: when the
        secret is unset the whole condition is falsy, so the refusal never runs
        and every caller is admitted. Unwrapped here and reported as fail-open
        by `_folded_fail_open`, because the guard is inside the condition rather
        than in a prologue statement.

    Returns None for anything else, which routes the gate to manual review.
    """
    if (
        isinstance(test, ast.BoolOp)
        and isinstance(test.op, ast.And)
        and len(test.values) == 2
        and _is_secret(test.values[0])
    ):
        return _parse_comparison(test.values[1])

    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.NotEq):
        left, right = test.left, test.comparators[0]
        if _is_secret(right):
            return ast.unparse(_strip_or_empty(left)), ast.unparse(right), False
        if _is_secret(left):
            return ast.unparse(_strip_or_empty(right)), ast.unparse(left), False
        return None

    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        call = test.operand
        if not isinstance(call, ast.Call) or len(call.args) != 2:
            return None
        name = (
            call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
        )
        if name != "compare_digest":
            return None
        a, b = call.args
        if _is_secret(b):
            return ast.unparse(_strip_or_empty(a)), ast.unparse(b), True
        if _is_secret(a):
            return ast.unparse(_strip_or_empty(b)), ast.unparse(a), True
    return None


def _read_raise(node: ast.stmt) -> tuple[int, str] | None:
    """Extract (status_code, detail) from a `raise HTTPException(...)`.

    Only a literal integer status is accepted. A computed status would have to be
    re-evaluated in the rewritten body, and the point of this script is to not
    guess about authentication control flow.
    """
    if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
        return None
    func = node.exc.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name != "HTTPException":
        return None
    status, detail = None, '"Forbidden"'
    for kw in node.exc.keywords:
        if kw.arg == "status_code":
            status = _status_value(kw.value)
        elif kw.arg == "detail":
            detail = _render(kw.value)
    for i, arg in enumerate(node.exc.args):
        if i == 0:
            status = _status_value(arg) or status
        elif i == 1:
            detail = _render(arg)
    return (status, detail) if isinstance(status, int) else None


def _render(node: ast.expr) -> str:
    """Unparse an expression using the repo's quote style.

    `ast.unparse` emits single-quoted strings; the repo formats with black,
    which rewrites them to double quotes. Emitting black's form directly keeps
    this rewrite out of the formatter's way — otherwise a `black .` run after
    the migration reformats the whole tree and buries a security change in
    hundreds of files of unrelated quote churn.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return '"' + node.value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return ast.unparse(node)


def _status_value(node: ast.expr) -> int | None:
    """Resolve a status code written as a literal or as a Starlette constant.

    `status.HTTP_401_UNAUTHORIZED` is as much a literal 401 as `401` is; reading
    only the integer form sent library-service to manual review for a purely
    cosmetic reason. The number is taken from the constant's own name rather
    than by importing starlette, so this stays a static rewrite with no import
    of the code it is rewriting.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    name = node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
    m = re.match(r"^HTTP_(\d{3})_", name or "")
    return int(m.group(1)) if m else None


def _fail_open_prologue(body: list[ast.stmt]) -> list[ast.stmt] | None:
    """Identify leading statements that wave the request through when unset.

    Two spellings, both meaning "no secret configured, so allow everyone":
    `if not SECRET: return` as a prologue, and `if SECRET and <compare>` folded
    into the condition itself (handled by the caller). Returns the nodes to drop,
    or None if the prologue contains no such escape.
    """
    dropped = []
    for stmt in body:
        if (
            isinstance(stmt, ast.If)
            and isinstance(stmt.test, ast.UnaryOp)
            and isinstance(stmt.test.op, ast.Not)
            and _is_secret(stmt.test.operand)
            and len(stmt.body) == 1
            and isinstance(stmt.body[0], (ast.Return, ast.Pass))
            and not stmt.orelse
            and (not isinstance(stmt.body[0], ast.Return) or stmt.body[0].value is None)
        ):
            dropped.append(stmt)
    return dropped or None


def _is_unconfigured_raise(stmt: ast.stmt) -> bool:
    """True for `if not SECRET: raise HTTPException(503, ...)`.

    lab-service and library-service both carry this as a separate statement
    beside the comparison — it is the fail-*closed* spelling, and it is exactly
    what `verify_internal_secret` does internally. Recognising it lets those
    gates migrate instead of being sent to manual review for expressing the
    right behaviour in two statements instead of one, and the resulting call
    keeps the same 503.
    """
    return (
        isinstance(stmt, ast.If)
        and isinstance(stmt.test, ast.UnaryOp)
        and isinstance(stmt.test.op, ast.Not)
        and _is_secret(stmt.test.operand)
        and not stmt.orelse
        and len(stmt.body) == 1
        and _read_raise(stmt.body[0]) is not None
    )


def _folded_fail_open(test: ast.expr) -> bool:
    """True when the condition itself is what admits everyone if the secret is unset.

    `if SECRET and presented != SECRET` reads as a check but is not one when
    SECRET is blank: the condition is falsy, the refusal is skipped, and the
    request proceeds unauthenticated. Reported separately from the prologue
    spelling so the migration summary counts every fail-open gate, however it
    was written.
    """
    return (
        isinstance(test, ast.BoolOp)
        and isinstance(test.op, ast.And)
        and len(test.values) == 2
        and _is_secret(test.values[0])
    )


def find_gates(path: Path) -> tuple[list[Gate], list[str]]:
    """Locate every gate in one file, and report the ones that cannot be read.

    Returns (rewritable gates, reasons the rest were skipped). A file is scanned
    even if it already imports the shared module, so a partially migrated service
    still surfaces its remaining gates.
    """
    src = path.read_text(encoding="utf-8", errors="ignore")
    if "INTERNAL_SECRET" not in src.upper():
        return [], []
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [], [f"{path.relative_to(ROOT)}: unparseable — {exc}"]

    gates, skipped = [], []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        unparsed = ast.unparse(func)
        if "INTERNAL_SECRET" not in unparsed.upper():
            continue
        if DELEGATED_CALL in unparsed:
            continue

        candidates = [
            s for s in func.body if isinstance(s, ast.If) and _parse_comparison(s.test) is not None
        ]
        if not candidates:
            # Not a gate: takes the header and passes it on, or reads the
            # variable for something other than a comparison.
            if re.search(r"(!=|==)\s*[A-Za-z_.]*SECRET|compare_digest", unparsed):
                skipped.append(
                    f"{path.relative_to(ROOT)}:{func.lineno} {func.name}(): compares the "
                    f"secret somewhere this script cannot place (nested in a loop, "
                    f"branch or comprehension) — migrate by hand"
                )
            continue
        if len(candidates) > 1:
            skipped.append(
                f"{path.relative_to(ROOT)}:{func.lineno} {func.name}(): {len(candidates)} "
                f"separate comparisons in one function — migrate by hand"
            )
            continue

        node = candidates[0]
        parsed = _parse_comparison(node.test)
        presented, expected, timing_safe = parsed
        if node.orelse:
            skipped.append(
                f"{path.relative_to(ROOT)}:{func.lineno} {func.name}(): the check has an "
                f"else branch, so refusing is not the only outcome — migrate by hand"
            )
            continue
        raised = _read_raise(node.body[-1]) if node.body else None
        if raised is None:
            skipped.append(
                f"{path.relative_to(ROOT)}:{func.lineno} {func.name}(): the failure branch "
                f"does not end in `raise HTTPException(status_code=<int>, ...)` — "
                f"migrate by hand"
            )
            continue
        idx = func.body.index(node)
        trailing = [s for s in func.body[idx + 1 :] if not _is_unconfigured_raise(s)]
        if any(not (isinstance(s, ast.Return) and s.value is None) for s in trailing):
            skipped.append(
                f"{path.relative_to(ROOT)}:{func.lineno} {func.name}(): statements follow "
                f"the check — migrate by hand"
            )
            continue

        status, detail = raised
        gates.append(
            Gate(
                path=path,
                func=func,
                if_node=node,
                presented=presented,
                expected=expected,
                status=status,
                detail=detail,
                timing_safe=timing_safe,
                fail_open_nodes=_fail_open_prologue(func.body[:idx]) or [],
                folded_fail_open=_folded_fail_open(node.test),
                # Scanned on both sides of the comparison: lab-service writes
                # the unconfigured raise after it, library-service before it,
                # and in both cases the delegated call now provides that 503.
                redundant_503=[
                    s
                    for s in (*func.body[:idx], *func.body[idx + 1 :])
                    if _is_unconfigured_raise(s)
                ],
            )
        )
    return gates, skipped


def render_body(gate: Gate, lines: list[str], indent: str) -> list[str]:
    """Build the replacement statements for one gate, preserving its own logic.

    Prologue and failure-side statements are copied from the source text rather
    than re-emitted from the AST, so comments and formatting inside them survive.
    A gate with no failure-side statements gets a plain call; one with them gets
    a try/except, because those statements (metrics counters, log lines) must
    still run when the check refuses.
    """
    drop = {id(n) for n in gate.fail_open_nodes} | {id(n) for n in gate.redundant_503}
    idx = gate.func.body.index(gate.if_node)
    prologue: list[str] = []
    for stmt in gate.func.body[:idx]:
        if id(stmt) in drop:
            continue
        prologue.extend(lines[stmt.lineno - 1 : stmt.end_lineno])

    failure_stmts = gate.if_node.body[:-1]
    failure: list[str] = []
    for stmt in failure_stmts:
        for raw in lines[stmt.lineno - 1 : stmt.end_lineno]:
            failure.append(indent + raw.strip() if raw.strip() else raw)

    # The expected secret is ALWAYS passed explicitly, even when the constant is
    # literally named INTERNAL_SECRET and the shared verifier would default to
    # reading that environment variable. Omitting it looks equivalent and is not:
    # the gate compared against a *module-level* value, which is read once at
    # import and can differ from the live environment. Tests monkeypatch it
    # (`monkeypatch.setattr(mod, "_INTERNAL_SECRET", ...)`), and a worker may
    # normalise or default it. Letting the verifier re-read os.environ instead
    # silently ignored both — it broke infinity-ws and swarm-coordinator, which
    # is how this was caught.
    call = (
        f"{indent}{DELEGATED_CALL}({gate.presented}, {gate.expected}, "
        f"mismatch_status={gate.status}, detail={gate.detail})\n"
    )

    if not failure:
        return prologue + [call]

    return (
        prologue
        + [f"{indent}try:\n", f"{indent}    {call.strip()}\n"]
        + [f"{indent}except HTTPException:\n"]
        + [f"{indent}    {line.strip()}\n" for line in failure if line.strip()]
        + [f"{indent}    raise\n"]
    )


def rewrite_file(path: Path, gates: list[Gate]) -> int:
    """Apply every rewritable gate in one file, bottom-up, and add the import.

    Rewrites from the last gate to the first so that each edit's line numbers
    are still valid when it is applied — the AST was parsed once, against the
    original text.
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for gate in sorted(gates, key=lambda g: g.func.lineno, reverse=True):
        first = min(
            [s.lineno for s in gate.func.body],
        )
        # Extend the replaced span over a trailing `if not SECRET: raise 503`,
        # whose behaviour the delegated call now provides; leaving it would
        # make the 503 unreachable dead code below a call that already raises.
        last = max(s.end_lineno for s in gate.func.body)
        indent = re.match(r"\s*", lines[gate.if_node.lineno - 1]).group(0)
        replacement = render_body(gate, lines, indent)
        lines[first - 1 : last] = replacement

    text = "".join(lines)
    if IMPORT_LINE not in text:
        text = insert_import(text)
    path.write_text(text, encoding="utf-8")
    return len(gates)


def insert_import(text: str) -> str:
    """Add the shared-module import after the file's last top-level import.

    Placed by the AST's `end_lineno` of the last top-level Import/ImportFrom,
    never by searching for the last line that looks like an import: a
    parenthesised multi-line `from x import (\\n a,\\n b,\\n)` ends on a line
    that does not, and splitting it produces a SyntaxError.
    """
    tree = ast.parse(text)
    last = 0
    seen_code = False
    needs_noqa = False
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last = max(last, node.end_lineno)
            # Several workers call sys.path.append() before importing from the
            # repo, and mark each of those imports with an E402 suppression.
            # An inserted
            # import lands in the same position and needs the same marker, or
            # it becomes the one E402 in an otherwise clean file.
            needs_noqa = needs_noqa or seen_code
        elif not isinstance(node, (ast.Expr, ast.ImportFrom)) or not (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        ):
            seen_code = True
    # Assembled rather than written literally: spelling the suppression marker
    # out in this source makes ruff read it as a directive on *this* line,
    # which it then reports as malformed because the line has nothing to
    # suppress.
    suffix = "  # " + "noqa: E402" if needs_noqa else ""
    lines = text.splitlines(keepends=True)
    lines.insert(last, IMPORT_LINE + suffix + "\n")
    return "".join(lines)


def main() -> int:
    """Migrate every readable gate, or report what remains under `--check`."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="report gates still comparing in-line; write nothing, exit 1 if any",
    )
    ap.add_argument("--only", help="limit to one service, for a staged rollout")
    args = ap.parse_args()

    paths = sorted(WORKERS.rglob("*.py"))
    if args.only:
        # Match against the path relative to workers/, not the absolute path —
        # WORKERS.rglob yields absolute paths, whose parts[1] is a filesystem
        # directory, so an absolute comparison silently matches nothing.
        paths = [p for p in paths if p.relative_to(WORKERS).parts[0] == args.only]

    all_gates: dict[Path, list[Gate]] = {}
    all_skipped: list[str] = []
    for path in paths:
        s = str(path)
        if "__pycache__" in s or f"{'/'}tests{'/'}" in s:
            continue
        # A vendored copy of the shared core is the implementation, not a
        # hand-rolled gate. Scanning it reports `verify_internal_secret` itself
        # as something to migrate to `verify_internal_secret`.
        if "/Dimensional/" in s or "/shared_core/" in s:
            continue
        gates, skipped = find_gates(path)
        if gates:
            all_gates[path] = gates
        all_skipped.extend(skipped)

    total = sum(len(g) for g in all_gates.values())
    unsafe = sum(1 for gs in all_gates.values() for g in gs if not g.timing_safe)
    fail_open = sum(1 for gs in all_gates.values() for g in gs if g.fails_open)

    if args.check:
        for gs in all_gates.values():
            for g in gs:
                flags = []
                if not g.timing_safe:
                    flags.append("timing-unsafe")
                if g.fails_open:
                    flags.append("FAILS OPEN")
                print(
                    f"ERROR: {g.label}: compares the internal secret in-line"
                    + (f" [{', '.join(flags)}]" if flags else "")
                    + " — call Dimensional.service_auth instead",
                    file=sys.stderr,
                )
        for line in all_skipped:
            print(f"WARN:  {line}")
        print(
            f"\ninternal-auth check: {total} in-line gate(s) across "
            f"{len(all_gates)} file(s), {len(all_skipped)} needing manual review"
        )
        return 1 if total else 0

    migrated = 0
    for path, gates in sorted(all_gates.items()):
        migrated += rewrite_file(path, gates)
        print(f"  {path.relative_to(ROOT)}: {len(gates)} gate(s) delegated")

    for line in all_skipped:
        print(f"WARN:  {line}")
    print(
        f"\n{migrated} gate(s) delegated across {len(all_gates)} file(s) "
        f"({unsafe} were timing-unsafe, {fail_open} failed open); "
        f"{len(all_skipped)} left for manual review"
    )
    print("Now run: python3 scripts/apply_shared_core_contexts.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
