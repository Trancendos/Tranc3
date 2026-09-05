#!/usr/bin/env python3
"""Keep every surface that runs ruff on this tree pinned to the same ruff.

WHY THIS EXISTS

`production-gate.yml` states the intent in its own comment:

    ruff matches the 0.15.8 already pinned in ci.yml, python.yml and test.yml,
    so the gate and the lint checks cannot disagree about what passes.

That was true across the workflows and false across the full lint surface.
`.pre-commit-config.yaml` pinned `ruff-pre-commit` at v0.16.4 while all four
workflows installed `ruff==0.15.8` -- two different formatters governing one
tree, one of them running on every local commit and as a pull-request status
via pre-commit.ci.

The divergence was real and measurable: ruff 0.16.x formats Python inside
Markdown fences and 0.15.8 does not, a ten-file difference on this repository.
It had not yet bitten only because the ruff hooks are typed to Python, so `.md`
never reached them -- a latent split held closed by an unrelated detail, which
is not a guarantee.

It did bite during the audit that found it: an ambient ruff 0.16.5 reported ten
formatting failures on `main` that the pinned 0.15.8 does not, and those were
nearly filed as real.

WHY THE FIRST VERSION OF THIS CHECK WAS ITSELF THE DEFECT IT HUNTS

The original implementation scanned `.github/workflows/*.yml` and
`.forgejo/workflows/*.yml` for the literal `ruff==<version>`, and skipped --
silently, with `if not found: continue` -- any file that had no such string. So
it reported "PASSED, 5 surfaces, all on ruff 0.15.8" while the estate actually
carried five more ruff surfaces it had never looked at:

  * `.forgejo/workflows/ci.yml`            `uv pip install --system ruff`
  * `.forgejo/workflows/nightly.yml`       `pip install ruff mypy`
  * `.forgejo/workflows/security-scan.yml` `pip install ... ruff ...`
  * `.woodpecker.yml`                      `pip install --quiet ruff`  (whole
    file unscanned -- it is not under either workflows directory)
  * `deploy/forgejo/runner.Dockerfile`     `ruff==0.4.4`, a THIRD version, and
    the image the Forgejo jobs above would have run inside

Four of those install whatever ruff is latest on the day the job runs, which is
the split gate this check exists to prevent, arriving by a route the check was
structurally unable to see. A check that reports alignment across files it did
not read is worse than no check, because it is believed.

WHAT IT CHECKS NOW

Across GitHub workflows, Forgejo workflows, Woodpecker pipelines and
Dockerfiles:

  1. Every command that INSTALLS ruff must pin it exactly (`ruff==X.Y.Z`).
     An unpinned install is a failure, not a skip.
  2. Every pinned version, plus the `rev:` of the `ruff-pre-commit` repo in
     `.pre-commit-config.yaml`, must resolve to one version. The pre-commit rev
     is written `vX.Y.Z` and a pip pin `X.Y.Z`; the leading `v` is the only
     difference tolerated.
  3. A file that INVOKES ruff but never installs it is a failure too: it runs
     whatever the runner image happens to carry, which is the same unpinned
     surface wearing a different hat.

Files that only mention ruff in prose or a step name are not surfaces and are
not reported. `scripts/security_scan.sh` is deliberately out of scope: it runs
ruff only `--exit-zero` when one is already on PATH, gates nothing, and pinning
it would mean installing a second ruff for a warn-only local helper.

It fails closed. A file it cannot read is a failure, never a pass.

Usage:
    python scripts/check_ruff_pin_alignment.py      # exit 1 on drift
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"

# Every place a ruff can be installed or invoked on this estate. `.yaml` is
# scanned alongside `.yml` because GitHub, Forgejo and Woodpecker all accept it
# and a renamed file must not fall out of the gate.
SCAN_GLOBS: tuple[str, ...] = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".forgejo/workflows/*.yml",
    ".forgejo/workflows/*.yaml",
    ".woodpecker.yml",
    ".woodpecker.yaml",
    ".woodpecker/*.yml",
    ".woodpecker/*.yaml",
    "**/*Dockerfile*",
)

# Vendored trees are not this estate's lint surface, and walking them is the
# difference between a check that runs in CI and one that times out in it.
EXCLUDED_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache"})

# A command that adds a package to an environment. Anchored on the verb so a
# bare package list on a continuation line is only read as an install once the
# continuation has been joined back onto the verb that owns it.
INSTALL_VERB = re.compile(
    r"(?:uv\s+pip\s+install|uv\s+tool\s+install|pipx\s+install"
    r"|python3?\s+-m\s+pip\s+install|pip3?\s+install|poetry\s+add"
    # `uv run --with ruff`, `uvx --from ruff` and `pipx run --spec ruff`
    # install into a throwaway environment. They are installs even though the
    # word "install" never appears, and an unpinned one drifts like any other.
    #
    # `--from` belongs here with the other two. Without it `uvx --from
    # ruff==0.15.8 ruff check .` -- the documented way to pin uvx -- was read as
    # an invocation with no install anywhere in the file, and the gate failed a
    # correctly pinned command. A check that rejects the right answer is one
    # people route around.
    r"|(?:uv\s+run|uvx|uv\s+tool\s+run|pipx\s+run)\s+(?:--with|--spec|--from))\b"
)

# The ephemeral runners take their package in a repeatable option, and any one
# of the repeats can be ruff: `uv run --with black --with ruff==0.15.8 ruff
# check .`. Reading only the option the verb itself matched saw `black`, found
# no ruff install in the file, and failed a command that had pinned it.
EPHEMERAL_PKG = re.compile(r"(?:--with|--spec|--from)(?:\s+|=)(?P<pkg>\S+)")

# An ephemeral runner on its own. `uv run --project . --with ruff==0.15.8 ruff
# check .` puts an ordinary option between the runner and the package option,
# so requiring `--with` to follow the runner immediately missed the install and
# failed a correctly pinned command.
EPHEMERAL_RUNNER = re.compile(r"(?:uv\s+run|uvx|uv\s+tool\s+run|pipx\s+run)(?![\w-])")

# `ruff` as its own token: not `ruff-pre-commit`, not `logs/ruff-results.json`,
# not `ruff-lint` (a step name). Captures an exact pin when one is present.
RUFF_TOKEN = re.compile(r"""(?<![\w.\-/])ruff(?![\w\-])(?:\s*==\s*(?P<pin>\d+\.\d+(?:\.\d+)?))?""")

# Runners that put another command in front of ruff. Requiring the segment to
# START with `ruff` meant `uv run ruff check .` and `python -m ruff check .`
# were not invocations at all, so a file using one and installing nothing
# inherited the runner's ruff without this check noticing.
_WRAPPERS = (
    r"uv\s+run",
    r"uvx",
    r"uv\s+tool\s+run",
    r"poetry\s+run",
    r"pipx\s+run",
    r"pdm\s+run",
    r"hatch\s+run",
    r"npx(?:\s+--yes)?",
    r"python3?\s+-m",
    r"nox\s+-s",
    r"tox\s+-e",
)

# A segment that runs the ruff binary rather than installing it. The leading
# prefix absorbs YAML's two ways of introducing a command -- `- run: ruff check`
# and a bare line inside a `run: |` block -- so an invocation is recognised in
# both without `- name: ruff-lint results` counting as one, and any of the
# wrappers above may sit between.
# Options may sit between the wrapper and ruff: `uv run --with ruff ruff
# check .` puts `--with ruff` in the gap, and requiring ruff to follow the
# wrapper immediately meant neither the temporary install nor the
# invocation was seen.
_OPTIONS = r"(?:-{1,2}[\w][\w\-]*(?:=\S+)?(?:\s+(?!ruff\b)\S+)?\s+)*"

# `RUN ruff check .` is a Dockerfile's shell form. It carries no colon, so
# the YAML `key:` prefix never matched it, and a Dockerfile could run ruff
# without installing it and still pass this gate.
RUFF_INVOCATION = re.compile(
    r"^\s*(?:-\s*)?(?:(?:[\w.\-]+:\s*)|(?:RUN\s+))?"
    r"(?:(?:" + "|".join(_WRAPPERS) + r")\s+" + _OPTIONS + r")?"
    r"ruff(?![\w\-])"
)

# Dockerfile exec form: `CMD ["ruff", "check", "."]` / `ENTRYPOINT ["ruff", …]`.
# No shell is involved, so the segment never begins with a bare `ruff`.
EXEC_FORM_RUFF = re.compile(
    r"(?:CMD|ENTRYPOINT|RUN)\s*\[\s*"
    r'(?:"ruff"|"python3?"\s*,\s*"-m"\s*,\s*"ruff")'
)

# The ruff-pre-commit repo block's `rev:`. Anchored to the repo URL so an
# unrelated `rev:` in the file cannot be mistaken for ruff's.
PRE_COMMIT_REV = re.compile(
    r"""-\s*repo:\s*https://github\.com/astral-sh/ruff-pre-commit\s*\n(?:\s*#.*\n)*\s*rev:\s*v?(\d+\.\d+\.\d+)""",
)


