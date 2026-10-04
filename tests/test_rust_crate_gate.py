"""The Rust crate compile gate, checked against mutations of its own inputs.

`scripts/check_rust_crates.py` exists because `rust.yml` compiled one of nine
crates and reported green. A gate built for that reason is held to the standard
it was built to enforce: every branch below is driven by a deliberately broken
input, so a gate that stopped being able to fail would fail these tests
instead of passing CI silently.

The [CHANGED] cases earn their own tests because the comparison they rest on
was loosened on purpose -- from rustc's full prose to the location and error
code -- and loosening a comparison is the exact move that turns a check into
one that cannot fail.
"""

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_rust_crates", REPO / "scripts" / "check_rust_crates.py"
)
gate = importlib.util.module_from_spec(_spec)
# @dataclass resolves annotations through sys.modules, so the module has to be
# registered before it is executed.
sys.modules["check_rust_crates"] = gate
_spec.loader.exec_module(gate)

PLAIN = "src/main.rs:290:44: error[E0308]: mismatched types: expected `Utf8Bytes`, found `String`"
COLOURED = (
    "src/main.rs:290:44: \x1b[1m\x1b[91merror[E0308]\x1b[0m: mismatched types: "
    "expected `Utf8Bytes`, found `String`"
)


def _compare(measured, ledger):
    return gate._compare(measured, ledger)


def _broken(reason):
    return gate.Measurement(status=gate.BROKEN, reason=reason)


# --- normalisation -------------------------------------------------------


def test_colour_escapes_are_stripped_before_comparison():
    """`CARGO_TERM_COLOR: always` must not make every CI run report a change."""
    assert gate._normalise(COLOURED) == PLAIN


def test_a_coloured_diagnostic_matches_the_plain_ledger_entry():
    failures = _compare(
        {"workers/nexus-ws-rs": _broken(gate._normalise(COLOURED))},
        {"workers/nexus-ws-rs": {"status": gate.BROKEN, "reason": PLAIN}},
    )
    assert failures == []


def test_rustc_rewording_its_own_prose_is_not_a_change():
    """The same defect, reworded by a newer compiler, is still the same defect."""
    recorded = (
        "src/main.rs:431:27: error[E0433]: failed to resolve: could not find `util` in `hyper`"
    )
    measured = "src/main.rs:431:27: error[E0433]: cannot find `util` in `hyper`"
    failures = _compare(
        {"src/nanoservices/nsa_broker": _broken(measured)},
        {"src/nanoservices/nsa_broker": {"status": gate.BROKEN, "reason": recorded}},
    )
    assert failures == []


# --- the mutations the loosening must still catch ------------------------


@pytest.mark.parametrize(
    "measured",
    [
        pytest.param(
            "src/main.rs:290:44: error[E0599]: no method named `send` found",
            id="different error code",
        ),
        pytest.param(
            "src/main.rs:290:44: error[E0308]: mismatched types: expected `usize`, found `String`",
            id="different expected type",
        ),
    ],
)
def test_a_materially_different_failure_is_still_reported(measured):
    failures = _compare(
        {
            "workers/nexus-ws-rs": gate.Measurement(
                status=gate.BROKEN, reason=measured, diagnostics=[measured]
            )
        },
        {
            "workers/nexus-ws-rs": {
                "status": gate.BROKEN,
                "reason": PLAIN,
                "errors": gate._fingerprint([PLAIN]),
            }
        },
    )
    assert len(failures) == 1
    assert "[CHANGED]" in failures[0]
    # Both sides are printed, because a human has to decide which is right.
    assert PLAIN in failures[0]
    assert measured in failures[0]


# --- the rest of the status vocabulary ----------------------------------


def test_a_crate_recorded_as_compiling_that_stops_compiling_regresses():
    failures = _compare(
        {"aeonmind/rust": _broken(PLAIN)},
        {"aeonmind/rust": {"status": gate.OK}},
    )
    assert len(failures) == 1
    assert "[REGRESSED]" in failures[0]


