"""SEC-020's premise checker must see what it claims to see.

Every case here is a bypass a reviewer reported on #1376 and that the first
version of `check_sec_020` got wrong. They are kept as tests because the
suppression in `SECURITY_ALERT_REGISTER.md` is only honest while the checker
behind it actually refuses what the entry says it refuses -- and the first
version claimed to reject a variable algorithm while reporting it as pinned.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "cdp", Path(__file__).resolve().parents[1] / "scripts" / "check_disposition_premises.py"
)
assert _SPEC and _SPEC.loader
cdp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cdp)


def _shapes(src: str) -> list[str]:
    return [shape for _line, shape, _count in cdp._jwt_decode_sites(ast.parse(src))]


def test_a_literal_algorithm_is_pinned():
    assert _shapes('jwt.decode(t, k, algorithms=["HS256"])') == ["literal"]


def test_a_module_constant_is_resolved_not_merely_assumed():
    """`algorithms=[ALGORITHM]` is chosen by this code -- now verified, not claimed.

    This test asserted the shape `reference` for both cases below. That shape is
    retired: it meant "a bare name or dotted attribute, which resolves to
    something this code chooses", and the checker never resolved anything. The
    first case is now `constant`, because the binding is read and found to be a
    string literal.

    The second case CHANGED VERDICT, deliberately. `cfg.ALGORITHM` cannot be
    resolved from this module, and an unresolvable algorithm is refused rather
    than assumed safe. No decode site in this estate uses a dotted algorithm --
    all twelve use bare names -- so the tightening costs nothing today, and the
    refusal names the fix (bind it to a module constant).
    """
    assert _shapes('ALG = "RS256"\njwt.decode(t, k, algorithms=[ALG])') == ["constant"]
    dotted = _shapes("jwt.decode(t, k, algorithms=[cfg.ALGORITHM])")[0]
    assert dotted not in cdp._ADMISSIBLE_SHAPES, dotted
    assert "dotted attribute" in dotted, dotted


def test_a_token_derived_algorithm_is_refused():
    """REGRESSION: reported as `pinned`, and it is the attack verbatim.

    `get_unverified_header(token)["alg"]` lets the attacker pick the algorithm
    while the verifier holds an asymmetric key -- exactly the confusion SEC-020
    suppresses. Raised by sourcery, codex, coderabbit and codeant on #1376.
    """
    for src in (
        'jwt.decode(t, k, algorithms=[jwt.get_unverified_header(t)["alg"]])',
        'jwt.decode(t, k, algorithms=[hdr["alg"]])',
        'jwt.decode(t, k, algorithms=[f"{a}"])',
        "jwt.decode(t, k, algorithms=[*algs])",
    ):
        assert _shapes(src) == ["algorithm is computed, so the token could choose it"], src


def test_a_non_string_algorithm_is_refused():
    assert _shapes("jwt.decode(t, k, algorithms=[256])") == [
        "algorithm is a non-string constant 256"
    ]


def test_an_aliased_jwt_import_is_still_scanned():
    """REGRESSION: `verifier.decode(...)` returned no sites at all.

    The checker matched four hard-coded receiver names, so an aliased import
    could widen its allowlist to two algorithms and the gate stayed green
    having never looked at it. Raised by sourcery, codex and coderabbit.
    """
    src = 'from jose import jwt as verifier\nverifier.decode(t, k, algorithms=["HS256", "RS256"])'
    assert _shapes(src) == ["algorithms= names more than one"]
    ok = 'from jose import jwt as verifier\nverifier.decode(t, k, algorithms=["HS256"])'
    assert _shapes(ok) == ["literal"]


def test_a_directly_imported_decode_is_still_scanned():
    """`from jose.jwt import decode` has no receiver to match on."""
    src = 'from jose.jwt import decode\ndecode(t, k, algorithms=["HS256", "RS256"])'
    assert _shapes(src) == ["algorithms= names more than one"]


def test_an_aliased_plain_import_is_still_scanned():
    src = 'import jwt as j\nj.decode(t, k, algorithms=[tok["alg"]])'
    assert _shapes(src) == ["algorithm is computed, so the token could choose it"]


def test_a_missing_allowlist_is_refused():
    assert _shapes("jwt.decode(t, k)") == ["no algorithms= argument at all"]


def test_a_non_list_allowlist_is_refused():
    assert _shapes("jwt.decode(t, k, algorithms=algs)") == ["algorithms= is not a literal list"]


def test_every_manifest_pinning_jose_is_listed_and_at_the_assessed_version():
    """The entry names eight manifests; the census only covers one of them."""
    assert cdp._declared_jose_versions() == []
    assert len(cdp._SEC_020_MANIFESTS) == 8


def test_the_entry_cites_no_other_advisory_id():
    """An ID anywhere in an accepting entry is collected as an accepted risk.

    REGRESSION: an earlier draft cited PyJWT's own algorithm-confusion CVE as a
    comparison, which `accepted_risk_register.py` would have registered as an
    accepted risk and allowed to license a `.trivyignore` entry. Raised by
    `chatgpt-codex-connector` on #1376.
    """
    register = Path(__file__).resolve().parents[1] / "SECURITY_ALERT_REGISTER.md"
    entry = register.read_text(encoding="utf-8").split("### SEC-020")[1].split("\n### ")[0]
    import re

    # Upper-cased to match `accepted_risk_register.py`, which collects IDs with
    # `match.upper()`. Comparing raw spellings failed this test on the entry's
    # own `GHSA-6c5p-j8vq-pqhj` -- a case difference, not an extra advisory.
    found = {m.upper() for m in re.findall(r"(?:CVE|GHSA|PYSEC)-[0-9A-Za-z-]+", entry)}
    assert found <= cdp._SEC_020_ADVISORY_IDS, (
        "SEC-020 cites advisory IDs that are not its own, which registers them as "
        f"accepted risks: {sorted(found - cdp._SEC_020_ADVISORY_IDS)}"
    )


def test_a_qualified_receiver_is_still_scanned():
    """REGRESSION: `jose.jwt.decode(...)` was skipped entirely.

    The matcher required a bare `ast.Name` receiver, so every qualified
    spelling had an `ast.Attribute` base and never reached the allowlist
    check. Raised by `llamapreview` on #1376.
    """
    assert _shapes('jose.jwt.decode(t, k, algorithms=["HS256", "RS256"])') == [
        "algorithms= names more than one"
    ]
    assert _shapes('pkg.jose.jwt.decode(t, k, algorithms=["HS256"])') == ["literal"]


def test_an_unrelated_decode_is_not_claimed():
    """The matcher must not sweep in decoders that are not JWT at all."""
    assert _shapes('base64.decode(blob, algorithms=["x", "y"])') == []
    assert _shapes("payload.decode('utf-8')") == []


def test_the_pass_message_count_comes_from_the_measured_run():
    """REGRESSION: the count was re-derived by a second full-tree walk.

    `_pinned_decode_sites` parsed every `.py` file again purely to format the
    pass line, roughly doubling the script's cost. Raised by cubic on #1376.
    """
    cdp._SEC_020_PINNED[:] = []
    assert cdp._pinned_decode_sites() == 0, "no run yet reports 0, not a guess"
    cdp._SEC_020_PINNED[:] = [12]
    assert cdp._pinned_decode_sites() == 12


# ---------------------------------------------------------------------------
# Assignment aliases. Raised by coderabbit on #1376 as a durability gap:
# `_jwt_bound_names` resolved imports but not assignments, so a decode site
# reached through `verifier = jose.jwt` was invisible -- while the register
# claimed coverage of every decode site. The gap is real; the claim being
# wider than the capability is the defect.
# ---------------------------------------------------------------------------


def test_an_assignment_alias_is_resolved():
    """REGRESSION: `verifier = jose.jwt` then `verifier.decode(...)`."""
    src = 'import jose\nverifier = jose.jwt\nverifier.decode(t, k, algorithms=["HS256", "RS256"])'
    sites = cdp._jwt_decode_sites(ast.parse(src))
    assert sites, "a decode reached through an assignment alias must be seen"
    assert sites[0][1] == "algorithms= names more than one", sites


def test_an_assigned_decode_function_is_resolved():
    """`d = jwt.decode` then `d(...)` -- no receiver at the call site at all."""
    src = 'from jose import jwt\nd = jwt.decode\nd(t, k, algorithms=["HS256", "RS256"])'
    sites = cdp._jwt_decode_sites(ast.parse(src))
    assert sites, "an assigned decode function must be seen"
    assert sites[0][1] == "algorithms= names more than one", sites


def test_an_alias_built_from_another_alias_is_resolved():
    """Why the resolution runs twice: an alias can be defined from an alias."""
    src = 'import jose\na = jose.jwt\nb = a\nb.decode(t, k, algorithms=["HS256", "RS256"])'
    sites = cdp._jwt_decode_sites(ast.parse(src))
    assert sites, "a chained alias must be seen"
    assert sites[0][1] == "algorithms= names more than one", sites


def test_a_pinned_site_reached_through_an_alias_still_passes():
    """Widening the matcher must not start failing correct code."""
    src = 'import jose\nv = jose.jwt\nv.decode(t, k, algorithms=["HS256"])'
    assert cdp._jwt_decode_sites(ast.parse(src)) == [(3, "literal", 1)]


def test_an_aliased_non_jwt_decoder_is_still_not_claimed():
    """The boundary: resolving aliases must not sweep in unrelated decoders."""
    src = 'import base64\nb = base64\nb.decode(blob, algorithms=["x", "y"])'
    assert cdp._jwt_decode_sites(ast.parse(src)) == []


def test_an_assignment_inside_a_statement_body_is_resolved():
    """The register says so, so it has to be true.

    `ast.walk` enters every statement body, so an alias assigned inside an
    `if`, `try`/`except`, `with` or loop is resolved. The first wording of the
    coverage bound said it did not resolve "a conditional", which readers would
    take as the `if` statement -- UNDERSTATING the coverage. Raised by cubic on
    #1376. Understating a bound is the same defect as overstating it, pointed
    the other way: either way the entry describes a checker that isn't this one.

    The bound names four statement forms and this test covered two of them --
    `if` and `try` -- which is the same shortfall one level down, also raised by
    cubic. All four are exercised here.
    """
    for src in (
        'import jose\nif flag:\n    v = jose.jwt\nv.decode(t, k, algorithms=["A", "B"])',
        "import jose\ntry:\n    v = jose.jwt\nexcept ImportError:\n    v = None\n"
        'v.decode(t, k, algorithms=["A", "B"])',
        'import jose\nwith lock:\n    v = jose.jwt\nv.decode(t, k, algorithms=["A", "B"])',
        'import jose\nfor _ in range(1):\n    v = jose.jwt\nv.decode(t, k, algorithms=["A", "B"])',
        'import jose\nwhile flag:\n    v = jose.jwt\nv.decode(t, k, algorithms=["A", "B"])',
    ):
        sites = cdp._jwt_decode_sites(ast.parse(src))
        assert sites, src
        assert sites[0][1] == "algorithms= names more than one", sites


def test_the_forms_the_bound_excludes_really_are_unresolved():
    """A bound is only honest if the excluded forms are actually excluded.

    If one of these quietly started resolving, the entry would be understating
    again -- so the exclusions are pinned, not just the inclusions.
    """
    for src in (
        # conditional EXPRESSION, not an `if` statement
        'import jose\nv = jose.jwt if flag else None\nv.decode(t, k, algorithms=["A", "B"])',
        'import jose\nd = {"j": jose.jwt}\nd["j"].decode(t, k, algorithms=["A", "B"])',
        'import jose\n\n\ndef get():\n    return jose.jwt\n\n\nget().decode(t, k, algorithms=["A", "B"])',
    ):
        assert cdp._jwt_decode_sites(ast.parse(src)) == [], src


# ---------------------------------------------------------------------------
# Resolving the algorithm REFERENCE, not just its shape.
#
# codeant on #1376: the checker accepted any bare name as `reference`, having
# only CLAIMED such a name resolves to something this code chooses. It did not
# check. So the attack it already rejected needed moving up one line to pass:
#
#     alg = jwt.get_unverified_header(t)["alg"]    # the token picks it
#     jwt.decode(t, k, algorithms=[alg])           # -> accepted
#
# Reproduced before fixing. The name is now resolved against the module's own
# bindings, and against ONE hop of `from <module> import <name>`.
# ---------------------------------------------------------------------------


def test_a_token_derived_algorithm_laundered_through_a_local_is_rejected():
    """REGRESSION: the bypass codeant found, verbatim."""
    src = 'alg = jwt.get_unverified_header(t)["alg"]\njwt.decode(t, k, algorithms=[alg])'
    shape = _shapes(src)[0]
    assert shape not in cdp._ADMISSIBLE_SHAPES, shape
    assert "computed" in shape, shape


def test_a_module_constant_resolves_and_is_accepted():
    assert _shapes('ALGORITHM = "RS256"\njwt.decode(t, k, algorithms=[ALGORITHM])') == ["constant"]


def test_a_parameter_default_is_accepted_but_reported_apart():
    """Weaker than a constant on purpose: the DEFAULT is verified, not the callers."""
    src = 'def f(token, key, algorithm="HS256"):\n    return jwt.decode(token, key, algorithms=[algorithm])'
    assert _shapes(src) == ["parameter"]


def test_the_weakest_binding_decides():
    """One literal binding cannot make a name safe if another computes it."""
    src = 'A = "HS256"\nif x:\n    A = hdr["alg"]\njwt.decode(t, k, algorithms=[A])'
    shape = _shapes(src)[0]
    assert shape not in cdp._ADMISSIBLE_SHAPES, shape


def test_an_unresolvable_name_fails_closed():
    """ "I could not look" must never read the same as "I looked and it was fine"."""
    for src in (
        "jwt.decode(t, k, algorithms=[MYSTERY])",
        "def f(t, k, algorithm):\n    return jwt.decode(t, k, algorithms=[algorithm])",
        "hdr = parse(t)\njwt.decode(t, k, algorithms=[hdr.alg])",
    ):
        shape = _shapes(src)[0]
        assert shape not in cdp._ADMISSIBLE_SHAPES, (src, shape)


def test_an_imported_constant_resolves_one_hop(tmp_path):
    """`workers/infinity-auth/service.py` really does this, so refusing it would be a false alarm.

    It imports `JWT_ALGORITHM` from a sibling `config.py` that sets it to
    `"HS256"`. The stricter check flagged it as unresolvable until the resolver
    learned this one hop -- which is a real production site, not a hypothetical.
    """
    (tmp_path / "config.py").write_text('JWT_ALGORITHM = "HS256"\n', encoding="utf-8")
    service = tmp_path / "service.py"
    service.write_text(
        "from config import JWT_ALGORITHM\n"
        "payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])\n",
        encoding="utf-8",
    )
    sites = cdp._jwt_decode_sites(ast.parse(service.read_text()), service)
    assert [shape for _l, shape, _c in sites] == ["imported"]


def test_an_import_whose_source_is_not_a_literal_is_rejected(tmp_path):
    """Resolving the hop must not mean trusting whatever it finds."""
    (tmp_path / "config.py").write_text(
        'import os\n\nJWT_ALGORITHM = os.environ["ALG"]\n', encoding="utf-8"
    )
    service = tmp_path / "service.py"
    service.write_text(
        "from config import JWT_ALGORITHM\n"
        "payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])\n",
        encoding="utf-8",
    )
    sites = cdp._jwt_decode_sites(ast.parse(service.read_text()), service)
    shape = sites[0][1]
    assert shape not in cdp._ADMISSIBLE_SHAPES, shape
    assert "does not bind it to a string literal" in shape, shape


def test_an_import_with_no_source_file_fails_closed():
    """Without a file to resolve against, the answer is "unknown", not "fine"."""
    src = "from config import JWT_ALGORITHM\njwt.decode(t, k, algorithms=[JWT_ALGORITHM])"
    shape = cdp._jwt_decode_sites(ast.parse(src), None)[0][1]
    assert shape not in cdp._ADMISSIBLE_SHAPES, shape


def test_the_source_file_is_not_confused_with_the_receiver_path(tmp_path):
    """REGRESSION for a bug I introduced writing this.

    `_jwt_decode_sites` already had a local named `path` holding the dotted
    RECEIVER string from `_receiver_path` (`"jose.jwt"`). Adding a `path`
    parameter for the source file shadowed it, so the file argument arrived as
    the string `"jwt"` and resolution crashed on `'str' has no attribute
    'parent'`. Renamed to `source`; this test pins that a QUALIFIED receiver
    and an imported constant work together, which is the combination that broke.
    """
    (tmp_path / "settings.py").write_text('ALG = "HS256"\n', encoding="utf-8")
    service = tmp_path / "svc.py"
    service.write_text(
        "import jose\nfrom settings import ALG\njose.jwt.decode(token, key, algorithms=[ALG])\n",
        encoding="utf-8",
    )
    sites = cdp._jwt_decode_sites(ast.parse(service.read_text()), service)
    assert [shape for _l, shape, _c in sites] == ["imported"], sites


# ---------------------------------------------------------------------------
# Resolution has to happen in the SCOPE THE DECODE CALL SITS IN.
#
# The fix above resolved names against the whole module, so an unrelated
# default elsewhere in the file laundered every same-named parameter -- a
# bypass of that very fix, raised by codeant on #1376. Measured before fixing:
#
#     scope leak -> [(6, 'parameter', 1)]
#     isolated   -> [(2, "algorithm 'algorithm' is not bound ...", -1)]
#
# The same case passed in isolation and failed in the configuration where it
# matters, which is why these tests put the decoy in the file.
# ---------------------------------------------------------------------------

_SCOPE_LEAK = (
    'def helper(algorithm="HS256"):\n'
    "    return algorithm\n"
    "\n"
    "def verify(token, key, algorithm):\n"
    "    return jwt.decode(token, key, algorithms=[algorithm])\n"
)


def test_another_functions_default_does_not_launder_this_parameter():
    """REGRESSION: codeant's bypass, verbatim. `helper`'s default is not `verify`'s."""
    shape = _shapes(_SCOPE_LEAK)[0]
    assert shape not in cdp._ADMISSIBLE_SHAPES, shape
    assert "no default" in shape, shape


