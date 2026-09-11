"""Every urlopen bandit is allowed to skip must be one it is safe to skip.

``pyproject.toml`` skips B310 (urllib URL opening) for the code bandit scans --
``src`` and ``api.py``. A blanket skip is a promise about every call site in that
scope, and this repository has now made that promise wrong twice:

* the original wording said all URLs were internal service-mesh endpoints, which
  CodeFactor disproved with a call to the public OSV API;
* the replacement said "every urlopen in this estate", which was wider still, and
  four reviewers caught it;
* the scoped rewrite said no in-scope site lets a caller choose the scheme -- and
  cubic found five that did (the vLLM and llama.cpp providers, two zero-cost
  probes, the SHI roadmap advisor; a sixth, the Wazuh connector, turned up while
  fixing those).

The pattern is not carelessness about wording. It is that a justification written
in prose has nothing checking it, so it decays silently while the code moves. This
file is the check. It does not restate the claim -- it enforces the two shapes the
claim names, so a new call site that is neither shape fails here rather than being
quietly covered by a skip written years earlier.

``urlopen`` matters because its default opener is not HTTP-only: it carries a
``FileHandler``, so ``file:///etc/passwd`` is a successful request returning file
contents. Every site below therefore has to constrain the scheme, either by
validating it or by never letting input near it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Exactly what `[tool.bandit] targets` / `exclude_dirs` in pyproject.toml scan.
IN_SCOPE = [REPO_ROOT / "src", REPO_ROOT / "api.py"]

CALL_RE = re.compile(r"\burlopen\s*\(")
_NOQA = "noqa" + ":"  # split so ruff does not read these literals as directives
SUPPRESSION_RE = re.compile(rf"#\s*(?:nosec\s+B310|{_NOQA}\s*S310)")
# A reason is anything after the suppression on the same line, or -- for the
# multi-line suppression shape -- a comment block immediately above it.
REASON_RE = re.compile(
    rf"#\s*(?:nosec\s+B310|{_NOQA}\s*S310)\s*[—–-]?\s*(?P<reason>.*)"
)

VALIDATION_MARKERS = (
    "from src.utils.url_guard import",
    "scheme not in",
    'scheme not in ("http"',
)
CONSTANT_MARKERS = ("hardcoded", "https")


class CallSite:
    def __init__(self, path: Path, lineno: int, line: str, preceding: list[str]):
        self.path = path
        self.lineno = lineno
        self.line = line
        self.preceding = preceding

    @property
    def rel(self) -> str:
        return self.path.relative_to(REPO_ROOT).as_posix()

    def __repr__(self) -> str:  # pragma: no cover - failure output only
        return f"{self.rel}:{self.lineno}"

    @property
    def suppressed(self) -> bool:
        return bool(SUPPRESSION_RE.search(self.line))

    @property
    def reason(self) -> str:
        match = REASON_RE.search(self.line)
        inline = match.group("reason").strip() if match else ""
        if inline:
            return inline
        # The noqa-with-reason-above form, as used in dvms/native_ecosystems.py.
        return " ".join(
            ln.strip().lstrip("#").strip() for ln in self.preceding if ln.strip().startswith("#")
        )


def _python_files() -> list[Path]:
    files: list[Path] = []
    for target in IN_SCOPE:
        if target.is_file():
            files.append(target)
        else:
            files.extend(p for p in target.rglob("*.py") if "__pycache__" not in p.parts)
    return files


def collect_call_sites() -> list[CallSite]:
    sites: list[CallSite] = []
    for path in _python_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):  # pragma: no cover
            continue
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") or not CALL_RE.search(line):
                continue
            if stripped.startswith(("from ", "import ")):
                continue
            sites.append(CallSite(path, index + 1, line, lines[max(0, index - 4) : index]))
    return sites


def _is_https_literal(node: ast.AST) -> bool:
    """True for `"https://..."` and for f-strings whose literal prefix is https://.

    The f-string case matters: `_BASE_URL = f"https://api.cloudflare.com/.../{id}"`
    fixes the scheme just as firmly as a plain constant -- interpolation happens
    after the prefix, so no value can move the URL onto another protocol handler.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.startswith("https://")
    if isinstance(node, ast.JoinedStr) and node.values:
        first = node.values[0]
        return isinstance(first, ast.Constant) and str(first.value).startswith("https://")
    return False


def _enclosing_scopes(tree: ast.Module, lineno: int) -> list[ast.AST]:
    """Module, then each class/function containing `lineno`, innermost last."""
    scopes: list[ast.AST] = [tree]

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and getattr(
                child, "lineno", 0
            ) <= lineno <= getattr(child, "end_lineno", 0):
                scopes.append(child)
                walk(child)
                return
            walk(child)

    walk(tree)
    return scopes


