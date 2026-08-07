# tests/test_estate_lint.py
# Formalizes the manual duplication sweep (docs/governance/DUPLICATE-WORKER-FINDINGS.md)
# into scripts/estate_lint.py so it runs on every CI pass instead of only when
# someone happens to look by hand. These tests use temp dirs/files rather than the
# real repo state so they stay hermetic and don't churn as the estate changes.

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "estate_lint", Path(__file__).parent.parent / "scripts" / "estate_lint.py"
)
estate_lint = importlib.util.module_from_spec(_SPEC)
sys.modules["estate_lint"] = estate_lint
_SPEC.loader.exec_module(estate_lint)


class TestNormalizeAltLanguageName:
    def test_strips_known_suffix(self):
        assert estate_lint._normalize_alt_language_name("vault-service-rs") == "vault-service"
        assert estate_lint._normalize_alt_language_name("monitoring-go") == "monitoring"

    def test_leaves_unsuffixed_name_alone(self):
        assert estate_lint._normalize_alt_language_name("queue-service") == "queue-service"

    def test_does_not_strip_below_empty(self):
        """A bare '-rs' with nothing in front must not normalize to ''."""
        assert estate_lint._normalize_alt_language_name("-rs") == "-rs"


class TestWorkerDirsReferencedByCompose:
    def test_finds_context_style_reference(self, tmp_path):
        compose = tmp_path / "docker-compose.yml"
        compose.write_text(
            "services:\n"
            "  foo:\n"
            "    build:\n"
            "      context: ./workers/foo-service\n"
            "      dockerfile: Dockerfile\n"
        )
        refs = estate_lint._worker_dirs_referenced_by_compose(compose)
        assert refs == {"foo-service"}

    def test_finds_dockerfile_style_reference(self, tmp_path):
        compose = tmp_path / "docker-compose.yml"
        compose.write_text(
            "services:\n"
            "  bar:\n"
            "    build:\n"
            "      context: .\n"
            "      dockerfile: workers/bar-service/Dockerfile\n"
        )
        refs = estate_lint._worker_dirs_referenced_by_compose(compose)
        assert refs == {"bar-service"}

    def test_non_worker_build_context_yields_no_refs(self, tmp_path):
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("services:\n  root-app:\n    build:\n      context: .\n")
        assert estate_lint._worker_dirs_referenced_by_compose(compose) == set()

    def test_malformed_yaml_returns_empty_not_raises(self, tmp_path):
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("services:\n  foo: [unterminated\n")
        assert estate_lint._worker_dirs_referenced_by_compose(compose) == set()


class TestCheckOrphanedWorkerDirs:
    def test_orphaned_dir_is_flagged(self, tmp_path, monkeypatch):
        workers = tmp_path / "workers"
        (workers / "wired-service").mkdir(parents=True)
        (workers / "orphan-service").mkdir()
        (tmp_path / "docker-compose.production.yml").write_text(
            "services:\n  wired:\n    build:\n      context: ./workers/wired-service\n"
        )
        monkeypatch.setattr(estate_lint, "ROOT", tmp_path)
        monkeypatch.setattr(estate_lint, "WORKERS_DIR", workers)

        warnings, tracked = estate_lint.check_orphaned_worker_dirs(baseline=set())
        assert any("orphan-service" in w for w in warnings)
        assert not any("wired-service" in w for w in warnings)
        assert tracked == []

    def test_baselined_orphan_reports_as_tracked_not_warning(self, tmp_path, monkeypatch):
        workers = tmp_path / "workers"
        (workers / "known-orphan").mkdir(parents=True)
        (tmp_path / "docker-compose.production.yml").write_text("services: {}\n")
        monkeypatch.setattr(estate_lint, "ROOT", tmp_path)
        monkeypatch.setattr(estate_lint, "WORKERS_DIR", workers)

        warnings, tracked = estate_lint.check_orphaned_worker_dirs(baseline={"known-orphan"})
        assert warnings == []
        assert any("known-orphan" in t for t in tracked)

    def test_missing_workers_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(estate_lint, "ROOT", tmp_path)
        monkeypatch.setattr(estate_lint, "WORKERS_DIR", tmp_path / "nonexistent")
        assert estate_lint.check_orphaned_worker_dirs(baseline=set()) == ([], [])

    def test_scans_every_compose_file_not_just_production(self, tmp_path, monkeypatch):
        """A worker legitimately wired only in a non-production compose file
        (e.g. optional-services) must not be misreported as orphaned."""
        workers = tmp_path / "workers"
        (workers / "optional-only").mkdir(parents=True)
        (tmp_path / "docker-compose.production.yml").write_text("services: {}\n")
        (tmp_path / "docker-compose.optional-services.yml").write_text(
            "services:\n  optional:\n    build:\n      context: ./workers/optional-only\n"
        )
        monkeypatch.setattr(estate_lint, "ROOT", tmp_path)
        monkeypatch.setattr(estate_lint, "WORKERS_DIR", workers)

        warnings, _tracked = estate_lint.check_orphaned_worker_dirs(baseline=set())
        assert warnings == []