def test_a_repaired_crate_fails_until_the_ledger_is_updated():
    """A fix is good news the ledger still has to be told about."""
    failures = _compare(
        {"workers/nexus-ws-rs": gate.Measurement(status=gate.OK)},
        {"workers/nexus-ws-rs": {"status": gate.BROKEN, "reason": PLAIN}},
    )
    assert len(failures) == 1
    assert "[FIXED, UNRECORDED]" in failures[0]


def test_a_crate_the_ledger_has_never_heard_of_fails():
    failures = _compare(
        {"workers/brand-new-rs": gate.Measurement(status=gate.OK)},
        {},
    )
    assert len(failures) == 1
    assert "[UNRECORDED]" in failures[0]


def test_a_crate_that_could_not_be_checked_is_never_reported_clean():
    """The IMMUNE-SYSTEM rule: a sensor that could not see says so."""
    failures = _compare(
        {
            "aeonmind/wasm": gate.Measurement(
                status=gate.BLOCKED,
                reason="recorded target(s) ['wasm32-unknown-unknown'] are not installed",
            )
        },
        {"aeonmind/wasm": {"status": gate.OK, "targets": ["wasm32-unknown-unknown"]}},
    )
    assert len(failures) == 1
    assert "[BLOCKED]" in failures[0]


def test_a_crate_recorded_broken_with_no_reason_is_a_ledger_defect():
    """Without a reason, no later failure could be distinguished from this one."""
    failures = _compare(
        {"workers/nexus-ws-rs": _broken(PLAIN)},
        {"workers/nexus-ws-rs": {"status": gate.BROKEN}},
    )
    assert any("[LEDGER]" in failure for failure in failures)


def test_an_unrecognised_ledger_status_is_a_ledger_defect():
    """A typo'd status must not quietly switch regression checking off."""
    failures = _compare(
        {"workers/nexus-ws-rs": _broken(PLAIN)},
        {"workers/nexus-ws-rs": {"status": "probably-fine"}},
    )
    assert len(failures) == 1
    assert "[LEDGER]" in failures[0]


# --- the ledger as committed --------------------------------------------


def test_the_committed_ledger_passes_its_own_validity_rules():
    ledger = gate._load_ledger()
    assert gate._ledger_problems(ledger) == []


def test_the_committed_ledger_covers_every_crate_in_the_tree():
    """The defect this gate was built for was a crate nothing checked.

    Skipped rather than passed without cargo. `_crate_roots()` falls back to
    `manifest.parent` when `cargo metadata` cannot run, and because all nine
    crates here are single-manifest directories that fallback produces exactly
    the ledger keys -- so this test reported green without ever exercising the
    workspace-membership discovery it is about. A test that cannot fail is the
    failure mode this whole gate was built to catch.
    """
    if shutil.which("cargo") is None:
        pytest.skip("cargo is absent, so crate discovery would take its fallback path")
    assert set(gate._crate_roots()) == set(gate._load_ledger())


# --- the full diagnostic set, not just the first error --------------------


def test_a_crate_that_gains_an_error_is_reported():
    """Fingerprinting only the first error let a crate get worse and pass."""
    recorded = {
        "status": gate.BROKEN,
        "reason": PLAIN,
        "errors": ["E0308(expected=Utf8Bytes, found=String)"],
    }
    measured = gate.Measurement(
        status=gate.BROKEN,
        reason=PLAIN,
        diagnostics=[
            PLAIN,
            "src/main.rs:401:9: error[E0599]: no method named `send` found",
        ],
    )
    failures = _compare({"workers/nexus-ws-rs": measured}, {"workers/nexus-ws-rs": recorded})
    assert len(failures) == 1
    assert "[CHANGED]" in failures[0]


def test_the_same_error_set_in_a_different_order_is_not_a_change():
    """Cargo's emission order is not a property of the breakage."""
    first = "src/a.rs:1:1: error[E0432]: unresolved import"
    second = "src/b.rs:2:2: error[E0599]: no method named `x`"
    recorded = {
        "status": gate.BROKEN,
        "reason": first,
        "errors": gate._fingerprint([first, second]),
    }
    measured = gate.Measurement(status=gate.BROKEN, reason=second, diagnostics=[second, first])
    assert _compare({"workers/nexus-ws-rs": measured}, {"workers/nexus-ws-rs": recorded}) == []


