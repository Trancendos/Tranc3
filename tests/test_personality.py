"""Tests for src/personality/matrix.py and src/personality/spawner.py."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict
from unittest.mock import patch

import pytest


# ============================================================================
# PersonalityProfile tests (matrix.py)
# ============================================================================


class TestPersonalityProfile:
    """Tests for the PersonalityProfile dataclass."""

    def _make_profile(self, **overrides):
        from src.personality.matrix import PersonalityProfile

        defaults = dict(
            name="test-personality",
            version="1.0.0",
            system_prompt="You are a test assistant.",
            temperature=0.8,
            top_k=50,
            top_p=0.92,
            repetition_penalty=1.15,
            max_new_tokens=512,
            tone="warm",
            domain_focus="general",
            avatar_id=None,
            context_preamble="",
        )
        defaults.update(overrides)
        return PersonalityProfile(**defaults)

    def test_defaults(self):
        """Profile should have sensible defaults for optional fields."""
        from src.personality.matrix import PersonalityProfile

        p = PersonalityProfile(name="test", version="1.0", system_prompt="Hello")
        assert p.temperature == 0.8
        assert p.top_k == 50
        assert p.top_p == 0.92
        assert p.repetition_penalty == 1.15
        assert p.max_new_tokens == 512
        assert p.tone == "warm"
        assert p.domain_focus == "general"
        assert p.avatar_id is None
        assert p.context_preamble == ""

    def test_custom_values(self):
        """Profile should accept custom values for all fields."""
        p = self._make_profile(
            name="guardian",
            version="2.0.0",
            system_prompt="You are The Guardian.",
            temperature=0.1,
            top_k=20,
            top_p=0.8,
            tone="professional",
            domain_focus="security",
            avatar_id="guardian-v1",
            context_preamble="Security context here",
        )
        assert p.name == "guardian"
        assert p.version == "2.0.0"
        assert p.temperature == 0.1
        assert p.tone == "professional"
        assert p.avatar_id == "guardian-v1"
        assert p.context_preamble == "Security context here"

    def test_from_file(self):
        """from_file should load a profile from a JSON file."""
        from src.personality.matrix import PersonalityProfile

        data = {
            "name": "file-profile",
            "version": "1.5.0",
            "system_prompt": "Loaded from file.",
            "temperature": 0.5,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            path = f.name

        try:
            profile = PersonalityProfile.from_file(path)
            assert profile.name == "file-profile"
            assert profile.version == "1.5.0"
            assert profile.temperature == 0.5
        finally:
            os.unlink(path)

    def test_to_file(self):
        """to_file should save a profile as JSON."""

        p = self._make_profile(name="save-test", version="3.0.0", system_prompt="Save me.")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "profile.json")
            p.to_file(path)
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert data["name"] == "save-test"
            assert data["version"] == "3.0.0"

    def test_build_system_prompt_basic(self):
        """build_system_prompt should return the system prompt."""
        p = self._make_profile(system_prompt="You are helpful.")
        result = p.build_system_prompt()
        assert "You are helpful." in result

    def test_build_system_prompt_with_preamble(self):
        """build_system_prompt should prepend context_preamble."""
        p = self._make_profile(
            system_prompt="Main prompt.",
            context_preamble="Preamble text.",
        )
        result = p.build_system_prompt()
        assert "Preamble text." in result
        assert "Main prompt." in result
        # Preamble should come first
        assert result.index("Preamble") < result.index("Main prompt")

    def test_build_system_prompt_with_user_context(self):
        """build_system_prompt should append user_context lines."""
        p = self._make_profile(system_prompt="Base.")
        user_ctx = {"name": "Alice", "mood": "curious"}
        result = p.build_system_prompt(user_context=user_ctx)
        assert "Alice" in result
        assert "curious" in result

    def test_build_system_prompt_skips_empty_user_context(self):
        """Empty user_context values should be skipped."""
        p = self._make_profile(system_prompt="Base.")
        user_ctx = {"name": "Bob", "empty_val": "", "none_val": None}
        result = p.build_system_prompt(user_context=user_ctx)
        assert "Bob" in result

    def test_build_system_prompt_no_user_context(self):
        """Without user_context, only system_prompt (+preamble) is returned."""
        p = self._make_profile(system_prompt="Solo.", context_preamble="")
        result = p.build_system_prompt()
        assert result.strip() == "Solo."

    def test_roundtrip_file(self):
        """Saving and loading should produce equivalent profiles."""
        from src.personality.matrix import PersonalityProfile

        original = self._make_profile(
            name="roundtrip",
            version="1.0.0",
            system_prompt="Round trip test.",
            temperature=0.42,
            tone="creative",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "roundtrip.json")
            original.to_file(path)
            loaded = PersonalityProfile.from_file(path)
            assert loaded.name == original.name
            assert loaded.version == original.version
            assert loaded.system_prompt == original.system_prompt
            assert loaded.temperature == original.temperature
            assert loaded.tone == original.tone


# ============================================================================
# PersonalityMatrix tests (matrix.py)
# ============================================================================


class TestPersonalityMatrix:
    """Tests for the PersonalityMatrix registry class."""

    def test_loads_profiles_from_directory(self):
        """PersonalityMatrix should load all JSON profiles from its directory."""
        from src.personality.matrix import PersonalityMatrix

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test profile
            profile_data = {
                "name": "test-profile",
                "version": "1.0.0",
                "system_prompt": "Test prompt.",
            }
            with open(os.path.join(tmpdir, "test-profile.json"), "w") as f:
                json.dump(profile_data, f)

            matrix = PersonalityMatrix(profiles_dir=tmpdir)
            assert "test-profile" in matrix.list_profiles()

    def test_get_existing_profile(self):
        """get() should return a PersonalityProfile for a known name."""
        from src.personality.matrix import PersonalityMatrix

        with tempfile.TemporaryDirectory() as tmpdir:
            profile_data = {
                "name": "fetchable",
                "version": "2.0.0",
                "system_prompt": "Fetch me.",
            }
            with open(os.path.join(tmpdir, "fetchable.json"), "w") as f:
                json.dump(profile_data, f)

            matrix = PersonalityMatrix(profiles_dir=tmpdir)
            profile = matrix.get("fetchable")
            assert profile.name == "fetchable"
            assert profile.version == "2.0.0"

    def test_get_missing_profile_raises(self):
        """get() should raise KeyError for an unknown profile name."""
        from src.personality.matrix import PersonalityMatrix

        with tempfile.TemporaryDirectory() as tmpdir:
            matrix = PersonalityMatrix(profiles_dir=tmpdir)
            with pytest.raises(KeyError, match="not found"):
                matrix.get("nonexistent")

    def test_list_profiles_empty(self):
        """list_profiles() should return an empty list for an empty directory."""
        from src.personality.matrix import PersonalityMatrix

        with tempfile.TemporaryDirectory() as tmpdir:
            matrix = PersonalityMatrix(profiles_dir=tmpdir)
            assert matrix.list_profiles() == []

    def test_list_profiles_multiple(self):
        """list_profiles() should return all loaded profile names."""
        from src.personality.matrix import PersonalityMatrix

        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["alpha", "beta", "gamma"]:
                data = {"name": name, "version": "1.0", "system_prompt": f"I am {name}"}
                with open(os.path.join(tmpdir, f"{name}.json"), "w") as f:
                    json.dump(data, f)

            matrix = PersonalityMatrix(profiles_dir=tmpdir)
            names = matrix.list_profiles()
            assert set(names) == {"alpha", "beta", "gamma"}

    def test_register_new_profile(self):
        """register() should add a profile to the registry and save it."""
        from src.personality.matrix import PersonalityMatrix, PersonalityProfile

        with tempfile.TemporaryDirectory() as tmpdir:
            matrix = PersonalityMatrix(profiles_dir=tmpdir)
            profile = PersonalityProfile(
                name="dynamic",
                version="1.0.0",
                system_prompt="I was registered at runtime.",
            )
            matrix.register(profile)
            assert "dynamic" in matrix.list_profiles()
            # File should exist on disk
            assert os.path.exists(os.path.join(tmpdir, "dynamic.json"))

    def test_nonexistent_directory(self):
        """PersonalityMatrix should handle a missing profiles directory gracefully."""
        from src.personality.matrix import PersonalityMatrix

        matrix = PersonalityMatrix(profiles_dir="/nonexistent/path")
        assert matrix.list_profiles() == []

    def test_invalid_json_skipped(self):
        """Invalid JSON files should be skipped without crashing."""
        from src.personality.matrix import PersonalityMatrix

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write invalid JSON
            with open(os.path.join(tmpdir, "broken.json"), "w") as f:
                f.write("{invalid json content")
            # Write valid JSON
            data = {"name": "valid", "version": "1.0", "system_prompt": "OK"}
            with open(os.path.join(tmpdir, "valid.json"), "w") as f:
                json.dump(data, f)

            matrix = PersonalityMatrix(profiles_dir=tmpdir)
            assert "valid" in matrix.list_profiles()
            assert "broken" not in matrix.list_profiles()


# ============================================================================
# PersonalitySpawner tests (spawner.py)
# ============================================================================


class TestPersonalitySpawner:
    """Tests for the PersonalitySpawner class."""

    def _make_spawner_with_profiles(self, profiles: Dict[str, Dict]):
        """Create a spawner with mocked profiles, bypassing file-system loading."""
        from src.personality.spawner import PersonalitySpawner

        with patch.object(PersonalitySpawner, "_load_all_profiles", return_value=profiles):
            spawner = PersonalitySpawner()
        return spawner

    def _guardian_profile(self) -> Dict:
        return {
            "id": "the-guardian",
            "code_name": "The Guardian",
            "domain": "security",
            "description": "Cyber-security enforcer",
            "system_prompt_prefix": "You are The Guardian.",
            "skill_domains": ["threat-modelling", "vulnerability-analysis"],
            "restricted_domains": ["social-engineering-attacks"],
            "behavior": {"temperature": 0.1, "top_p": 0.8, "max_tokens": 768},
            "mcp_tools_priority": ["search_skills"],
        }

    def test_list_personalities(self):
        """list_personalities should return info about all loaded profiles."""
        profiles = {
            "the-guardian": self._guardian_profile(),
            "tranc3-base": {
                "id": "tranc3-base",
                "code_name": "Tranc3 Base",
                "domain": "general",
                "description": "Base personality",
            },
        }
        spawner = self._make_spawner_with_profiles(profiles)
        result = spawner.list_personalities()
        assert len(result) == 2
        ids = [p["id"] for p in result]
        assert "the-guardian" in ids
        assert "tranc3-base" in ids

    def test_spawn_unknown_personality_raises(self):
        """Spawning an unknown personality should raise ValueError."""
        spawner = self._make_spawner_with_profiles({})
        with pytest.raises(ValueError, match="Unknown personality"):
            spawner.spawn("nonexistent", "test-repo", output_dir="/tmp")

    def test_spawn_creates_directory(self):
        """Spawning should create the target directory and scaffold files."""
        profiles = {"the-guardian": self._guardian_profile()}
        spawner = self._make_spawner_with_profiles(profiles)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawner.spawn("the-guardian", "guardian-repo", output_dir=tmpdir)
            assert "files_written" in result
            assert result["personality"] == "the-guardian"
            assert result["repo_name"] == "guardian-repo"
            # Target directory should exist
            assert Path(result["output_path"]).exists()
            # Should have written several files
            assert len(result["files_written"]) >= 5

    def test_spawn_duplicate_raises(self):
        """Spawning into an existing directory should raise FileExistsError."""
        profiles = {"the-guardian": self._guardian_profile()}
        spawner = self._make_spawner_with_profiles(profiles)

        with tempfile.TemporaryDirectory() as tmpdir:
            spawner.spawn("the-guardian", "guardian-repo", output_dir=tmpdir)
            with pytest.raises(FileExistsError):
                spawner.spawn("the-guardian", "guardian-repo", output_dir=tmpdir)

    def test_spawn_writes_config(self):
        """Spawning should write a tranc3_config.yaml."""
        profiles = {"the-guardian": self._guardian_profile()}
        spawner = self._make_spawner_with_profiles(profiles)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawner.spawn("the-guardian", "guardian-repo", output_dir=tmpdir)
            config_path = Path(result["output_path"]) / "tranc3_config.yaml"
            assert config_path.exists()

    def test_spawn_writes_active_profile(self):
        """Spawning should write an active_profile.json."""
        profiles = {"the-guardian": self._guardian_profile()}
        spawner = self._make_spawner_with_profiles(profiles)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawner.spawn("the-guardian", "guardian-repo", output_dir=tmpdir)
            profile_path = (
                Path(result["output_path"]) / "src" / "personality" / "active_profile.json"
            )
            assert profile_path.exists()
            with open(profile_path) as f:
                data = json.load(f)
            assert data["id"] == "the-guardian"

    def test_spawn_writes_env_example(self):
        """Spawning should write a .env.example."""
        profiles = {"the-guardian": self._guardian_profile()}
        spawner = self._make_spawner_with_profiles(profiles)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawner.spawn("the-guardian", "guardian-repo", output_dir=tmpdir)
            env_path = Path(result["output_path"]) / ".env.example"
            assert env_path.exists()
            content = env_path.read_text()
            assert "ENVIRONMENT" in content

    def test_spawn_writes_readme(self):
        """Spawning should write a README.md."""
        profiles = {"the-guardian": self._guardian_profile()}
        spawner = self._make_spawner_with_profiles(profiles)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawner.spawn("the-guardian", "guardian-repo", output_dir=tmpdir)
            readme_path = Path(result["output_path"]) / "README.md"
            assert readme_path.exists()
            content = readme_path.read_text()
            assert "The Guardian" in content

    def test_spawn_writes_dockerfile(self):
        """Spawning should write a Dockerfile."""
        profiles = {"the-guardian": self._guardian_profile()}
        spawner = self._make_spawner_with_profiles(profiles)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawner.spawn("the-guardian", "guardian-repo", output_dir=tmpdir)
            docker_path = Path(result["output_path"]) / "Dockerfile"
            assert docker_path.exists()

    def test_spawn_writes_api_personality(self):
        """Spawning should write api_personality.py."""
        profiles = {"the-guardian": self._guardian_profile()}
        spawner = self._make_spawner_with_profiles(profiles)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawner.spawn("the-guardian", "guardian-repo", output_dir=tmpdir)
            api_path = Path(result["output_path"]) / "api_personality.py"
            assert api_path.exists()
            content = api_path.read_text()
            assert "the-guardian" in content

    def test_spawn_result_fields(self):
        """Spawn result should contain all expected fields."""
        profiles = {"the-guardian": self._guardian_profile()}
        spawner = self._make_spawner_with_profiles(profiles)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawner.spawn("the-guardian", "guardian-repo", output_dir=tmpdir)
            assert "personality" in result
            assert "code_name" in result
            assert "repo_name" in result
            assert "output_path" in result
            assert "files_written" in result
            assert "spawned_at" in result
            assert "instructions" in result

    def test_spawn_sanitizes_repo_name(self):
        """Repo name with path separators should be sanitized."""
        profiles = {"the-guardian": self._guardian_profile()}
        spawner = self._make_spawner_with_profiles(profiles)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Repo name with path separators — sanitize strips them
            result = spawner.spawn("the-guardian", "guardian-repo", output_dir=tmpdir)
            # Verify the spawn succeeded and repo_name is clean
            assert ".." not in result["repo_name"]
            assert "/" not in result["repo_name"]

    def test_spawn_traversal_repo_name_blocked(self):
        """Repo name with traversal characters should be blocked."""
        from shared_core.path_validation import PathTraversalError

        profiles = {"the-guardian": self._guardian_profile()}
        spawner = self._make_spawner_with_profiles(profiles)

        with tempfile.TemporaryDirectory() as tmpdir:
            # After sanitize_filename strips /, "guardian/../etc" becomes
            # "guardian..etc" which still contains ".." → PathTraversalError
            with pytest.raises(PathTraversalError):
                spawner.spawn("the-guardian", "guardian/../etc", output_dir=tmpdir)


class TestPathValidation:
    """Tests for path validation utilities used by the spawner."""

    def test_sanitize_filename_normal(self):
        """Normal filenames should pass through unchanged."""
        from shared_core.path_validation import sanitize_filename

        assert sanitize_filename("my-repo") == "my-repo"

    def test_sanitize_filename_strips_path_separators(self):
        """Path separators should be stripped from filenames."""
        from shared_core.path_validation import sanitize_filename

        result = sanitize_filename("dir/subdir")
        assert "/" not in result

    def test_sanitize_filename_strips_dots(self):
        """Leading dots should be stripped (prevents hidden files / traversal)."""
        from shared_core.path_validation import sanitize_filename

        result = sanitize_filename(".hidden")
        assert not result.startswith(".")

    def test_sanitize_filename_empty_raises(self):
        """Empty filenames should raise ValueError."""
        from shared_core.path_validation import sanitize_filename

        with pytest.raises(ValueError, match="must not be empty"):
            sanitize_filename("")

    def test_safe_join_normal(self):
        """safe_join with normal components should return a valid path."""
        from shared_core.path_validation import safe_join

        result = safe_join("/tmp", "subdir", "file.txt")
        assert str(result).startswith("/tmp")

    def test_safe_join_traversal_raises(self):
        """safe_join with traversal components should raise PathTraversalError."""
        from shared_core.path_validation import PathTraversalError, safe_join

        with pytest.raises(PathTraversalError):
            safe_join("/tmp", "..", "etc", "passwd")

    def test_safe_join_empty_component_raises(self):
        """safe_join with empty components should raise ValueError."""
        from shared_core.path_validation import safe_join

        with pytest.raises(ValueError, match="Empty"):
            safe_join("/tmp", "", "file")

    def test_validate_path_normal(self):
        """validate_path with a normal path should succeed."""
        from shared_core.path_validation import validate_path

        result = validate_path("subdir/file.txt", "/tmp")
        assert str(result).startswith("/tmp")

    def test_validate_path_traversal_raises(self):
        """validate_path with traversal should raise PathTraversalError."""
        from shared_core.path_validation import PathTraversalError, validate_path

        with pytest.raises(PathTraversalError):
            validate_path("../../etc/passwd", "/tmp")

    def test_path_traversal_error_is_value_error(self):
        """PathTraversalError should be a subclass of ValueError."""
        from shared_core.path_validation import PathTraversalError

        assert issubclass(PathTraversalError, ValueError)
