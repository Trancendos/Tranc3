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
            "src/main.rs:412:9: error[E0308]: mismatched types: expected `Utf8Bytes`, found `String`",
            id="different line",
        ),
        pytest.param(
            "src/lib.rs:290:44: error[E0308]: mismatched types: expected `Utf8Bytes`, found `String`",
            id="different file",
        ),
    ],
)
def test_a_materially_different_failure_is_still_reported(measured):
    failures = _compare(
        {"workers/nexus-ws-rs": _broken(measured)},
        {"workers/nexus-ws-rs": {"status": gate.BROKEN, "reason": PLAIN}},
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
    """The defect this gate was built for was a crate nothing checked."""
    assert set(gate._crate_roots()) == set(gate._load_ledger())
