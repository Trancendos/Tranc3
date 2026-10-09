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


def test_a_module_constant_is_pinned_by_reference():
    """`algorithms=[ALGORITHM]` is chosen by this code, not by the token."""
    assert _shapes('ALG = "RS256"\njwt.decode(t, k, algorithms=[ALG])') == ["reference"]
    assert _shapes("jwt.decode(t, k, algorithms=[cfg.ALGORITHM])") == ["reference"]


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
    """
    for src in (
        'import jose\nif flag:\n    v = jose.jwt\nv.decode(t, k, algorithms=["A", "B"])',
        "import jose\ntry:\n    v = jose.jwt\nexcept ImportError:\n    v = None\n"
        'v.decode(t, k, algorithms=["A", "B"])',
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
