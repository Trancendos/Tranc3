#!/usr/bin/env python3
"""Prove that each security guard is actually load-bearing.

WHY THIS EXISTS

The estate's recurring defect is not a missing control. It is a control that
exists, runs, reports, and does not act. Every one of these was found in code
whose tests were green:

  * `src/workflow/nodes/base.py` — the evaluator that replaced `eval()` shipped
    with an allowlist of safe builtins that name resolution never consulted, so
    `len(x)` failed in production. Its own tests passed `{"len": len}` into the
    namespace themselves, a namespace no call site builds. Ten further defects
    followed in the same file (#1145).
  * `src/event_bus/wiring.py` — `security.*` events routed to a channel that
    exists, so nothing was ever rejected or logged, and no security consumer
    saw a threat detection.
  * `src/tranquility/wellbeing.py` — a safeguarding assessment compared against
    a synthetic string that could never match, discarded the result, and
    swallowed the error.
  * `renovate.json` — a rule that read as a block while a rule below it set
    `automerge: true` on the same packages.

A test suite cannot distinguish "this guard works" from "this guard is never
reached". Only removing the guard can. That is what this does: for each entry
below it deletes the guard, runs the tests that claim to cover it, and requires
them to FAIL. A guard whose removal keeps the suite green is not protecting
anything, and CI says so.

This is mutation testing scoped deliberately narrow — security guards only,
each with the tests that must notice. A general mutation run over the whole
tree would cost minutes and drown the signal.

FAIL-CLOSED BEHAVIOUR

Two ways to report success dishonestly, both refused:

  * A mutation whose target text is not found means the manifest has drifted
    from the code. That is a failure, never a skip — a silently-skipped entry
    verifies nothing while still printing a pass.
  * A guard whose removal leaves the suite green is a failure, which is the
    whole point.

The original bytes are held in memory and restored in a `finally`. This does
not use `git checkout --`: that restores from the index, so it destroys an
unstaged or untracked fix rather than restoring it, which corrupted an entire
calibration run during the #1145 work before the cause was understood.

ADDING A GUARD

Append to `GUARDS`. `removes` is the exact source text to delete (or a
(before, after) pair to substitute); `tests` are pytest node ids that must fail
without it; `why` is the incident that earned the entry.

Usage:
    python scripts/check_guard_calibration.py           # all guards
    python scripts/check_guard_calibration.py --list    # show the manifest
    python scripts/check_guard_calibration.py --only ID # one guard
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Guard:
    """One security guard and the tests that must fail without it."""

    id: str
    path: str
    why: str
    tests: tuple[str, ...]
    # Exact source text to delete. Either a string (removed) or a
    # (before, after) pair (substituted) when deleting outright would not parse.
    removes: str | tuple[str, str] = ""
    extra: tuple[str | tuple[str, str], ...] = field(default_factory=tuple)


_EVAL = "src/workflow/nodes/base.py"
_EVAL_TESTS = "tests/test_safe_eval.py"

GUARDS: tuple[Guard, ...] = (
    Guard(
        id="format-traversal",
        path=_EVAL,
        why=(
            "str.format runs getattr inside CPython's format mini-language, "
            "outside the AST this evaluator walks, so it read private state "
            "straight through the dunder-attribute rule."
        ),
        removes=(
            "    if fname in _DENIED_METHODS:\n"
            "        raise ValueError(\n"
            "            f\"Call to '{fname}' is denied: it performs its own unrestricted "
            'attribute access"\n'
            "        )\n"
        ),
        tests=(
            f"{_EVAL_TESTS}::test_format_cannot_traverse_private_attributes",
            f"{_EVAL_TESTS}::test_format_map_is_denied_too",
        ),
    ),
    Guard(
        id="mutating-methods",
        path=_EVAL,
        why=(
            "inputs and context enter the namespace by reference, so "
            "context.clear() wiped a running workflow's execution_id."
        ),
        removes=(
            "    if fname in _MUTATING_METHODS:\n"
            "        raise ValueError(f\"Call to '{fname}' is denied: it mutates its receiver\")\n"
        ),
        # Removing that branch alone proves nothing: _DENIED_METHODS is a
        # SUPERSET of _MUTATING_METHODS, so every mutator was still refused and
        # the test failed only because the error text changed. The guard read as
        # load-bearing while its removal changed no behaviour -- exactly the
        # defect this tool exists to catch, occurring inside the tool. The
        # mutant must therefore drop the mutators from _DENIED_METHODS too, so
        # `context.clear()` genuinely executes.
        extra=(
            (
                '_DENIED_METHODS = frozenset({"format", "format_map"}) | _MUTATING_METHODS',
                '_DENIED_METHODS = frozenset({"format", "format_map"})',
            ),
        ),
        tests=(f"{_EVAL_TESTS}::test_mutating_methods_cannot_change_workflow_state",),
    ),
    Guard(
        id="repeat-ceiling",
        path=_EVAL,
        why=(
            "the ceiling capped the repeat count per operation, so chaining "
            "stayed under it while the sequence grew: 'a'*1000*1000*100 "
            "allocated 100 MB."
        ),
        removes=(
            "        if isinstance(left, (str, bytes, list, tuple)) and isinstance(right, int):\n"
            "            _guard_repeat(len(left), right)\n"
            "        if isinstance(right, (str, bytes, list, tuple)) and isinstance(left, int):\n"
            "            _guard_repeat(len(right), left)\n"
        ),
        tests=(f"{_EVAL_TESTS}::test_oversized_repetition_is_rejected_without_allocating",),
    ),
    Guard(
        id="call-result-ceiling",
        path=_EVAL,
        why=(
            "namespace values arrive in the request body, not the expression "
            "text, so list(s) over a long input built an unbounded list while "
            "every other path was guarded."
        ),
        removes=(
            "        return _guard_size(func(*args, **kwargs))",
            "        return func(*args, **kwargs)",
        ),
        tests=(f"{_EVAL_TESTS}::test_call_results_are_size_guarded",),
    ),
    Guard(
        id="builtin-name-resolution",
        path=_EVAL,
        why=(
            "the call allowlist was unreachable: name resolution consulted only "
            "the caller namespace, which the nodes build from workflow inputs, "
            "so len(x) failed with 'Unknown variable: len' in production."
        ),
        removes=(
            "        if node.id in _SAFE_BUILTINS:\n            return _SAFE_BUILTINS[node.id]\n"
        ),
        tests=(f"{_EVAL_TESTS}::test_builtins_are_reachable_from_the_production_namespace",),
    ),
    Guard(
        id="expression-length",
        path=_EVAL,
        why=(
            "a literal is only as large as the text spelling it out, so the "
            "result ceilings alone did not stop one enormous literal."
        ),
        removes=(
            "    if len(expr) > _MAX_EXPR_CHARS:\n"
            '        raise ValueError("Expression exceeds the maximum allowed length")\n'
        ),
        tests=(f"{_EVAL_TESTS}::test_expression_length_is_bounded",),
    ),
    Guard(
        id="boolean-operand-semantics",
        path=_EVAL,
        why=(
            "all()/any() collapsed and/or to a bool, so the ordinary fallback "
            'idiom "x or default" yielded True whichever side won and a '
            "TransformNode passed that downstream as data."
        ),
        removes=(
            "        is_and = isinstance(node.op, ast.And)\n"
            "        result = _eval(node.values[0])\n"
            "        for operand in node.values[1:]:\n"
            "            # Short-circuit, so the remaining operands are never evaluated.\n"
            "            if is_and and not result:\n"
            "                return result\n"
            "            if not is_and and result:\n"
            "                return result\n"
            "            result = _eval(operand)\n"
            "        return result\n",
            "        if isinstance(node.op, ast.And):\n"
            "            return all(_eval(v) for v in node.values)\n"
            "        return any(_eval(v) for v in node.values)\n",
        ),
        tests=(
            f"{_EVAL_TESTS}::test_boolean_operators_return_the_operand_not_a_bool",
            f"{_EVAL_TESTS}::test_boolean_operators_short_circuit",
        ),
    ),
    Guard(
        id="private-attribute",
        path=_EVAL,
        why=(
            "non-underscore-only attribute access is what keeps "
            "().__class__.__bases__ out of reach; without it the original RCE "
            "walk is available again."
        ),
        removes=(
            '        if node.attr.startswith("_"):\n'
            "            raise ValueError(f\"Access to private attribute '{node.attr}' is denied\")\n"
        ),
        tests=(
            f"{_EVAL_TESTS}::test_safe_eval_attribute",
            f"{_EVAL_TESTS}::test_safe_eval_unsupported",
        ),
    ),
    Guard(
        id="dict-unpack-merge",
        path=_EVAL,
        why=(
            "a None key is `**mapping`; skipping those made {**data} evaluate "
            "to {} so a TransformNode returned empty and reported success."
        ),
        removes=(
            "            if k is None:\n"
            "                spread = _eval(v)\n"
            "                if not isinstance(spread, dict):\n"
            "                    raise ValueError(\"Only a mapping can be unpacked with '**'\")\n"
            "                out.update(spread)\n"
            "            else:\n"
            "                out[_eval(k)] = _eval(v)\n",
            "            if k is not None:\n                out[_eval(k)] = _eval(v)\n",
        ),
        tests=(
            f"{_EVAL_TESTS}::test_dict_unpacking_is_merged_not_dropped",
            f"{_EVAL_TESTS}::test_unpacking_a_non_mapping_is_refused",
        ),
    ),
    Guard(
        id="duplicate-keyword",
        path=_EVAL,
        why=(
            "Python raises for f(z=1, **{'z': 2}); a plain update() kept one "
            "value, so the evaluator gave a different answer from the same "
            "expression outside it."
        ),
        removes=(
            "            if name in kwargs:\n"
            "                raise ValueError(f\"Got multiple values for keyword argument '{name}'\")\n"
        ),
        tests=(f"{_EVAL_TESTS}::test_duplicate_keyword_across_explicit_and_unpacked_is_refused",),
    ),
)


def _apply(text: str, edit: str | tuple[str, str]) -> str:
    """Apply one edit, raising if its target is absent (manifest drift)."""
    if isinstance(edit, tuple):
        before, after = edit
    else:
        before, after = edit, ""
    if before not in text:
        raise LookupError(before)
    return text.replace(before, after, 1)


# pytest's documented exit codes. Only these two mean "the suite ran and
# reached a verdict"; everything else (2 interrupted, 3 internal error,
# 4 usage error, 5 nothing collected, or a signal) means it never got that far.
_PYTEST_PASSED = 0
_PYTEST_TESTS_FAILED = 1


class CalibrationError(RuntimeError):
    """pytest did not run to a verdict, so its exit status proves nothing."""


def _run_tests(tests: tuple[str, ...]) -> bool:
    """True if the tests all passed; raises if pytest never reached a verdict.

    The distinction is the whole point. This tool reads "non-zero" as "the
    guard's removal was detected" -- but a mutation that breaks collection, or
    a pytest killed by the OOM killer, also exits non-zero while detecting
    nothing. Treating those as success is the precise failure this tool exists
    to catch, so they raise instead.
    """
    # Inherit the real environment and PREPEND to PYTHONPATH rather than
    # replacing it. A hand-built env worked locally and would have been a
    # landmine on a CI runner, where the interpreter, its site-packages and the
    # tool cache live at paths this process cannot guess; replacing the
    # variable outright would also drop a workspace's own import paths.
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(REPO_ROOT), env.get("PYTHONPATH", "")) if part
    )
    # Do not let the MUTATED source be written to __pycache__. Python validates
    # cached bytecode on (mtime, size), and restoring the original gives back
    # the identical size within the same second -- so the stale .pyc keeps
    # looking fresh and a later import silently executes the mutation from a
    # file that reads correctly on disk. That is not hypothetical: it happened
    # during this tool's own development and cost an hour, with `git diff`
    # clean and the source visibly right the whole time.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
    # argv is a list (no shell), and every element is either a literal or comes
    # from the GUARDS manifest above -- module constants in this file, not input.
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *tests],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode not in (_PYTEST_PASSED, _PYTEST_TESTS_FAILED):
        raise CalibrationError(
            f"pytest exited {proc.returncode} without reaching a verdict on "
            f"{', '.join(tests)} — this is not evidence the guard was detected.\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    if proc.returncode == _PYTEST_TESTS_FAILED:
        # Keep the diagnostics: without them a red gate cannot be repaired.
        _last_failure_output.clear()
        _last_failure_output.append(proc.stdout + proc.stderr)
    return proc.returncode == _PYTEST_PASSED


# Output of the most recent failing pytest run, surfaced when the BASELINE
# fails -- at that point the suite is broken and the operator needs to see why.
_last_failure_output: list[str] = []


def _purge_bytecode(source: Path) -> None:
    """Drop cached bytecode for `source`, so a restore cannot leave a mutant behind.

    Belt and braces alongside PYTHONDONTWRITEBYTECODE: any interpreter that
    imported the file before this ran may already have cached the mutation, and
    the cache would still validate because the restored file has the same size
    and, very often, the same mtime second.
    """
    cache = source.parent / "__pycache__"
    if not cache.is_dir():
        return
    for stale in cache.glob(f"{source.stem}.*.pyc"):
        try:
            stale.unlink()
        except OSError:
            # Best effort: a cache we cannot remove is not worth failing the
            # run over, and PYTHONDONTWRITEBYTECODE already prevents new ones.
            pass


def calibrate(guard: Guard) -> tuple[bool, str]:
    """Remove the guard, require its tests to fail, restore. Returns (ok, note)."""
    target = REPO_ROOT / guard.path
    original = target.read_text(encoding="utf-8")
    try:
        mutated = original
        for edit in (guard.removes, *guard.extra):
            if not edit:
                continue
            try:
                mutated = _apply(mutated, edit)
            except LookupError as exc:
                snippet = str(exc).strip().splitlines()[0][:60] if str(exc).strip() else "?"
                return (
                    False,
                    f"manifest drift — target text not found in {guard.path}: {snippet!r}. "
                    "The guard may have been renamed or removed; update the manifest.",
                )
        if mutated == original:
            return False, "mutation changed nothing — the manifest entry is empty"
        target.write_text(mutated, encoding="utf-8")

        if _run_tests(guard.tests):
            return (
                False,
                "guard removed and the suite still PASSED — these tests do not "
                "cover it: " + ", ".join(guard.tests),
            )
        return True, "removal detected"
    finally:
        # The original bytes, held in memory. Not `git checkout --`, which
        # restores from the index and would discard uncommitted work.
        target.write_text(original, encoding="utf-8")
        _purge_bytecode(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="show the manifest and exit")
    parser.add_argument("--only", metavar="ID", help="calibrate a single guard")
    args = parser.parse_args()

    if args.list:
        for guard in GUARDS:
            print(f"{guard.id:28} {guard.path}  ({len(guard.tests)} test(s))")
        return 0

    guards = GUARDS
    if args.only:
        guards = tuple(g for g in GUARDS if g.id == args.only)
        if not guards:
            print(f"no guard with id {args.only!r}", file=sys.stderr)
            return 1

    # A baseline failure would make every result meaningless: the suite must
    # pass before anything is mutated, or "removal detected" means nothing.
    all_tests = tuple(sorted({t for g in guards for t in g.tests}))
    if not _run_tests(all_tests):
        print(
            "FAIL the guard tests do not pass before any mutation — fix the suite "
            "first, or every 'removal detected' below would be meaningless.",
            file=sys.stderr,
        )
        # Print what pytest said. A gate that reports only "the baseline failed"
        # cannot be repaired from its own output.
        for captured in _last_failure_output:
            print(captured, file=sys.stderr)
        return 1

    failures = 0
    for guard in guards:
        try:
            ok, note = calibrate(guard)
        except CalibrationError as exc:
            # Not "the guard was detected" — the run never reached a verdict.
            ok, note = False, str(exc).splitlines()[0]
        if ok:
            print(f"OK   {guard.id:28} {note}")
        else:
            failures += 1
            print(f"FAIL {guard.id:28} {note}", file=sys.stderr)
            print(f"     guard exists because: {guard.why}", file=sys.stderr)

    print()
    if failures:
        print(
            f"Guard calibration: FAILED — {failures} of {len(guards)} guard(s) are "
            "not proven load-bearing. A guard whose removal keeps the suite green "
            "is not protecting anything.",
            file=sys.stderr,
        )
        return 1
    print(f"Guard calibration: PASSED — all {len(guards)} guards proven load-bearing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
