"""Go and Rust scanning — the ecosystems the census could not see.

This module exists because a Security Agent report listed a HIGH gRPC-Go
advisory as open while the platform's own census reported green. The census was
not wrong about what it scanned; it was silent about three `go.mod` and nine
`Cargo.toml` files it never opened. A control that reports clean over surfaces
it never read is the defect this whole engagement keeps finding.

Two properties get the hardest tests, because both were real bugs here rather
than imagined ones:

  * `/v1/querybatch` returns `{id, modified}` and NO `affected` block. Reading
    fix versions off a batch result reports "no released fix" for every finding
    in existence. The first run of this module said exactly that about
    `GHSA-vp52-pcj8-j9qc`, which OSV records as fixed in 1.83.1.
  * An unreachable OSV, an unhydratable advisory and a `Cargo.toml` with no
    lockfile must all report the surface **errored**. Each of them silently
    produces an empty findings list, and an empty findings list is
    indistinguishable from a clean scan.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dvms import native_ecosystems as native  # noqa: E402


class _Response:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _opener(batch_results, vulns, calls=None):
    """A stand-in for urlopen serving both OSV endpoints."""

    def open_it(request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        if calls is not None:
            calls.append(url)
        if url.startswith(native.OSV_VULN_URL):
            identifier = url[len(native.OSV_VULN_URL) :]
            if identifier not in vulns:
                raise OSError("not found")
            return _Response(vulns[identifier])
        if batch_results is None:
            raise OSError("connection reset")
        return _Response({"results": batch_results})

    return open_it


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    monkeypatch.setattr(native.time, "sleep", lambda _s: None)


GRPC_RECORD = {
    "id": "GHSA-vp52-pcj8-j9qc",
    "aliases": ["CVE-2026-84304"],
    "summary": "gRPC-Go: Heap Memory Exhaustion (OOM) via HTTP/2 DATA Frame Fragmentation",
    "database_specific": {"severity": "HIGH"},
    "affected": [
        {
            "package": {"name": "google.golang.org/grpc", "ecosystem": "Go"},
            "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "1.83.1"}]}],
        }
    ],
}


class TestGoModParsing:
    def test_a_require_block_yields_every_module(self):
        text = (
            "module github.com/Trancendos/Tranc3/x\n\n"
            "go 1.21\n\n"
            "require (\n"
            "\tgithub.com/google/uuid v1.21.0\n"
            "\tgoogle.golang.org/grpc v1.82.2\n"
            ")\n"
        )
        assert native.parse_go_mod(text) == [
            ("github.com/google/uuid", "v1.21.0"),
            ("google.golang.org/grpc", "v1.82.2"),
        ]

    def test_an_indirect_dependency_is_still_a_dependency(self):
        """An indirect module is compiled into the binary and is exploitable there.

        Dropping `// indirect` entries is how a transitive advisory becomes
        somebody else's problem while still shipping in this estate's binary —
        and the gRPC-Go advisory this module exists for reaches most Go trees
        exactly that way.
        """
        text = "require (\n\tgolang.org/x/net v0.30.0 // indirect\n)\n"
        assert native.parse_go_mod(text) == [("golang.org/x/net", "v0.30.0")]

    def test_module_go_and_replace_lines_are_not_dependencies(self):
        """`module` and `go` name no package; recorded, they become queries.

        `module github.com/Trancendos/Tranc3/x` would be asked about as if it
        were a public module, and a name collision with a real one would
        attribute a stranger's advisory to this estate.

        Held three times over — the outside-a-block `require ` requirement, the
        name pattern's mandatory dot and slash, and the version's mandatory `v`
        prefix — so no single-mechanism mutation breaks this test. Measured. It
        pins the behaviour rather than any one guard, which is the right
        contract when three of them agree.
        """
        text = "module github.com/Trancendos/Tranc3/x\ngo 1.21\ntoolchain go1.21.5\n"
        assert native.parse_go_mod(text) == []

    def test_a_single_line_require_is_read(self):
        assert native.parse_go_mod("require github.com/pkg/errors v0.9.1\n") == [
            ("github.com/pkg/errors", "v0.9.1")
        ]

    def test_a_commented_out_require_is_not_a_dependency(self):
        assert native.parse_go_mod("// require github.com/x/y v1.0.0\n") == []


class TestCargoLockParsing:
    def test_registry_packages_are_collected(self):
        text = (
            "[[package]]\n"
            'name = "serde"\n'
            'version = "1.0.210"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
            "\n"
            "[[package]]\n"
            'name = "aead"\n'
            'version = "0.6.1"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
        )
        assert native.parse_cargo_lock(text) == [("serde", "1.0.210"), ("aead", "0.6.1")]

    def test_a_workspace_member_crate_is_not_queried(self):
        """A crate with no `source` is this repository's own and has no advisory.

        Queried anyway, a local crate whose name collides with a published one
        would pull that stranger's advisories into this estate's findings.
        """
        text = '[[package]]\nname = "tranc3-crypto"\nversion = "0.1.0"\n'
        assert native.parse_cargo_lock(text) == []

    def test_the_final_stanza_is_not_dropped(self):
        """A lockfile ends without a trailing separator, so the last package is
        only recorded if the parser flushes at EOF as well as at `[[package]]`."""
        text = '[[package]]\nname = "only"\nversion = "1.0.0"\nsource = "registry+https://x"\n'
        assert native.parse_cargo_lock(text) == [("only", "1.0.0")]


class TestFixVersions:
    def test_a_released_fix_is_reported(self):
        assert native._released_fix(GRPC_RECORD) == ["1.83.1"]

    def test_a_commit_only_fix_is_not_a_released_fix(self):
        """A GIT range names a commit, and a commit is not a version to pin.

        Reported as a fix it would classify a genuinely unfixable finding as
        `fixable` and fail the gate over work nobody can do.
        """
        record = {
            "affected": [{"ranges": [{"type": "GIT", "events": [{"fixed": "deadbeef" * 5}]}]}]
        }
        assert native._released_fix(record) == []

    def test_a_batch_stub_carries_no_fix_information(self):
        """The bug this module shipped with, pinned so it cannot come back.

        `/v1/querybatch` returns `{id, modified}` and nothing else. Reading
        `_released_fix` off that stub says "no released fix" about an advisory
        OSV records as fixed in 1.83.1 — which is not a harmless omission: it
        is the exact evidence somebody would use to disposition a remediable
        HIGH as an accepted risk.
        """
        assert native._released_fix({"id": "GHSA-vp52-pcj8-j9qc", "modified": "2026-09-03"}) == []


class TestQueryOsv:
    def test_a_hit_is_hydrated_before_it_is_reported(self):
        """The regression guard: the finding must carry the real fix version."""
        opener = _opener(
            [{"vulns": [{"id": "GHSA-vp52-pcj8-j9qc", "modified": "x"}]}],
            {"GHSA-vp52-pcj8-j9qc": GRPC_RECORD},
        )
        findings = native.query_osv([("google.golang.org/grpc", "v1.82.2")], "Go", opener=opener)
        assert findings is not None and len(findings) == 1
        assert findings[0]["fix_versions"] == ["1.83.1"]
        assert findings[0]["aliases"] == ["CVE-2026-84304"]
        assert findings[0]["severity"] == "high"

    def test_an_unreachable_osv_is_unscannable_not_clean(self):
        """`None` and `[]` are different answers and must stay different."""
        assert native.query_osv([("x", "1.0")], "Go", opener=_opener(None, {})) is None

    def test_an_unhydratable_advisory_makes_the_surface_unscannable(self):
        """Not knowing whether a patch shipped is not the same as none shipping.

        Reported with an empty `fix_versions` the finding reads as unfixable,
        and an unfixable finding is exactly what the register accepts.
        """
        opener = _opener([{"vulns": [{"id": "GHSA-aaaa-bbbb-cccc"}]}], {})
        assert native.query_osv([("x", "1.0")], "Go", opener=opener) is None

    def test_a_clean_scan_returns_an_empty_list_not_none(self):
        assert native.query_osv([("x", "1.0")], "Go", opener=_opener([{}], {})) == []

    def test_no_packages_makes_no_request(self):
        calls: list = []
        assert native.query_osv([], "Go", opener=_opener([], {}, calls)) == []
        assert calls == []

    def test_each_advisory_is_fetched_once_however_many_packages_hit_it(self):
        """One advisory across twenty crates is one hydration, not twenty.

        Without the de-duplication a widely shared dependency turns a scan into
        a rate-limit incident against somebody else's free API.
        """
        calls: list = []
        opener = _opener(
            [
                {"vulns": [{"id": "GHSA-vp52-pcj8-j9qc"}]},
                {"vulns": [{"id": "GHSA-vp52-pcj8-j9qc"}]},
            ],
            {"GHSA-vp52-pcj8-j9qc": GRPC_RECORD},
            calls,
        )
        findings = native.query_osv([("a", "1.0"), ("b", "2.0")], "Go", opener=opener)
        assert len(findings) == 2
        assert sum(1 for c in calls if c.startswith(native.OSV_VULN_URL)) == 1

    def test_a_traversal_shaped_id_is_never_queried(self):
        """The id is interpolated into a URL, so its shape is checked, not trusted."""

        def _boom(*_a, **_k):  # pragma: no cover - must never be reached
            raise AssertionError("a malformed id reached the network")

        assert native.hydrate("GHSA-../../etc/passwd", opener=_boom) is None


class TestSurfaceScanning:
    def test_a_cargo_toml_without_a_lockfile_is_errored_not_skipped(self, tmp_path):
        """Six of this estate's nine crates are in exactly this state.

        `Cargo.toml` declares version RANGES and an advisory applies to an
        exact version, so there is genuinely nothing to query — but reporting
        that as zero findings would put six unscanned crates behind a green
        gate, which is the failure this module was written to end.
        """
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        surface = native.scan_rust_crate(str(tmp_path), "Cargo.toml")
        assert surface.errored
        assert "no Cargo.lock" in surface.reason
        assert surface.findings == []

    def test_a_locked_crate_is_scanned(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "Cargo.lock").write_text(
            '[[package]]\nname = "serde"\nversion = "1.0.0"\nsource = "registry+https://x"\n',
            encoding="utf-8",
        )
        surface = native.scan_rust_crate(str(tmp_path), "Cargo.toml", opener=_opener([{}], {}))
        assert not surface.errored
        assert surface.queried == 1

    def test_an_unreachable_scan_errors_the_go_surface(self, tmp_path):
        (tmp_path / "go.mod").write_text(
            "require (\n\tgithub.com/x/y v1.0.0\n)\n", encoding="utf-8"
        )
        surface = native.scan_go_module(str(tmp_path), "go.mod", opener=_opener(None, {}))
        assert surface.errored
        assert "OSV unusable" in surface.reason

    def test_a_go_module_with_no_requirements_is_clean_not_errored(self, tmp_path):
        """Zero dependencies is a real answer. Erroring on it would make every
        stub module a permanent gate failure nobody can clear."""
        (tmp_path / "go.mod").write_text("module x\ngo 1.21\n", encoding="utf-8")
        surface = native.scan_go_module(str(tmp_path), "go.mod")
        assert not surface.errored
        assert surface.queried == 0

    def test_discovery_skips_build_output_and_vendored_trees(self, tmp_path):
        """`target/` holds a compiled dependency's own vendored manifests.

        Scanning them reports advisories against crates this repo cannot
        upgrade, in paths that vanish on `cargo clean`.
        """
        (tmp_path / "target" / "debug").mkdir(parents=True)
        (tmp_path / "target" / "debug" / "Cargo.toml").write_text("", encoding="utf-8")
        (tmp_path / "Cargo.toml").write_text("", encoding="utf-8")
        assert native.discover_rust_crates(str(tmp_path)) == ["Cargo.toml"]

    def test_an_excluded_prefix_is_not_discovered(self, tmp_path):
        """Submodules are separate repositories that audit themselves."""
        (tmp_path / "compliance" / "magna-carta").mkdir(parents=True)
        (tmp_path / "compliance" / "magna-carta" / "go.mod").write_text("", encoding="utf-8")
        assert native.discover_go_modules(str(tmp_path), ("compliance/magna-carta",)) == []


class TestTheLockfileGuardAfterReview:
    """A present lockfile that parses to nothing must never scan clean.

    Calibrated as a set: deleting the `if not packages:` guard fails every
    test in this class. The earlier marker-string version of the guard is
    gone — it was unreachable for any non-empty file, so no mutation of it
    could fail anything, which is why it is not what these tests protect.
    """

    def test_a_file_holding_only_the_stanza_header_is_unscannable(self, tmp_path):
        """A truncated lockfile cut mid-stanza has no package entries."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "Cargo.lock").write_text("[[package]]\n", encoding="utf-8")
        surface = native.scan_rust_crate(str(tmp_path), "Cargo.toml", opener=_opener([{}], {}))
        assert surface.errored
        assert "[[package]] stanza" in surface.reason

    def test_a_file_holding_only_a_version_line_is_unscannable(self, tmp_path):
        """`version = ` is a line in almost any TOML file, not a package entry."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "Cargo.lock").write_text("version = 4\n", encoding="utf-8")
        surface = native.scan_rust_crate(str(tmp_path), "Cargo.toml", opener=_opener([{}], {}))
        assert surface.errored

    def test_an_empty_lockfile_is_unscannable(self, tmp_path):
        """A crate with no registry dependencies still gets a [[package]] stanza.

        Cargo writes one for the workspace root, so an empty lockfile is a
        broken file rather than a dependency-free crate.
        """
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "Cargo.lock").write_text("", encoding="utf-8")
        surface = native.scan_rust_crate(str(tmp_path), "Cargo.toml", opener=_opener([{}], {}))
        assert surface.errored

    def test_a_valid_lockfile_with_no_registry_packages_scans_clean(self, tmp_path):
        """Calibrated: testing the package count alone fails this.

        A crate whose dependencies are all path-, git- or workspace-local has
        a perfectly valid lockfile and nothing on crates.io to query. Calling
        that unscannable would put a permanent error on a crate with no
        registry exposure — the opposite mistake from the one the guard
        exists to prevent, and just as wrong.
        """
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "Cargo.lock").write_text(
            "# This file is automatically @generated by Cargo.\n"
            "[[package]]\n"
            'name = "my-workspace-root"\n'
            'version = "0.1.0"\n'
            "\n"
            "[[package]]\n"
            'name = "my-local-crate"\n'
            'version = "0.1.0"\n',
            encoding="utf-8",
        )
        surface = native.scan_rust_crate(str(tmp_path), "Cargo.toml", opener=_opener([], {}))
        assert not surface.errored
        assert surface.queried == 0
        assert surface.findings == []

    def test_a_truncated_stanza_cannot_borrow_the_header_version(self, tmp_path):
        """Calibrated: the substring form of the guard passes this file.

        Cargo.lock opens with its own `version = 3` format line, outside any
        stanza. A guard that only asks whether the strings `[[package]]`,
        `name = ` and `version = ` each appear *somewhere* is satisfied by a
        file truncated after a package's name, because the header supplies
        the version it is missing — and a broken lockfile then scans clean.
        `name` and `version` have to be found inside one stanza.
        """
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "Cargo.lock").write_text(
            "# This file is automatically @generated by Cargo.\n"
            "version = 3\n"
            "\n"
            "[[package]]\n"
            'name = "serde"\n',
            encoding="utf-8",
        )
        surface = native.scan_rust_crate(str(tmp_path), "Cargo.toml", opener=_opener([{}], {}))
        assert surface.errored
        assert "[[package]] stanza" in surface.reason

    def test_a_stanza_closed_by_another_table_does_not_complete_a_later_one(self, tmp_path):
        """Keys after `[metadata]` belong to that table, not to a package."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "Cargo.lock").write_text(
            '[[package]]\nname = "serde"\n\n[metadata]\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        surface = native.scan_rust_crate(str(tmp_path), "Cargo.toml", opener=_opener([{}], {}))
        assert surface.errored

    def test_a_complete_stanza_is_scanned(self, tmp_path):
        """The baseline the three above must not be allowed to break."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "Cargo.lock").write_text(
            "# This file is automatically @generated by Cargo.\n"
            "[[package]]\n"
            'name = "serde"\n'
            'version = "1.0.0"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n',
            encoding="utf-8",
        )
        surface = native.scan_rust_crate(str(tmp_path), "Cargo.toml", opener=_opener([{}], {}))
        assert not surface.errored
        assert surface.queried == 1


class TestTheRetryBudget:
    def test_a_backoff_never_sleeps_past_the_deadline(self):
        """Calibrated: returning the raw exponential interval fails this.

        A request failing a second before the deadline used to sleep the full
        interval and only then re-check the clock, overshooting the caller's
        budget by up to BACKOFF_SECONDS * 2 ** N.
        """
        deadline = time.monotonic() + 1.0
        assert native._backoff(4, deadline) <= 1.0

    def test_a_backoff_past_the_deadline_is_zero_not_negative(self):
        """Calibrated: omitting the max(0.0, ...) fails this.

        time.sleep raises ValueError on a negative interval, which would turn
        an expired budget into a crash instead of a recorded error.
        """
        assert native._backoff(3, time.monotonic() - 60) == 0.0

    def test_without_a_deadline_the_backoff_is_the_full_interval(self):
        assert native._backoff(1, None) == native.BACKOFF_SECONDS