def _strip_comment(line: str, quote: str | None = None) -> tuple[str, str | None]:
    """Drop a trailing comment, honouring quotes AND backslash escapes.

    A naive "cut at the first ` #`" truncated `run: echo "a # b" && pip install
    ruff` at the quoted hash and never saw the install -- a fail-open path in a
    check whose entire job is to fail closed. Escapes matter for the same
    reason: in `echo "a\\" # b" && pip install ruff` the backslash escapes the
    quote, so the `#` is NOT inside a string and everything after it really is a
    comment -- while a stripper that ignores escapes thinks the string is still
    open and keeps the whole line. Either way round, guessing loses an install.

    Applied to each PHYSICAL line, carrying the open-quote state in and back
    out, so a quoted string spanning a `\\`-continuation is tracked through the
    join rather than reset at it -- while a comment still ends where its own
    line does. Stripping the joined line instead got the quote state right and
    the comment boundary wrong: a comment ending in `\\` swallowed the command
    on the next line, which in a check that exists to find unpinned installs
    means it stops seeing one.
    """
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index], quote
    return line, quote


def _is_continuation(line: str) -> bool:
    """Does this stripped line end in a continuation backslash?

    An ODD number of trailing backslashes continues the line; an even number is
    an escaped backslash that ends it. `RUN echo a\\\\` is a complete command.
    """
    trailing = len(line) - len(line.rstrip("\\"))
    return trailing % 2 == 1