def test_the_decoy_is_what_makes_the_case_fail():
    """The same site without the decoy was already refused -- the leak was the decoy."""
    alone = "def verify(token, key, algorithm):\n    return jwt.decode(token, key, algorithms=[algorithm])\n"
    assert _shapes(alone)[0] not in cdp._ADMISSIBLE_SHAPES
    assert _shapes(_SCOPE_LEAK)[0] not in cdp._ADMISSIBLE_SHAPES


def test_a_parameter_shadows_a_module_constant_of_the_same_name():
    """The parameter is what runs, so the module constant must not resolve it."""
    src = 'ALG = "RS256"\ndef f(t, k, ALG):\n    return jwt.decode(t, k, algorithms=[ALG])'
    shape = _shapes(src)[0]
    assert shape not in cdp._ADMISSIBLE_SHAPES, shape


def test_a_nested_function_still_sees_an_enclosing_binding():
    """Scope-awareness must not become scope-blindness.

    A closure really does read the module constant and the enclosing
    parameter's default, so refusing them would be a false alarm -- the same
    defect as the leak, pointed the other way.
    """
    assert _shapes(
        'ALG = "RS256"\ndef outer():\n    def inner(t, k):\n        return jwt.decode(t, k, algorithms=[ALG])\n'
    ) == ["constant"]
    assert _shapes(
        'def outer(alg="HS256"):\n    def inner(t, k):\n        return jwt.decode(t, k, algorithms=[alg])\n'
    ) == ["parameter"]