def test_a_repeated_error_code_is_not_a_change_and_this_is_a_known_gap():
    """rustc's cascade count is the compiler's behaviour, not the code's.

    This test replaces one I wrote asserting the opposite. CI disproved it:
    `nsa_broker` reported [CHANGED] between rustc 1.94.1 and the runner's
    newer stable with the same primary E0433 at the same line, because the
    number of consequent errors a root cause produces differs by release.

    The gap is real and recorded here rather than left implicit: a crate can
    gain another instance of a code it already has and pass.
    """
    one = "src/a.rs:1:1: error[E0599]: no method named `x`"
    recorded = {"status": gate.BROKEN, "reason": one, "errors": gate._fingerprint([one])}
    measured = gate.Measurement(
        status=gate.BROKEN, reason=one, diagnostics=[one, one.replace("1:1", "9:9")]
    )
    assert _compare({"workers/nexus-ws-rs": measured}, {"workers/nexus-ws-rs": recorded}) == []


def test_a_new_kind_of_error_alongside_a_repeated_one_is_a_change():
    """The signal that survives: a code the crate did not emit before."""
    one = "src/a.rs:1:1: error[E0599]: no method named `x`"
    recorded = {"status": gate.BROKEN, "reason": one, "errors": gate._fingerprint([one])}
    measured = gate.Measurement(
        status=gate.BROKEN,
        reason=one,
        diagnostics=[one, one, "src/b.rs:2:2: error[E0432]: unresolved import"],
    )
    failures = _compare({"workers/nexus-ws-rs": measured}, {"workers/nexus-ws-rs": recorded})
    assert len(failures) == 1
    assert "[CHANGED]" in failures[0]


def test_a_source_edit_that_moves_a_line_is_not_a_change():
    """Keyed on file:line:col, a new comment above the failure tripped CHANGED."""
    recorded = {
        "status": gate.BROKEN,
        "reason": PLAIN,
        "errors": gate._fingerprint([PLAIN]),
    }
    moved = PLAIN.replace("290:44", "312:44")
    measured = gate.Measurement(status=gate.BROKEN, reason=moved, diagnostics=[moved])
    assert _compare({"workers/nexus-ws-rs": measured}, {"workers/nexus-ws-rs": recorded}) == []


def test_a_changed_type_mismatch_at_the_same_place_is_a_change():
    """E0308 carries its operands, or a new mismatch reads as the old one."""
    recorded_line = (
        "src/main.rs:290:44: error[E0308]: mismatched types: expected `String`, found `i32`"
    )
    measured_line = (
        "src/main.rs:290:44: error[E0308]: mismatched types: expected `usize`, found `i32`"
    )
    recorded = {
        "status": gate.BROKEN,
        "reason": recorded_line,
        "errors": gate._fingerprint([recorded_line]),
    }
    measured = gate.Measurement(
        status=gate.BROKEN, reason=measured_line, diagnostics=[measured_line]
    )
    failures = _compare({"workers/nexus-ws-rs": measured}, {"workers/nexus-ws-rs": recorded})
    assert len(failures) == 1
    assert "[CHANGED]" in failures[0]


def test_a_non_string_reason_does_not_crash_the_comparison():
    """`reason: 123` raised TypeError instead of reporting the LEDGER finding."""
    failures = _compare(
        {"workers/nexus-ws-rs": _broken(PLAIN)},
        {"workers/nexus-ws-rs": {"status": gate.BROKEN, "reason": 123}},
    )
    assert failures  # reported, not raised
    assert all(isinstance(f, str) for f in failures)


def test_every_broken_crate_in_the_committed_ledger_records_its_error_set():
    """A single recorded line cannot distinguish one failure from eighteen."""
    ledger = gate._load_ledger()
    for directory, entry in ledger.items():
        if entry.get("status") == gate.BROKEN:
            assert entry.get("errors"), f"{directory} records no error set"
