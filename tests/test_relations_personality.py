# tests/test_relations_personality.py
# Tests for src/relations/personality.py — best-effort personality-quirk
# loader used by the Relationship Matrix.

from __future__ import annotations

import json

import pytest

from src.relations import personality as personality_module
from src.relations.personality import PersonalityQuirks, get_quirks


@pytest.fixture(autouse=True)
def _reset_module_caches(monkeypatch):
    """Each test gets its own fresh index/cache so profile-dir fixtures
    from one test don't leak into another via the module-level globals."""
    monkeypatch.setattr(personality_module, "_index", None)
    monkeypatch.setattr(personality_module, "_cache", {})
    yield


class TestNeutralFallback:
    def test_unknown_code_name_returns_neutral_defaults(self):
        quirks = get_quirks("Some Unknown AI")
        assert quirks.found is False
        assert quirks.traits["agreeableness"] == 0.5
        assert quirks.positivity_multiplier == pytest.approx(1.0)
        assert quirks.negativity_multiplier == pytest.approx(1.0)

    def test_missing_profiles_dir_falls_back_to_neutral(self, monkeypatch, tmp_path):
        monkeypatch.setattr(personality_module, "_PROFILES_DIR", tmp_path / "does-not-exist")
        quirks = get_quirks("Anyone")
        assert quirks.found is False


class TestMalformedProfiles:
    def test_non_dict_json_root_falls_back_to_neutral(self, monkeypatch, tmp_path):
        (tmp_path / "bad.json").write_text(json.dumps(["not", "a", "dict"]))
        monkeypatch.setattr(personality_module, "_PROFILES_DIR", tmp_path)
        quirks = get_quirks("Anyone")
        assert quirks.found is False

    def test_null_style_does_not_crash(self, monkeypatch, tmp_path):
        (tmp_path / "weird.json").write_text(
            json.dumps({"code_name": "Weird AI", "style": None, "traits": {"empathy": 0.9}})
        )
        monkeypatch.setattr(personality_module, "_PROFILES_DIR", tmp_path)
        quirks = get_quirks("Weird AI")
        assert quirks.found is True
        assert quirks.tone == "neutral"
        assert quirks.traits["empathy"] == 0.9

    def test_non_dict_traits_falls_back_to_neutral_traits(self, monkeypatch, tmp_path):
        (tmp_path / "weird2.json").write_text(
            json.dumps({"code_name": "Weird AI 2", "traits": "not-a-dict"})
        )
        monkeypatch.setattr(personality_module, "_PROFILES_DIR", tmp_path)
        quirks = get_quirks("Weird AI 2")
        assert quirks.found is True
        assert quirks.traits["agreeableness"] == 0.5

    def test_invalid_json_falls_back_to_neutral(self, monkeypatch, tmp_path):
        (tmp_path / "broken.json").write_text("{not valid json")
        monkeypatch.setattr(personality_module, "_PROFILES_DIR", tmp_path)
        quirks = get_quirks("Anyone")
        assert quirks.found is False

    def test_null_description_does_not_crash(self, monkeypatch, tmp_path):
        (tmp_path / "nulldesc.json").write_text(
            json.dumps({"code_name": "Null Desc AI", "description": None})
        )
        monkeypatch.setattr(personality_module, "_PROFILES_DIR", tmp_path)
        quirks = get_quirks("Null Desc AI")
        assert quirks.found is True
        assert quirks.description == ""

    def test_invalid_utf8_falls_back_to_neutral(self, monkeypatch, tmp_path):
        # read_text() raises UnicodeDecodeError (a ValueError subclass) — the
        # loader must catch it and fall back rather than propagate.
        (tmp_path / "badenc.json").write_bytes(b"\xff\xfe not utf-8 at all")
        monkeypatch.setattr(personality_module, "_PROFILES_DIR", tmp_path)
        quirks = get_quirks("Anyone")
        assert quirks.found is False

    def test_non_string_code_name_is_skipped_not_crashed(self, monkeypatch, tmp_path):
        # A non-string code_name (e.g. a list) must not crash _build_index when
        # it tries to use the value as a dict key (unhashable -> TypeError).
        (tmp_path / "listname.json").write_text(json.dumps({"code_name": ["not", "a", "string"]}))
        (tmp_path / "good.json").write_text(
            json.dumps({"code_name": "Good AI", "description": "ok"})
        )
        monkeypatch.setattr(personality_module, "_PROFILES_DIR", tmp_path)
        # The good profile still resolves; the bad one is ignored.
        assert get_quirks("Good AI").found is True

    def test_malformed_profile_logs_warning(self, monkeypatch, tmp_path, caplog):
        (tmp_path / "broken.json").write_text("{not valid json")
        monkeypatch.setattr(personality_module, "_PROFILES_DIR", tmp_path)
        with caplog.at_level("WARNING"):
            get_quirks("Anyone")
        assert any("could not be read/parsed" in rec.message for rec in caplog.records)

    def test_deeply_nested_json_recursionerror_falls_back_to_neutral(self, monkeypatch, tmp_path):
        # Deeply nested JSON makes json.loads raise RecursionError, which is NOT
        # a ValueError subclass; the loader must catch it and fall back rather
        # than letting it crash _build_index and null out the whole index.
        depth = 100_000
        (tmp_path / "deep.json").write_text("[" * depth + "]" * depth)
        (tmp_path / "good.json").write_text(
            json.dumps({"code_name": "Good AI", "description": "ok"})
        )
        monkeypatch.setattr(personality_module, "_PROFILES_DIR", tmp_path)
        # Must not raise, and the well-formed profile still resolves.
        assert get_quirks("Good AI").found is True


class TestDuplicateCodeName:
    def test_duplicate_code_name_logs_warning_and_still_resolves(
        self, monkeypatch, tmp_path, caplog
    ):
        (tmp_path / "a.json").write_text(
            json.dumps({"code_name": "Dup AI", "description": "first"})
        )
        (tmp_path / "b.json").write_text(
            json.dumps({"code_name": "Dup AI", "description": "second"})
        )
        monkeypatch.setattr(personality_module, "_PROFILES_DIR", tmp_path)
        with caplog.at_level("WARNING"):
            quirks = get_quirks("Dup AI")
        assert quirks.found is True
        assert any("collision" in rec.message for rec in caplog.records)


class TestMultipliers:
    def test_high_agreeableness_and_empathy_raise_positivity_multiplier(self):
        quirks = PersonalityQuirks(
            code_name="x", traits={"agreeableness": 1.0, "empathy": 1.0}, found=True
        )
        assert quirks.positivity_multiplier > 1.0

    def test_high_assertiveness_and_neuroticism_raise_negativity_multiplier(self):
        quirks = PersonalityQuirks(
            code_name="x", traits={"assertiveness": 1.0, "neuroticism": 1.0}, found=True
        )
        assert quirks.negativity_multiplier > 1.0