def test_a_class_attribute_does_not_resolve_a_name_inside_a_method():
    """A method does not see class-level names unqualified -- that is a NameError.

    Accepting it would mean the checker passed code that cannot run. Written
    directly in the class body, the same name does resolve.
    """
    method = (
        "class V:\n"
        '    ALG = "HS256"\n'
        "    def f(self, t, k):\n"
        "        return jwt.decode(t, k, algorithms=[ALG])\n"
    )
    assert _shapes(method)[0] not in cdp._ADMISSIBLE_SHAPES
    body = 'class V:\n    ALG = "HS256"\n    x = jwt.decode(t, k, algorithms=[ALG])\n'
    assert _shapes(body) == ["constant"]


def test_a_binding_target_this_check_does_not_read_is_refused():
    """A loop, `with`, comprehension or unpacking target is computed, not chosen.

    Each of these also SHADOWS a module constant of the same name, so the
    search has to stop at it rather than resolving the constant behind it.
    """
    for src in (
        'ALG = "HS256"\nfor ALG in algs:\n    jwt.decode(t, k, algorithms=[ALG])',
        'ALG = "HS256"\nwith open(p) as ALG:\n    jwt.decode(t, k, algorithms=[ALG])',
        'ALG = "HS256"\n[jwt.decode(t, k, algorithms=[ALG]) for ALG in algs]',
        'ALG = "HS256"\nALG, other = pick()\njwt.decode(t, k, algorithms=[ALG])',
    ):
        shape = _shapes(src)[0]
        assert shape not in cdp._ADMISSIBLE_SHAPES, (src, shape)