def https_literals_in_scope(path: Path, lineno: int) -> list[str]:
    """Literal https:// URLs visible from the call site's own scope chain.

    Scoped rather than file-wide on purpose: an https constant defined for an
    unrelated feature at the bottom of a 900-line module is not evidence about
    the URL this particular call opens.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):  # pragma: no cover
        return []
    found: list[str] = []
    for scope in _enclosing_scopes(tree, lineno):
        for node in ast.walk(scope):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and _is_https_literal(node.value):
                found.append(ast.unparse(node.value)[:60])
            elif isinstance(node, ast.Call):
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    if _is_https_literal(arg):
                        found.append(ast.unparse(arg)[:60])
    return found


def test_in_scope_call_sites_are_found():
    """A guard over an empty set proves nothing."""
    sites = collect_call_sites()
    assert len(sites) >= 15, (
        f"Only {len(sites)} urlopen call sites found in bandit's scanned scope. "
        "Either they moved out of src/ or this collector stopped matching."
    )


def test_every_in_scope_urlopen_is_explicitly_suppressed():
    unsuppressed = [s for s in collect_call_sites() if not s.suppressed]
    assert not unsuppressed, (
        "urlopen call sites in bandit's scanned scope with no B310 suppression:\n"
        + "\n".join(f"  {s}" for s in unsuppressed)
        + "\n\nThe blanket skip in pyproject.toml hides these from bandit either way. "
        "The marker is what makes a reader (and this test) able to see them at all."
    )


def test_every_suppression_states_a_reason():
    bare = [s for s in collect_call_sites() if s.suppressed and not s.reason]
    assert not bare, (
        "B310 suppressions with no stated reason:\n"
        + "\n".join(f"  {s}: {s.line.strip()}" for s in bare)
        + "\n\n'# nosec B310' alone asserts safety without saying why, which is the "
        "same defect as the blanket skip, at a smaller scale."
    )


def test_each_reason_matches_a_shape_the_file_actually_implements():
    """The two claimable shapes, checked against the file rather than believed.

    * "scheme validated/checked" -- the file must contain a scheme check or import
      the shared guard.
    * "hardcoded https" -- the file must contain a module-level constant that is a
      literal https:// URL.
    """
    failures = []
    for site in collect_call_sites():
        reason = site.reason.lower()
        if not reason:
            continue  # covered by test_every_suppression_states_a_reason
        source = site.path.read_text(encoding="utf-8")
        claims_validation = "scheme" in reason and (
            "valid" in reason or "check" in reason or "restrict" in reason
        )
        claims_constant = any(marker in reason for marker in CONSTANT_MARKERS)
        if claims_validation:
            if not any(marker in source for marker in VALIDATION_MARKERS):
                failures.append(
                    f"{site}: claims the scheme is validated, but {site.rel} contains "
                    f"no scheme check and does not import src.utils.url_guard"
                )
        elif claims_constant:
            if not https_literals_in_scope(site.path, site.lineno):
                failures.append(
                    f"{site}: claims a hardcoded https URL, but no literal https:// "
                    f"value is visible from that call's scope chain in {site.rel}"
                )
        else:
            failures.append(
                f"{site}: reason {site.reason!r} is neither of the two shapes the "
                f"pyproject B310 skip claims (scheme-validated, or hardcoded https "
                f"constant). Add the missing guard, or widen this test deliberately."
            )
    assert not failures, "\n".join(failures)


class TestTheGuardWouldCatchIt:
    """Probe each rule against the defect it is supposed to detect."""

    def test_an_unsuppressed_call_is_detected(self, tmp_path):
        line = "        with urlopen(url, timeout=5) as resp:"
        site = CallSite(tmp_path / "x.py", 1, line, [])
        assert not site.suppressed, "an unannotated urlopen would have passed"

    def test_a_bare_suppression_has_no_reason(self, tmp_path):
        line = "        with urlopen(req, timeout=5) as resp:  # nosec B310"
        site = CallSite(tmp_path / "x.py", 1, line, [])
        assert site.suppressed and not site.reason

    def test_a_reason_is_read_from_the_em_dash_form(self, tmp_path):
        line = "        urlopen(req)  # nosec B310 — scheme validated at import"
        site = CallSite(tmp_path / "x.py", 1, line, [])
        assert site.reason == "scheme validated at import"

    def test_a_validation_claim_fails_without_a_validator(self, tmp_path):
        path = tmp_path / "unguarded.py"
        path.write_text(
            "import os, urllib.request\n"
            "BASE = os.getenv('X', 'http://localhost:1')\n"
            "def go():\n"
            "    urllib.request.urlopen(BASE)  # nosec B310 — scheme validated\n"
        )
        source = path.read_text()
        assert not any(m in source for m in VALIDATION_MARKERS), (
            "the validation-marker check would not have fired on an unguarded file"
        )

    def test_a_constant_claim_fails_without_an_https_literal(self, tmp_path):
        path = tmp_path / "nonconst.py"
        path.write_text("import os\nBASE = os.getenv('X', 'http://h')\nx = BASE\n")
        assert https_literals_in_scope(path, 3) == []

    def test_the_three_real_literal_shapes_are_all_recognised(self, tmp_path):
        path = tmp_path / "shapes.py"
        path.write_text(
            'MOD = f"https://api.cloudflare.com/v4/{acct}/run"\n'
            "class C:\n"
            '    BASE_URL = "https://api.lemonsqueezy.com/v1"\n'
            "    def go(self):\n"
            "        return open(self.BASE_URL)\n"
            "def inline():\n"
            '    return open("https://ec.europa.eu/vies")\n'
        )
        assert https_literals_in_scope(path, 1), "module-level f-string not recognised"
        assert https_literals_in_scope(path, 5), "class attribute not recognised"
        assert https_literals_in_scope(path, 7), "inline literal argument not recognised"

    def test_a_plain_http_literal_is_not_accepted(self, tmp_path):
        path = tmp_path / "plain.py"
        path.write_text('BASE = "http://localhost:8090"\nx = BASE\n')
        assert https_literals_in_scope(path, 2) == []