# A YAML `key: 'value'` scalar. The quotes are YAML's, not the shell's -- YAML
# removes them before the runner ever sees a command -- so `run: 'pip install
# ruff'` is an ordinary unquoted install.
#: Keys whose value is a shell command. Restricted deliberately: the pattern
#: used to accept ANY `key:`, so `name: "lint with ruff"` was unwrapped and read
#: as a command, and a job title mentioning an install produced a finding about
#: a command nobody runs. A false failure on a correct workflow is how this
#: gate earns a suppression instead of a fix.
_COMMAND_KEYS = ("run", "cmd", "command", "commands", "script", "entrypoint")

_YAML_SCALAR = re.compile(
    r"""^(?P<lead>\s*(?:-\s*)?(?:"""
    + "|".join(_COMMAND_KEYS)
    + r""")\s*:\s*)(?P<quote>['"])(?P<body>.*)(?P=quote)\s*$""",
    re.IGNORECASE,
)

#: A command key whose quoted value does NOT close on the same line. The scalar
#: continues onto following lines, which this line-based reader cannot join, and
#: the shell-quote analysis then sees an unclosed quote and treats the rest as
#: quoted — hiding an install rather than reporting it. Reported instead.
_YAML_SCALAR_OPENER = re.compile(
    r"""^\s*(?:-\s*)?(?:"""
    + "|".join(_COMMAND_KEYS)
    + r""")\s*:\s*(?P<quote>['"])(?P<body>(?:[^'"]|(?!(?P=quote)).)*)$""",
    re.IGNORECASE,
)


def unterminated_yaml_scalar(line: str) -> bool:
    """True when a command key opens a quoted scalar it does not close.

    No `_YAML_SCALAR.match(...)` guard, because it would be dead: the opener's
    body can consume neither the closing quote nor anything after it, so a
    properly closed scalar cannot match it in the first place. Measured — with
    the guard removed, every closed scalar in the suite still reads False.
    """
    return bool(_YAML_SCALAR_OPENER.match(line))