def test_assigning_an_attribute_does_not_shadow_the_name():
    """`obj.ALG = x` rebinds no name, so it must not refuse the real constant."""
    assert _shapes('ALG = "HS256"\nobj.ALG = x\njwt.decode(t, k, algorithms=[ALG])') == ["constant"]


def test_a_global_declaration_resolves_outward():
    """`global ALG` means the module binding is the one in force."""
    src = (
        'ALG = "HS256"\ndef f(t, k):\n    global ALG\n    return jwt.decode(t, k, algorithms=[ALG])'
    )
    assert _shapes(src) == ["constant"]


def test_the_estates_own_twelve_sites_keep_their_verdicts():
    """The tightening must not change what this repository already resolves.

    Measured across the tree both before and after the scope fix: 5 constant,
    4 parameter, 2 literal, 1 imported. Each of the four `parameter` sites has
    its OWN string default, so none of them was relying on the leak -- which
    is worth pinning, because "the fix changed nothing here" is a claim about
    this estate that only a count can support.
    """
    from collections import Counter

    # `cdp._walk` is the checker's OWN walker, with its own ten-entry skip
    # list. This test used `rglob` with three exclusions, so it counted a file
    # set the checker never looks at -- a local `venv/`, `build/` or
    # `site-packages/` would make the expected count fail while the checker was
    # perfectly correct. A test that pins a checker's count has to measure the
    # checker's files. Raised by cubic on #1376.
    root = Path(__file__).resolve().parents[1]
    tally: Counter[str] = Counter()
    for path in sorted(cdp._walk(root, {".py"})):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for _line, shape, _count in cdp._jwt_decode_sites(tree, path):
            tally[shape] += 1
    assert tally == Counter({"constant": 5, "parameter": 4, "literal": 2, "imported": 1}), tally


