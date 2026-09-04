"""What The Lab can write, and what it can prove about what it wrote.

The distinction this module exists for
--------------------------------------
The Lab generates code in any language a prompt names. That is not the same
as *handling* a language, and conflating the two is how a code platform ships
output nobody checked. So every entry here carries two separate facts: the
language, and the **verification tier** The Lab can actually reach for it —
measured from the binaries on PATH at the moment you ask, not declared.

Measured, not declared, is the whole design. `workers/the-lab` builds from
`python:3.11-slim` with fastapi, starlette, uvicorn and httpx. There is no
compiler, no node, no go, no rustc, no formatter, no linter and no test
runner in that image, and `/lab/run` answers 501 because AST import-blocking
was never a sandbox. A declared matrix would say The Lab supports twelve
languages. The measured one says it can parse one and prove nothing about
any of them, which is the fact an operator needs.

What replaced what
------------------
`workers/the-lab/main.py` defines `ALLOWED_LANGUAGES`, a set of twelve
strings, and references it exactly once — at its own definition. Nothing
validates against it, nothing exposes it, and a request naming any other
language is interpolated straight into a prompt. It was a capability claim
with no capability behind it.

Verification tiers
------------------
Each tier subsumes the ones before it.

``NONE``   Generated text. Nothing has looked at it.
``PARSE``  Syntax is checkable without leaving the process.
``LINT``   A linter is on PATH and can be run against it.
``TYPE``   A type checker is on PATH.
``TEST``   A runtime and test runner are on PATH, so behaviour can be
           exercised rather than inspected.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

__all__ = [
    "LANGUAGES",
    "Language",
    "Tool",
    "Verification",
    "language",
    "resolve_language",
    "skills_matrix",
    "verification_for",
]


class Verification(str, Enum):
    NONE = "none"
    PARSE = "parse"
    LINT = "lint"
    TYPE = "type"
    TEST = "test"


#: Ascending capability. `_rank` compares tiers by this order rather than by
#: the enum's string value, which would sort alphabetically and rank LINT
#: above TEST.
_TIER_ORDER: tuple[Verification, ...] = (
    Verification.NONE,
    Verification.PARSE,
    Verification.LINT,
    Verification.TYPE,
    Verification.TEST,
)


def _rank(tier: Verification) -> int:
    return _TIER_ORDER.index(tier)


@dataclass(frozen=True)
class Tool:
    """A binary that, when present, unlocks a verification tier."""

    binary: str
    purpose: str
    unlocks: Verification

    def to_dict(self) -> dict[str, object]:
        return {"binary": self.binary, "purpose": self.purpose, "unlocks": self.unlocks.value}


@dataclass(frozen=True)
class Language:
    id: str
    name: str
    family: str
    paradigms: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    toolchain: tuple[Tool, ...] = ()
    #: The tier reachable with no external binary at all. Python is PARSE
    #: because `ast` is in the standard library of the process doing the
    #: asking; nothing else is.
    intrinsic: Verification = Verification.NONE
    notes: str = ""

    def names(self) -> tuple[str, ...]:
        return (self.id, *self.aliases)

    def verification(self, which: Optional[Callable[[str], Optional[str]]] = None) -> Verification:
        """The highest tier reachable right now, on this machine.

        Takes `which` so a test can describe a toolchain without installing
        one, and so the answer is always about a real PATH rather than a
        remembered one.
        """
        look = which or shutil.which
        best = self.intrinsic
        for tool in self.toolchain:
            if look(tool.binary) and _rank(tool.unlocks) > _rank(best):
                best = tool.unlocks
        return best

    def missing_tools(
        self, which: Optional[Callable[[str], Optional[str]]] = None
    ) -> tuple[Tool, ...]:
        look = which or shutil.which
        return tuple(tool for tool in self.toolchain if not look(tool.binary))

    def to_dict(self, which: Optional[Callable[[str], Optional[str]]] = None) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "family": self.family,
            "paradigms": list(self.paradigms),
            "aliases": list(self.aliases),
            "intrinsic": self.intrinsic.value,
            "verification": self.verification(which).value,
            "toolchain": [t.to_dict() for t in self.toolchain],
            "missing_tools": [t.binary for t in self.missing_tools(which)],
            "notes": self.notes,
        }


def _t(binary: str, purpose: str, unlocks: Verification) -> Tool:
    return Tool(binary=binary, purpose=purpose, unlocks=unlocks)


LANGUAGES: tuple[Language, ...] = (
    Language(
        id="python",
        name="Python",
        family="scripting",
        paradigms=("imperative", "object-oriented", "functional"),
        aliases=("py", "python3"),
        intrinsic=Verification.PARSE,
        toolchain=(
            _t("ruff", "lint and format", Verification.LINT),
            _t("mypy", "static types", Verification.TYPE),
            _t("pytest", "run the tests", Verification.TEST),
        ),
        notes="The only language whose syntax The Lab can check with no binary at all.",
    ),
    Language(
        id="javascript",
        name="JavaScript",
        family="web",
        paradigms=("imperative", "functional", "prototype-based"),
        aliases=("js", "node"),
        toolchain=(
            _t("eslint", "lint", Verification.LINT),
            _t("node", "run and test", Verification.TEST),
        ),
    ),
    Language(
        id="typescript",
        name="TypeScript",
        family="web",
        paradigms=("imperative", "functional", "structurally typed"),
        aliases=("ts",),
        toolchain=(
            _t("eslint", "lint", Verification.LINT),
            _t("tsc", "type-check and compile", Verification.TYPE),
            _t("node", "run and test", Verification.TEST),
        ),
    ),
    Language(
        id="go",
        name="Go",
        family="systems",
        paradigms=("imperative", "concurrent"),
        aliases=("golang",),
        toolchain=(
            _t("gofmt", "format and parse", Verification.PARSE),
            _t("go", "vet, build and test", Verification.TEST),
        ),
    ),
    Language(
        id="rust",
        name="Rust",
        family="systems",
        paradigms=("imperative", "functional", "ownership"),
        aliases=("rs",),
        toolchain=(
            _t("rustfmt", "format and parse", Verification.PARSE),
            _t("clippy-driver", "lint", Verification.LINT),
            _t("cargo", "build and test", Verification.TEST),
        ),
    ),
    Language(
        id="java",
        name="Java",
        family="jvm",
        paradigms=("object-oriented", "imperative"),
        toolchain=(
            _t("javac", "compile and type-check", Verification.TYPE),
            _t("java", "run", Verification.TEST),
        ),
    ),
    Language(
        id="kotlin",
        name="Kotlin",
        family="jvm",
        paradigms=("object-oriented", "functional"),
        aliases=("kt",),
        toolchain=(_t("kotlinc", "compile and type-check", Verification.TYPE),),
    ),
    Language(
        id="scala",
        name="Scala",
        family="jvm",
        paradigms=("object-oriented", "functional"),
        toolchain=(_t("scalac", "compile and type-check", Verification.TYPE),),
    ),
    Language(
        id="c",
        name="C",
        family="systems",
        paradigms=("imperative", "procedural"),
        toolchain=(
            _t("gcc", "compile", Verification.TYPE),
            _t("clang-tidy", "lint", Verification.LINT),
        ),
    ),
    Language(
        id="cpp",
        name="C++",
        family="systems",
        paradigms=("object-oriented", "generic", "imperative"),
        aliases=("c++", "cplusplus"),
        toolchain=(
            _t("g++", "compile", Verification.TYPE),
            _t("clang-tidy", "lint", Verification.LINT),
        ),
    ),
    Language(
        id="csharp",
        name="C#",
        family="dotnet",
        paradigms=("object-oriented", "imperative"),
        aliases=("cs", "c#"),
        toolchain=(_t("dotnet", "build and test", Verification.TEST),),
    ),
    Language(
        id="ruby",
        name="Ruby",
        family="scripting",
        paradigms=("object-oriented", "dynamic"),
        aliases=("rb",),
        toolchain=(
            _t("rubocop", "lint", Verification.LINT),
            _t("ruby", "run and test", Verification.TEST),
        ),
    ),
    Language(
        id="php",
        name="PHP",
        family="web",
        paradigms=("imperative", "object-oriented"),
        toolchain=(_t("php", "lint and run", Verification.TEST),),
    ),
    Language(
        id="swift",
        name="Swift",
        family="systems",
        paradigms=("object-oriented", "functional", "protocol-oriented"),
        toolchain=(_t("swiftc", "compile and type-check", Verification.TYPE),),
    ),
    Language(
        id="haskell",
        name="Haskell",
        family="functional",
        paradigms=("purely functional", "lazy"),
        aliases=("hs",),
        toolchain=(_t("ghc", "compile and type-check", Verification.TYPE),),
    ),
    Language(
        id="elixir",
        name="Elixir",
        family="functional",
        paradigms=("functional", "concurrent", "actor"),
        aliases=("ex",),
        toolchain=(_t("elixir", "compile and run", Verification.TEST),),
    ),
    Language(
        id="lua",
        name="Lua",
        family="scripting",
        paradigms=("imperative", "prototype-based"),
        toolchain=(_t("luac", "parse", Verification.PARSE), _t("lua", "run", Verification.TEST)),
    ),
    Language(
        id="r",
        name="R",
        family="data",
        paradigms=("functional", "array"),
        toolchain=(_t("Rscript", "run", Verification.TEST),),
    ),
    Language(
        id="julia",
        name="Julia",
        family="data",
        paradigms=("multiple dispatch", "functional"),
        aliases=("jl",),
        toolchain=(_t("julia", "run and test", Verification.TEST),),
    ),
    Language(
        id="perl",
        name="Perl",
        family="scripting",
        paradigms=("imperative", "procedural"),
        aliases=("pl",),
        toolchain=(_t("perl", "syntax check and run", Verification.TEST),),
    ),
    Language(
        id="shell",
        name="Shell",
        family="scripting",
        paradigms=("imperative",),
        aliases=("bash", "sh", "zsh"),
        toolchain=(
            _t("shellcheck", "lint", Verification.LINT),
            _t("bash", "syntax check with -n", Verification.PARSE),
        ),
    ),
    Language(
        id="sql",
        name="SQL",
        family="data",
        paradigms=("declarative", "relational"),
        toolchain=(_t("sqlfluff", "lint and parse", Verification.LINT),),
    ),
    Language(
        id="html",
        name="HTML",
        family="markup",
        paradigms=("declarative",),
        toolchain=(_t("tidy", "validate", Verification.LINT),),
    ),
    Language(
        id="css",
        name="CSS",
        family="markup",
        paradigms=("declarative",),
        toolchain=(_t("stylelint", "lint", Verification.LINT),),
    ),
    Language(
        id="yaml",
        name="YAML",
        family="config",
        paradigms=("declarative",),
        aliases=("yml",),
        toolchain=(_t("yamllint", "lint", Verification.LINT),),
    ),
    Language(
        id="json",
        name="JSON",
        family="config",
        paradigms=("declarative",),
        intrinsic=Verification.PARSE,
        notes="`json` is in the standard library, so syntax is always checkable.",
    ),
    Language(
        id="markdown",
        name="Markdown",
        family="markup",
        paradigms=("declarative",),
        aliases=("md",),
        toolchain=(_t("markdownlint", "lint", Verification.LINT),),
    ),
    Language(
        id="dockerfile",
        name="Dockerfile",
        family="config",
        paradigms=("declarative",),
        aliases=("docker",),
        toolchain=(_t("hadolint", "lint", Verification.LINT),),
    ),
    Language(
        id="terraform",
        name="Terraform",
        family="config",
        paradigms=("declarative", "infrastructure"),
        aliases=("hcl", "tf"),
        toolchain=(_t("terraform", "validate and plan", Verification.TYPE),),
    ),
)

_BY_NAME: dict[str, Language] = {}
for _lang in LANGUAGES:
    for _name in _lang.names():
        _BY_NAME[_name] = _lang


def language(language_id: str) -> Optional[Language]:
    """Look up by canonical id only."""
    for entry in LANGUAGES:
        if entry.id == language_id:
            return entry
    return None


def resolve_language(name: str) -> Optional[Language]:
    """Look up by id or alias, case- and whitespace-insensitively.

    A caller writing "Golang", "C++" or "node" means a language this
    registry knows. Refusing them because the spelling differs would push
    callers back to the free-form string this registry replaced.
    """
    return _BY_NAME.get(name.strip().lower())


def verification_for(
    name: str, which: Optional[Callable[[str], Optional[str]]] = None
) -> Verification:
    """The tier reachable for this language, or NONE for one we do not know.

    An unknown language is NONE rather than an error, because the caller's
    question is "what can you prove about this", and the honest answer for
    something unrecognised is "nothing".
    """
    entry = resolve_language(name)
    return entry.verification(which) if entry else Verification.NONE


def skills_matrix(which: Optional[Callable[[str], Optional[str]]] = None) -> dict[str, object]:
    """The whole picture: what is claimed, and what is actually reachable."""
    entries = [entry.to_dict(which) for entry in LANGUAGES]
    by_tier: dict[str, int] = {tier.value: 0 for tier in Verification}
    for entry in entries:
        by_tier[str(entry["verification"])] += 1
    families: dict[str, list[str]] = {}
    for entry in LANGUAGES:
        families.setdefault(entry.family, []).append(entry.id)
    return {
        "languages": entries,
        "total": len(entries),
        "by_verification": by_tier,
        "families": {k: sorted(v) for k, v in sorted(families.items())},
        # The headline number an operator needs: generation is unconstrained,
        # and this is how much of it anything checks.
        "verifiable": sum(1 for e in entries if e["verification"] != Verification.NONE.value),
    }
