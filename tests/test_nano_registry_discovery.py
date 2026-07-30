# tests/test_nano_registry_discovery.py
# Tests for src/nanoservices/nano_registry.py's discover_library_nanoservices()
# — closes the gap where only the 13 HTTP-exposed nanoservices (out of 61
# module directories under src/nanoservices/) were registered at all.

from __future__ import annotations

import pytest

from src.nanoservices.nano_registry import (
    NanoService,
    NanoServiceRegistry,
    _parse_package_metadata,
    discover_library_nanoservices,
)


@pytest.fixture
def bare_registry():
    """A registry with the 13 built-in HTTP services but discovery
    disabled, so tests can control exactly what discover_library_
    nanoservices() adds."""
    return NanoServiceRegistry(discover_library_modules=False)


class TestDiscoverLibraryNanoservices:
    def test_registers_known_library_module(self, bare_registry):
        discover_library_nanoservices(bare_registry)
        svc = bare_registry.get("cosmic_curiosity")
        assert svc is not None
        assert svc.kind == "library"

    def test_does_not_reregister_http_services(self, bare_registry):
        discover_library_nanoservices(bare_registry)
        tokenizer = bare_registry.get("tokenizer")
        assert tokenizer.kind == "http"
        assert tokenizer.endpoint == "/nano/tokenize"

    def test_library_entry_has_no_http_endpoint(self, bare_registry):
        discover_library_nanoservices(bare_registry)
        svc = bare_registry.get("aerial_drone_adapter")
        assert svc.endpoint is None
        assert svc.health_url is None

    def test_library_entry_captures_docstring_and_exports(self, bare_registry):
        discover_library_nanoservices(bare_registry)
        svc = bare_registry.get("cosmic_curiosity")
        assert "Cosmic Curiosity" in svc.metadata["docstring"]
        assert "CosmicCuriosityService" in svc.capabilities

    def test_module_path_metadata_is_importable_dotted_path(self, bare_registry):
        discover_library_nanoservices(bare_registry)
        svc = bare_registry.get("cosmic_curiosity")
        assert svc.metadata["module_path"] == "src.nanoservices.cosmic_curiosity"

    def test_discovers_a_meaningful_number_of_modules(self, bare_registry):
        count = discover_library_nanoservices(bare_registry)
        assert count >= 40  # 61 module dirs total, 13 already HTTP-registered

    def test_running_twice_does_not_duplicate(self, bare_registry):
        first = discover_library_nanoservices(bare_registry)
        second = discover_library_nanoservices(bare_registry)
        assert second == 0
        assert first > 0

    def test_skips_rust_and_pycache_directories(self, bare_registry):
        discover_library_nanoservices(bare_registry)
        assert bare_registry.get("rust") is None
        assert bare_registry.get("__pycache__") is None

    def test_default_constructor_runs_discovery(self):
        registry = NanoServiceRegistry()
        lib_entries = [s for s in registry.list_all() if s["kind"] == "library"]
        assert len(lib_entries) >= 40

    def test_list_all_reports_kind(self, bare_registry):
        discover_library_nanoservices(bare_registry)
        entries = {e["name"]: e["kind"] for e in bare_registry.list_all()}
        assert entries["tokenizer"] == "http"
        assert entries["cosmic_curiosity"] == "library"


class TestParsePackageMetadata:
    def test_extracts_docstring_and_all(self, tmp_path):
        init_file = tmp_path / "__init__.py"
        init_file.write_text(
            '"""Example nanoservice."""\n\nfrom .impl import Thing, Other\n\n'
            '__all__ = ["Thing", "Other"]\n'
        )
        docstring, exported = _parse_package_metadata(init_file)
        assert docstring == "Example nanoservice."
        assert exported == ["Thing", "Other"]

    def test_handles_missing_all(self, tmp_path):
        init_file = tmp_path / "__init__.py"
        init_file.write_text('"""No exports here."""\n')
        docstring, exported = _parse_package_metadata(init_file)
        assert docstring == "No exports here."
        assert exported == []

    def test_never_raises_on_syntax_error(self, tmp_path):
        init_file = tmp_path / "__init__.py"
        init_file.write_text("this is not : valid python (((")
        docstring, exported = _parse_package_metadata(init_file)
        assert docstring == ""
        assert exported == []

    def test_never_raises_on_missing_file(self, tmp_path):
        docstring, exported = _parse_package_metadata(tmp_path / "does_not_exist.py")
        assert docstring == ""
        assert exported == []


def test_nanoservice_dataclass_defaults_to_http_kind():
    svc = NanoService(name="example")
    assert svc.kind == "http"
    assert svc.endpoint is None
    assert svc.capabilities == []