# ---------------------------------------------------------------------------
# The alias pass reaches a FIXED POINT, not two hops.
#
# Raised by cubic on #1376: two passes stopped one hop short, so `v3 = v2` /
# `v2 = v1` / `v1 = jose.jwt` left `v3` unresolved and `v3.decode(...)` was
# invisible -- free to widen its allowlist with the gate green. Probing the
# fixed point then found the same hole in the loop's other half, where a
# re-aliased decoder (`d2 = d1`) was not chained either.
# ---------------------------------------------------------------------------


def test_a_chained_module_alias_resolves_however_deep():
    src = (
        "from jose import jwt\n"
        "v1 = jwt\n"
        "v2 = v1\n"
        "v3 = v2\n"
        'v3.decode(t, k, algorithms=["HS256", "RS256"])\n'
    )
    shape = _shapes(src)[0]
    assert shape not in cdp._ADMISSIBLE_SHAPES, shape
    assert "more than one" in shape, shape


def test_a_chained_direct_decoder_resolves_however_deep():
    """Found by probing the fixed point, not reported: `d2 = d1` was not chained."""
    src = (
        'from jose import jwt\nd3 = d2\nd2 = d1\nd1 = jwt.decode\nd3(t, k, algorithms=["HS256"])\n'
    )
    assert _shapes(src) == ["literal"]