def _unwrap_yaml_scalar(line: str) -> str:
    """Blank the YAML scalar quotes so shell-quote analysis sees the real command.

    Closing the "an install inside quotes is not an install" hole opened a worse
    one: `run: 'pip install ruff'` is valid YAML for an UNQUOTED shell command,
    and treating the delimiters as shell quotes made the install invisible
    altogether. That is a fail-open in the direction this check exists to guard.

    The quotes are replaced with spaces rather than removed, so every offset --
    and therefore every reported line number -- is unchanged. Only a value that
    is quoted end to end is unwrapped; `run: echo "a" && pip install ruff` is
    shell quoting and is left alone.

    YAML's own escape inside a single-quoted scalar ('' for a literal quote) is
    not decoded. It would shift offsets, and a command containing one is not a
    shape this estate writes; the quotes still come off, so the install is seen.
    """
    match = _YAML_SCALAR.match(line)
    if not match:
        return line
    start = match.start("quote")
    end = match.end("body")
    return line[:start] + " " + line[start + 1 : end] + " " + line[end + 1 :]


def _quoted_spans(text: str) -> list[tuple[int, int]]:
    """Index ranges inside single or double quotes, escape-aware.

    An install VERB inside quotes is not an install. `echo \'pip install
    ruff==0.15.8\' && ruff check .` records a pinned install that never happens,
    and the real invocation beside it then passes the gate on whatever ruff the
    runner already had -- the exact drift this check exists to catch, written
    as a string literal.

    The package ARGUMENT of a real install is usually quoted (`pip install
    "ruff==0.15.8"`), so this is used to place the verb, never to read the
    package.
    """
    spans: list[tuple[int, int]] = []
    quote: str | None = None
    start = 0
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                spans.append((start, index))
                quote = None
            continue
        if char in "'\"":
            quote = char
            start = index + 1
    if quote:  # unterminated: everything to the end is inside it
        spans.append((start, len(text)))
    return spans


