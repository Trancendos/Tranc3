# tests/test_ml_configs.py
# Regression tests for ModelConfig/InferenceConfig/TrainingConfig
# (src/core/config.py) and UserSetting (src/database/schema.py).
#
# All four were previously missing entirely, breaking src.core.model,
# src.inference.engine, src.training.trainer, and src.settings_store with
# ImportError on every import — found via a full pkgutil.walk_packages
# sweep across src/. None of these are wired into the live FastAPI app
# (confirmed via grep: only scripts/train.py, scripts/chat.py, and
# src/training/evaluator.py reference them), but they're real, otherwise-
# functional standalone ML tooling that has been dead on arrival since
# they were added.

from __future__ import annotations

import pytest
import torch

from src.core.config import InferenceConfig, ModelConfig, TrainingConfig
from src.core.model import Tranc3Model
from src.database.schema import Base


class TestModelConfig:
    def test_defaults_are_internally_consistent(self):
        cfg = ModelConfig()
        assert cfg.d_head == cfg.d_model // cfg.n_heads

    def test_d_head_derived_from_d_model_and_n_heads(self):
        cfg = ModelConfig(d_model=256, n_heads=4)
        assert cfg.d_head == 64

    def test_indivisible_d_model_and_n_heads_rejected(self):
        with pytest.raises(ValueError):
            ModelConfig(d_model=257, n_heads=4)

    def test_zero_n_heads_rejected_not_zero_division_error(self):
        with pytest.raises(ValueError):
            ModelConfig(n_heads=0)

    def test_non_positive_d_model_rejected(self):
        with pytest.raises(ValueError):
            ModelConfig(d_model=0, n_heads=1)
        with pytest.raises(ValueError):
            ModelConfig(d_model=-8, n_heads=4)

    def test_odd_d_head_rejected_before_model_construction(self):
        # d_model=15, n_heads=3 -> d_head=5 (odd), which used to build a
        # ModelConfig successfully and only fail on the first forward pass
        # with a confusing RoPE tensor-shape RuntimeError.
        with pytest.raises(ValueError):
            ModelConfig(d_model=15, n_heads=3)

    def test_builds_and_runs_a_real_model(self):
        cfg = ModelConfig(
            vocab_size=500, d_model=64, n_layers=2, n_heads=4, d_ff=256, max_seq_len=32
        )
        model = Tranc3Model(cfg)
        x = torch.randint(0, 500, (2, 16))
        logits, loss = model(x, targets=x)
        assert logits.shape == (2, 16, 500)
        assert loss is not None
        # Ensure ModelConfig remains compatible with parameter_count() wiring
        assert model.parameter_count() is not None
        assert sum(p.numel() for p in model.parameters()) > 0

    def test_generate_produces_new_tokens(self):
        cfg = ModelConfig(
            vocab_size=500, d_model=64, n_layers=2, n_heads=4, d_ff=256, max_seq_len=32
        )
        model = Tranc3Model(cfg)
        x = torch.randint(0, 500, (1, 4))
        out = model.generate(x, max_new_tokens=5)
        assert out.shape == (1, 9)


class TestInferenceConfig:
    def test_default_device_is_auto(self):
        assert InferenceConfig().device == "auto"


class TestTrainingConfig:
    def test_defaults_construct_without_error(self):
        cfg = TrainingConfig()
        assert cfg.max_steps > 0
        assert cfg.batch_size > 0

    def test_accepts_overrides(self):
        cfg = TrainingConfig(max_steps=100, batch_size=8, run_name="test-run")
        assert cfg.max_steps == 100
        assert cfg.batch_size == 8
        assert cfg.run_name == "test-run"


class TestUserSettingModel:
    def test_table_registered_on_base_metadata(self):
        assert "user_settings" in Base.metadata.tables

    def test_settings_store_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-secret-key-at-least-32-characters-long")
        from src.settings_store import UserSettingsStore

        db_path = tmp_path / "settings.db"
        store = UserSettingsStore(f"sqlite:///{db_path}")
        store.set("alice", "GROQ_API_KEY", "gsk_test123")
        assert store.get("alice", "GROQ_API_KEY") == "gsk_test123"
        assert store.list_keys("alice")["GROQ_API_KEY"] == "set"
        assert store.delete("alice", "GROQ_API_KEY") is True
        assert store.get("alice", "GROQ_API_KEY") is None

    def test_orm_model_matches_migration_003_column_shape(self):
        """UserSetting must match migrations/versions/003_user_settings.py exactly:
        Base.metadata.create_all() does not alter an already-migrated table, so if
        the ORM model drifts from the deployed schema (e.g. a UUID PK vs. the
        migration's INTEGER autoincrement PK), inserts against a real migrated
        database would fail even though tests against a fresh create_all() db
        would pass."""
        table = Base.metadata.tables["user_settings"]
        assert table.c.id.autoincrement in (True, "auto")
        assert not isinstance(table.c.id.type, type(table.c.encrypted_value.type))
        assert table.c.username.type.length == 64
        assert table.c.key.type.length == 128

    def test_settings_store_works_against_migrated_schema(self, tmp_path, monkeypatch):
        """Build the table via the real Alembic migration (not create_all) and
        confirm UserSettingsStore still works against exactly that shape."""
        import importlib.util

        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import create_engine

        monkeypatch.setenv("SECRET_KEY", "test-secret-key-at-least-32-characters-long")

        db_path = tmp_path / "migrated_settings.db"
        engine = create_engine(f"sqlite:///{db_path}")
        migrations_dir = __import__("pathlib").Path(__file__).resolve().parent.parent / "migrations"
        spec = importlib.util.spec_from_file_location(
            "m003_user_settings", migrations_dir / "versions" / "003_user_settings.py"
        )
        m003 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m003)

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            m003.op = Operations(ctx)
            m003.upgrade()

        from src.settings_store import UserSettingsStore

        store = UserSettingsStore(f"sqlite:///{db_path}")
        store.set("bob", "GITHUB_TOKEN", "ghp_test456")
        assert store.get("bob", "GITHUB_TOKEN") == "ghp_test456"