def test_an_unrelated_alias_chain_is_not_claimed_as_a_decode_site():
    """The fixed point must not widen what counts as a JWT module."""
    assert _shapes("import os\na = os.path\nb = a\nb.join(x)\n") == []


def test_a_sibling_file_cannot_stand_in_for_a_package_module(tmp_path):
    """REGRESSION: `from pkg.config import ALG` resolved against any `config.py`.

    The basename shortcut was tried FIRST, so a sibling file for a different
    binding answered for the real module. Raised by cubic on #1376 and
    reproduced -- the sibling bound `"HS256"`, the real `pkg/config.py` bound
    `get_unverified_header(t)["alg"]`, and the site came back `imported`:
    the checker measured the wrong file and reported the answer as if it were
    the right one.
    """
    (tmp_path / "pkg").mkdir()
    (tmp_path / "config.py").write_text('ALG = "HS256"\n', encoding="utf-8")
    (tmp_path / "pkg" / "config.py").write_text(
        'import jwt\nALG = jwt.get_unverified_header(t)["alg"]\n', encoding="utf-8"
    )
    service = tmp_path / "service.py"
    service.write_text(
        "from pkg.config import ALG\nimport jwt\njwt.decode(t, k, algorithms=[ALG])\n",
        encoding="utf-8",
    )
    shape = cdp._jwt_decode_sites(ast.parse(service.read_text(encoding="utf-8")), service)[0][1]
    assert shape not in cdp._ADMISSIBLE_SHAPES, shape
    assert "does not bind it to a string literal" in shape, shape


def test_an_undotted_import_still_resolves_against_its_sibling(tmp_path):
    """The shortcut the estate actually needs is kept, bounded to undotted names.

    `workers/infinity-auth/service.py` does `from config import JWT_ALGORITHM`
    against a sibling `config.py`. Refusing that would be a false alarm, so the
    basename candidate survives for a module name with no dots -- the case
    where the basename IS the module.
    """
    (tmp_path / "config.py").write_text('JWT_ALGORITHM = "HS256"\n', encoding="utf-8")
    service = tmp_path / "service.py"
    service.write_text(
        "from config import JWT_ALGORITHM\nimport jwt\n"
        "jwt.decode(t, k, algorithms=[JWT_ALGORITHM])\n",
        encoding="utf-8",
    )
    assert cdp._jwt_decode_sites(ast.parse(service.read_text(encoding="utf-8")), service) == [
        (3, "imported", 1)
    ]