def _inside(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


# Shell separators. Splitting on these keeps `pip install "ruff==0.15.8" &&
# ruff check .` from reading its own invocation as a second, unpinned install.
SEPARATOR = re.compile(r"&&|\|\||[;|]")


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def _logical_lines(
    text: str, yaml_scalars: bool = False
) -> list[tuple[str, list[tuple[int, int]]]]:
    """Comment-stripped lines with `\\` continuations joined, plus a line map.

    The map is `[(offset, line number), ...]` marking where each physical line
    begins inside the joined text, so a finding inside a 25-line `RUN pip
    install ... \\` block is reported against the line that actually names
    ruff rather than the line the block opens on.
    """
    joined: list[tuple[str, list[tuple[int, int]]]] = []
    buffer = ""
    line_map: list[tuple[int, int]] = []
    quote: str | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        # Comment stripped per physical line, but with the open-quote state
        # carried across the join. Both halves matter and they pull opposite
        # ways: a string can span a continuation, so the state has to survive
        # it, while a comment cannot, so the boundary must not.
        # YAML quoting comes off FIRST. The other order let a `#` inside a
        # quoted scalar survive `_strip_comment` (which saw it as quoted), and
        # unwrapping then exposed the comment as command text -- so
        # `run: 'echo hi # pip install ruff'` reported an unpinned install of a
        # command the shell never runs.
        raw_line = _unwrap_yaml_scalar(raw.rstrip()) if yaml_scalars else raw.rstrip()
        line, quote = _strip_comment(raw_line, quote)
        line = line.rstrip()
        line_map.append((len(buffer), number))
        if _is_continuation(line):
            buffer += line[:-1] + " "
            continue
        buffer += line
        joined.append((buffer.rstrip(), line_map))
        buffer = ""
        line_map = []
        quote = None
    if buffer:
        joined.append((buffer.rstrip(), line_map))
    return joined


def _line_at(line_map: list[tuple[int, int]], offset: int) -> int:
    """The physical line number that `offset` in the joined text came from."""
    number = line_map[0][1]
    for start, candidate in line_map:
        if start > offset:
            break
        number = candidate
    return number


def _segments(line: str):
    """Shell segments of a logical line, with each one's offset into it."""
    position = 0
    for match in SEPARATOR.finditer(line):
        yield position, line[position : match.start()]
        position = match.end()
    yield position, line[position:]


def _install_spans(segment: str) -> list[tuple[int, str]]:
    """(offset, text) for every stretch of a segment that names an installed package.

    Two shapes, and the difference is where the package is:

      `pip install ruff==0.15.8 black` -- everything after the verb is packages.
      `uv run --with ruff==0.15.8 ruff check .` -- ONLY the token named by the
      package option is a package; the trailing `ruff` is the command being run,
      and counting it reported a second, unpinned install on a correctly pinned
      line.

    Verbs inside quotes are excluded. `echo 'pip install ruff==0.15.8' && ruff
    check .` recorded an install that never happens, and the real invocation
    beside it then passed on whatever ruff the runner already had.
    """
    quoted = _quoted_spans(segment)
    spans: list[tuple[int, str]] = []

    # EVERY install verb, not just the first: `uv run --with black --with
    # ruff==0.15.8` is one segment carrying two, and stopping at the first read
    # only `black`.
    verbs = [v for v in INSTALL_VERB.finditer(segment) if not _inside(v.start(), quoted)]
    for index, verb in enumerate(verbs):
        # Each verb owns the text up to the next, so a package list is never
        # counted twice.
        end_at = verbs[index + 1].start() if index + 1 < len(verbs) else len(segment)
        tail = segment[verb.end() : end_at]
        if not verb.group(0).rstrip().endswith(("--with", "--spec", "--from")):
            spans.append((verb.end(), tail))
            continue
        # The verb swallowed one option, so its package is the token straight
        # after it. `split()` not `split(" ")`: a tab between the package and
        # the command put `ruff check .` inside the package span.
        stripped = tail.lstrip()
        if stripped:
            spans.append((verb.end() + (len(tail) - len(stripped)), stripped.split()[0]))

    # An ephemeral runner may carry ordinary options before its package option
    # (`uv run --project . --with ruff==0.15.8`), so it is located separately
    # and every package option after it is read.
    for runner in EPHEMERAL_RUNNER.finditer(segment):
        if _inside(runner.start(), quoted):
            continue
        tail = segment[runner.end() :]
        spans.extend(
            (runner.end() + extra.start("pkg"), extra.group("pkg"))
            for extra in EPHEMERAL_PKG.finditer(tail)
            if not _inside(runner.end() + extra.start("pkg"), quoted)
        )

    # A verb and a runner can name the same package; keep one span per offset.
    return list({offset: (offset, text) for offset, text in spans}.values())


def scan_file(path: Path, rel: str) -> tuple[list[tuple[str, str | None]], bool, list[str]]:
    """Ruff installs found in one file, whether it invokes ruff, and any problems.

    Each install is `(location, version or None)`; None means the install did
    not pin a version.

    The problems are lines this reader cannot honestly parse. There is exactly
    one shape today — a command key opening a quoted scalar it does not close —
    and it is reported rather than skipped because skipping it is fail-OPEN:
    the shell-quote analysis sees an unclosed quote, treats everything after it
    as quoted, and an unpinned install inside becomes invisible.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"{rel} could not be read ({exc.__class__.__name__})")
        raise SystemExit(1) from exc

    installs: list[tuple[str, str | None]] = []
    invokes = False
    problems: list[str] = []
    # YAML surfaces need their scalar quoting removed first; a Dockerfile's
    # quotes are the shell's and must be left in place.
    is_yaml = path.suffix.lower() in {".yml", ".yaml"}
    if is_yaml:
        for number, raw in enumerate(text.splitlines(), start=1):
            if unterminated_yaml_scalar(raw.rstrip()):
                problems.append(
                    f"{rel}:{number} opens a quoted YAML scalar that does not close on "
                    "the same line — this reader joins shell continuations, not YAML "
                    "ones, and would treat the rest as quoted and miss an install "
                    "inside it. Use a block scalar (`run: |`)."
                )
    for line, line_map in _logical_lines(text, yaml_scalars=is_yaml):
        for offset, segment in _segments(line):
            for base, text in _install_spans(segment):
                for token in RUFF_TOKEN.finditer(text):
                    position = offset + base + token.start()
                    number = _line_at(line_map, position)
                    installs.append((f"{rel}:{number}", token.group("pin")))

            # Checked whether or not the segment installed something. It was an
            # `elif`, so `uv run --with black ruff check .` -- an install of a
            # different package, then ruff run from whatever the runner already
            # had -- recorded no ruff install and no invocation either, and a
            # file whose only use of ruff was that line passed the gate.
            # A segment that installs ruff and runs it in the same breath is
            # both, and reporting both is correct: the install is what the
            # invocation is measured against.
            if RUFF_INVOCATION.search(segment) or EXEC_FORM_RUFF.search(segment):
                invokes = True
    return installs, invokes, problems


def ruff_surfaces() -> tuple[dict[str, str], list[str]]:
    """Map "<location>" -> pinned version, plus a list of problems found."""
    pins: dict[str, str] = {}
    problems: list[str] = []
    seen: set[Path] = set()

    for pattern in SCAN_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if not path.is_file() or path in seen:
                continue
            if EXCLUDED_DIRS.intersection(path.parts):
                continue
            seen.add(path)
            rel = str(path.relative_to(REPO_ROOT))
            installs, invokes, unreadable = scan_file(path, rel)
            problems.extend(unreadable)

            for location, version in installs:
                if version is None:
                    problems.append(
                        f"{location} installs ruff without pinning a version — it will "
                        "run whatever ruff is latest on the day the job runs"
                    )
                    continue
                # Two installs can share a location: `pip install ruff==0.15.8 &&
                # pip install ruff==0.16.4` is one line, so keying the map by
                # location alone let the second silently overwrite the first and
                # the divergence vanished from the very report meant to show it.
                key = location
                suffix = 2
                while key in pins and pins[key] != version:
                    key = f"{location} (#{suffix})"
                    suffix += 1
                pins[key] = version

            if invokes and not installs:
                problems.append(
                    f"{rel} runs ruff but never installs it — it inherits whatever "
                    "version the runner image happens to carry"
                )

    return pins, problems


def pre_commit_pin() -> str:
    """The ruff version `.pre-commit-config.yaml` resolves to."""
    if not PRE_COMMIT.is_file():
        _fail(".pre-commit-config.yaml is missing")
        raise SystemExit(1)
    text = PRE_COMMIT.read_text(encoding="utf-8")
    match = PRE_COMMIT_REV.search(text)
    if not match:
        _fail(
            ".pre-commit-config.yaml has no readable rev for astral-sh/ruff-pre-commit "
            "-- cannot verify it agrees with the workflows"
        )
        raise SystemExit(1)
    return match.group(1)


def main() -> int:
    pins, problems = ruff_surfaces()
    if not pins and not problems:
        _fail("no scanned file installs ruff -- expected at least one `ruff==<version>`")
        return 1

    hook = pre_commit_pin()
    surfaces = dict(pins)
    surfaces[".pre-commit-config.yaml"] = hook

    width = max(len(name) for name in surfaces)
    for name in sorted(surfaces):
        print(f"  {name:{width}}  ruff {surfaces[name]}")

    versions = sorted(set(surfaces.values()))
    if len(versions) > 1:
        problems.append(
            "ruff is pinned to more than one version across the surfaces that lint "
            f"this tree: {', '.join(versions)}"
        )

    if problems:
        print()
        for problem in problems:
            _fail(problem)
        print(
            "\nTwo ruff versions formatting one tree is a split gate: a file that "
            "pre-commit rewrites can be rejected by CI, and vice versa. An unpinned "
            "install is the same split with the second version chosen for you at run "
            "time. Pin every surface above to one version -- pip pins are written "
            "`ruff==X.Y.Z` and the pre-commit rev `vX.Y.Z`.",
            file=sys.stderr,
        )
        return 1

    print(f"\nRuff pin alignment: PASSED — {len(surfaces)} surfaces, all on ruff {versions[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
