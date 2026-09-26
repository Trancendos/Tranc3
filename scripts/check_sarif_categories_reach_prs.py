#!/usr/bin/env python3
"""Fail when a code-scanning configuration exists on main but can never exist on a PR.

Why this exists
---------------
GitHub generates one check per code-scanning tool on a pull request, and it
compares the configurations the PR produced against the ones `refs/heads/main`
has. A configuration present on main and absent from the PR is reported as
`N configurations not found`, and the check concludes FAILURE.

`trivy.yml`'s `trivy-enforce` job carried `if: github.event_name == 'push' &&
github.ref == 'refs/heads/main'`, so its `trivy-fs-enforce` category existed only
on main. The consequence was not a one-off: the Trivy check concluded FAILURE on
**every pull request in this repository**, permanently, whatever the code did.

That is this estate's recurring defect wearing its plainest face. A control that
reports the same thing on a clean branch and a filthy one carries no
information; the only lesson available to a reader is to stop reading it. And
the second cost is larger than the noise -- the enforcing pass was running only
AFTER the merge it exists to gate.

How it decides, and why it is differential
------------------------------------------
The first version of this file matched two substrings and read categories with
`[\\w.-]+`. Both were wrong in the way a blind sensor is wrong -- it reported
PASSED about workflows it had not understood:

* `codeql.yml`'s category is `/language:${{ matrix.language }}`. The first
  character after the quote is `/`, outside `[\\w.-]`, so the regex did not
  match and the repository's largest code-scanning configuration was never
  examined at all. Had that upload later been restricted to main, this guard
  would still have printed PASSED. (Found by `chatgpt-codex-connector`.)
* Substring matching cannot tell `github.event_name == 'push'` from
  `github.event_name == 'push' || github.event_name == 'pull_request'`, and
  flagged the second. It also could not see `github.event_name !=
  'pull_request'`, which produces the identical defect. (Found by
  `chatgpt-codex-connector` and `codeant-ai`.)

So the workflows are parsed as YAML, and each condition is evaluated twice --
once in a pull-request context, once in a push-to-main context -- with
three-valued logic. Anything the evaluator cannot resolve (a `steps.*` output, a
`secrets` check, `success()`) becomes an *unknown*, and the same text yields the
same unknown on both sides. A configuration is reported only when it is
definitely unreachable on a pull request while still reachable on main. That is
the asymmetry that breaks the check; a condition that is equally uncertain on
both sides does not, and is left alone.

A condition that cannot be parsed at all is reported as UNREADABLE and fails the
run. A guard that quietly skips what it does not understand is the thing this
file exists to prevent; see docs/governance/IMMUNE-SYSTEM.md.

An intentional main-only category must be listed in ACCEPTED_MAIN_ONLY with a
written reason, so the decision is visible in a diff instead of implicit in a
skipped job.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"

#: category -> written reason. Empty on purpose: every configuration this
#: repository uploads should be reachable on a PR, and an addition here is a
#: decision someone has to justify in review. A blank reason is rejected, so the
#: dictionary cannot be used to silence a finding without saying why.
ACCEPTED_MAIN_ONLY: dict[str, str] = {}

#: What the two contexts look like to an `if:` expression.
PR_CONTEXT: dict[str, Any] = {
    "github.event_name": "pull_request",
    "github.ref": "refs/pull/42/merge",
    "github.ref_name": "42/merge",
    "github.ref_type": "branch",
    "github.base_ref": "main",
    "github.head_ref": "a-feature-branch",
    "github.event.repository.default_branch": "main",
}
MAIN_CONTEXT: dict[str, Any] = {
    "github.event_name": "push",
    "github.ref": "refs/heads/main",
    "github.ref_name": "main",
    "github.ref_type": "branch",
    "github.base_ref": "",
    "github.head_ref": "",
    "github.event.repository.default_branch": "main",
}


class CannotReadWorkflows(RuntimeError):
    """Raised when the workflow directory cannot be enumerated.

    Without it every configuration looks reachable, so the guard would report a
    clean estate having examined nothing. See docs/governance/IMMUNE-SYSTEM.md.
    """


class Unparseable(ValueError):
    """The condition is outside the expression subset this file evaluates."""


class Unknown:
    """A value the evaluator cannot resolve, identified by the text that made it.

    Two unknowns from the same source text are equal, which is what lets the
    push-context and pull-request-context evaluations cancel out instead of
    producing a spurious asymmetry.
    """

    __slots__ = ("key",)

    def __init__(self, key: str) -> None:
        self.key = key

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Unknown) and other.key == self.key

    def __hash__(self) -> int:
        return hash(("Unknown", self.key))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Unknown({self.key!r})"


_TOKEN = re.compile(
    r"""
      \s+
    | (?P<str>'(?:[^']|'')*')
    | (?P<op>==|!=|&&|\|\||[()!,])
    | (?P<num>-?\d+(?:\.\d+)?)
    | (?P<word>[A-Za-z_][A-Za-z_0-9.\-*\[\]]*)
    """,
    re.VERBOSE,
)


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if match is None:
            raise Unparseable(f"unexpected character at offset {pos}: {text[pos : pos + 12]!r}")
        pos = match.end()
        for name in ("str", "op", "num", "word"):
            value = match.group(name)
            if value is not None:
                tokens.append(value)
                break
    return tokens


class _Parser:
    """Recursive descent over the GitHub-expression subset that appears in `if:`."""

    def __init__(self, tokens: list[str], context: dict[str, Any]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.context = context

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> str:
        if self.pos >= len(self.tokens):
            raise Unparseable("expression ended early")
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect(self, token: str) -> None:
        got = self.take()
        if got != token:
            raise Unparseable(f"expected {token!r}, got {got!r}")

    def parse(self) -> Any:
        value = self.or_expr()
        if self.peek() is not None:
            raise Unparseable(f"trailing tokens from {self.peek()!r}")
        return value

    def or_expr(self) -> Any:
        value = self.and_expr()
        while self.peek() == "||":
            self.take()
            right = self.and_expr()
            value = _or(value, right)
        return value

    def and_expr(self) -> Any:
        value = self.unary()
        while self.peek() == "&&":
            self.take()
            right = self.unary()
            value = _and(value, right)
        return value

    def unary(self) -> Any:
        if self.peek() == "!":
            self.take()
            return _not(self.unary())
        return self.comparison()

    def comparison(self) -> Any:
        left = self.primary()
        token = self.peek()
        if token in ("==", "!="):
            self.take()
            right = self.primary()
            return _compare(left, right, equal=token == "==")
        return left

    def primary(self) -> Any:
        token = self.take()
        if token == "(":
            value = self.or_expr()
            self.expect(")")
            return value
        if token.startswith("'"):
            return token[1:-1].replace("''", "'")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", token):
            return float(token)
        if token in ("true", "false"):
            return token == "true"
        if token == "null":
            return None
        if self.peek() == "(":  # function call
            return self.call(token)
        return self.context.get(token, Unknown(token))

    def call(self, name: str) -> Any:
        self.expect("(")
        args: list[Any] = []
        if self.peek() != ")":
            args.append(self.or_expr())
            while self.peek() == ",":
                self.take()
                args.append(self.or_expr())
        self.expect(")")
        if name == "always":
            return True
        if name == "cancelled":
            return False
        if name in ("contains", "startsWith", "endsWith") and len(args) == 2:
            left, right = args
            if isinstance(left, str) and isinstance(right, str):
                if name == "contains":
                    return right in left
                if name == "startsWith":
                    return left.startswith(right)
                return left.endswith(right)
        # success()/failure() and anything else resolve the same way in both
        # contexts, so they cancel out rather than creating a false asymmetry.
        rendered = ",".join(a.key if isinstance(a, Unknown) else repr(a) for a in args)
        return Unknown(f"{name}({rendered})")


def _truthy(value: Any) -> Any:
    if isinstance(value, Unknown):
        return value
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value != ""
    if isinstance(value, float):
        return value != 0.0
    return bool(value)


def _and(left: Any, right: Any) -> Any:
    left, right = _truthy(left), _truthy(right)
    if left is False or right is False:
        return False
    if left is True and right is True:
        return True
    return Unknown("and")


def _or(left: Any, right: Any) -> Any:
    left, right = _truthy(left), _truthy(right)
    if left is True or right is True:
        return True
    if left is False and right is False:
        return False
    return Unknown("or")


def _not(value: Any) -> Any:
    value = _truthy(value)
    return Unknown("not") if isinstance(value, Unknown) else not value


def _compare(left: Any, right: Any, *, equal: bool) -> Any:
    if isinstance(left, Unknown) or isinstance(right, Unknown):
        lhs = left.key if isinstance(left, Unknown) else repr(left)
        rhs = right.key if isinstance(right, Unknown) else repr(right)
        return Unknown(f"{lhs}{'==' if equal else '!='}{rhs}")
    return (left == right) if equal else (left != right)


def _strip_wrapper(condition: str) -> str:
    text = condition.strip()
    if text.startswith("${{") and text.endswith("}}"):
        return text[3:-2].strip()
    return text


def evaluate(condition: Any, context: dict[str, Any]) -> Any:
    """Three-valued evaluation of a workflow `if:` in the given context."""
    if condition is None:
        return True
    if isinstance(condition, bool):
        return condition
    text = _strip_wrapper(str(condition))
    if not text:
        return True
    if "${{" in text:
        # An interpolation inside a larger expression: not something this
        # evaluator models, and saying so beats guessing.
        raise Unparseable("nested ${{ }} interpolation")
    return _truthy(_Parser(_tokenize(text), context).parse())


def _triggers(workflow: dict[str, Any]) -> set[str]:
    # PyYAML 1.1 reads a bare `on:` key as the boolean True.
    raw = workflow.get("on", workflow.get(True))
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {str(item) for item in raw}
    if isinstance(raw, dict):
        return {str(key) for key in raw}
    return set()


def _label(path: Path, root: Path) -> str:
    """Repo-relative where that exists, root-relative otherwise (tests, forks)."""
    for base in (REPO, root):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            continue
    return path.as_posix()


def _accepted_reason_problems() -> list[str]:
    """A blank reason is not a reason; reject it before anything is scanned."""
    problems = []
    for category, reason in ACCEPTED_MAIN_ONLY.items():
        if not isinstance(reason, str) or not reason.strip():
            problems.append(
                f"ACCEPTED_MAIN_ONLY['{category}'] has no written reason. An "
                f"intentional main-only configuration has to say why it is "
                f"intentional, or the exception silences the finding without "
                f"recording a decision."
            )
    return problems


def _sarif_steps(workflow: dict[str, Any]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    found = []
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return found
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            if "upload-sarif" in str(step.get("uses", "")):
                found.append((str(job_name), job, step))
    return found


def findings(root: Path = WORKFLOWS) -> list[str]:
    """Configurations that a push to main produces and a pull request cannot."""
    if not root.is_dir():
        raise CannotReadWorkflows(f"{root} is not a directory, so nothing was examined.")
    files = sorted(list(root.glob("*.yml")) + list(root.glob("*.yaml")))
    if not files:
        raise CannotReadWorkflows(f"{root} holds no workflow files, which cannot be right.")

    problems: list[str] = _accepted_reason_problems()
    for path in files:
        try:
            workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problems.append(f"[UNREADABLE] {_label(path, root)}: not parseable as YAML ({exc}).")
            continue
        if not isinstance(workflow, dict):
            continue
        steps = _sarif_steps(workflow)
        if not steps:
            continue

        triggers = _triggers(workflow)
        on_pr = bool(triggers & {"pull_request", "pull_request_target"})
        on_main = "push" in triggers or "schedule" in triggers or "workflow_dispatch" in triggers

        for job_name, job, step in steps:
            with_block = step.get("with") if isinstance(step.get("with"), dict) else {}
            category = with_block.get("category")
            name = str(step.get("name") or step.get("uses") or "upload-sarif")
            where = f"{_label(path, root)} :: job '{job_name}' :: step '{name}'"
            shown = f"category '{category}'" if category else "its implicit category"

            try:
                pr_ok = _all_true(job.get("if"), step.get("if"), PR_CONTEXT) and on_pr
                main_ok = _all_true(job.get("if"), step.get("if"), MAIN_CONTEXT) and on_main
            except Unparseable as exc:
                problems.append(
                    f"[UNREADABLE] {where}: this guard could not evaluate the "
                    f"condition ({exc}), so it cannot say whether {shown} reaches a "
                    f"pull request.\n        Reporting that rather than passing: a "
                    f"check that skips what it does not understand is the defect "
                    f"this file exists to catch."
                )
                continue

            if pr_ok is not False or main_ok is False:
                continue
            if category is not None and str(category) in ACCEPTED_MAIN_ONLY:
                continue
            problems.append(
                f"[MAIN-ONLY] {where}: {shown} is produced by a push to main and "
                f"never by a pull request.\n        GitHub then reports "
                f"'configuration not found' and fails the generated check on EVERY "
                f"PR, whatever the code does.\n        Run the upload on pull "
                f"requests too (enforcing only on main), or list the category in "
                f"ACCEPTED_MAIN_ONLY with a reason."
            )
    return problems


def _all_true(job_if: Any, step_if: Any, context: dict[str, Any]) -> Any:
    return _and(evaluate(job_if, context), evaluate(step_if, context))


def main(argv: list[str] | None = None) -> int:
    try:
        problems = findings()
    except CannotReadWorkflows as exc:
        print(f"cannot check SARIF category reachability: {exc}", file=sys.stderr)
        return 1
    if problems:
        print("SARIF category reachability: FAILED")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("SARIF category reachability: PASSED — every uploaded configuration reaches a PR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