class TestCheckAltLanguageDuplicates:
    def test_suffixed_variant_alongside_original_is_flagged(self):
        compose = {"services": {"queue-service": {}, "queue-service-go": {}}}
        warnings, tracked = estate_lint.check_alt_language_duplicates(compose, baseline=set())
        assert any("queue-service-go" in w for w in warnings)
        assert tracked == []

    def test_suffixed_variant_without_original_is_still_flagged(self):
        """The Python 'original' doesn't have to share the exact base name for
        this to be worth a human's attention — see nexus-ws-rs, whose actual
        Python counterpart is infinity-ws, not nexus-ws. Under-flagging here
        risks missing exactly the pattern this check exists to catch."""
        compose = {"services": {"nexus-ws-rs": {}, "infinity-ws": {}}}
        warnings, _tracked = estate_lint.check_alt_language_duplicates(compose, baseline=set())
        assert any("nexus-ws-rs" in w for w in warnings)

    def test_no_suffix_collision_is_silent(self):
        compose = {"services": {"queue-service": {}, "cache-service": {}}}
        warnings, tracked = estate_lint.check_alt_language_duplicates(compose, baseline=set())
        assert warnings == []
        assert tracked == []

    def test_baselined_duplicate_reports_as_tracked_not_warning(self):
        compose = {"services": {"vault-service": {}, "vault-service-rs": {}}}
        warnings, tracked = estate_lint.check_alt_language_duplicates(
            compose, baseline={"vault-service-rs"}
        )
        assert warnings == []
        assert any("vault-service-rs" in t for t in tracked)


class TestLoadDuplicationBaseline:
    def test_missing_baseline_file_returns_empty_sets(self, tmp_path, monkeypatch):
        monkeypatch.setattr(estate_lint, "DUPLICATION_BASELINE_PATH", tmp_path / "nope.yaml")
        baseline = estate_lint.load_duplication_baseline()
        assert baseline == {"orphaned_worker_dirs": [], "alt_language_duplicates": []}

    def test_real_baseline_file_parses(self, tmp_path, monkeypatch):
        path = tmp_path / "duplication_baseline.yaml"
        path.write_text("orphaned_worker_dirs:\n  - foo\nalt_language_duplicates:\n  - bar-rs\n")
        monkeypatch.setattr(estate_lint, "DUPLICATION_BASELINE_PATH", path)
        baseline = estate_lint.load_duplication_baseline()
        assert baseline["orphaned_worker_dirs"] == {"foo"}
        assert baseline["alt_language_duplicates"] == {"bar-rs"}


class TestMainRunsAgainstRealRepo:
    def test_no_unbaselined_errors_on_real_estate(self):
        """Smoke test: running against the actual repo estate must not crash,
        and today's known-tracked findings must all resolve via the real
        config/estate/duplication_baseline.yaml — not a fixture. If this
        starts failing, either a genuinely new duplication/orphan finding
        appeared (investigate it), or the baseline needs updating because a
        tracked finding was resolved (remove it from the baseline)."""
        exit_code = estate_lint.main(strict=False)
        assert exit_code == 0  # no errors — only warnings, which don't fail non-strict mode
