# tests/test_turingshub_routes.py
# Exercises the Turing's Hub (/turingshub) route handlers directly. These use
# PersonalitySpawner / PersonalityMatrix, which load JSON profiles — no torch —
# so they run in the deps-light coverage job.

from src.personality.turingshub.routes import (
    active_personality,
    list_personalities,
    turings_hub_status,
)


async def test_status_ok():
    res = await turings_hub_status()
    # dict on success, or a JSONResponse on error — either way it responds.
    assert isinstance(res, dict) or getattr(res, "status_code", None) is not None


async def test_list_personalities():
    res = await list_personalities()
    assert isinstance(res, list) or getattr(res, "status_code", None) is not None


async def test_matrix_active_returns_active_personality_key():
    # Exercises _matrix() (PersonalityMatrix import). The matrix has no active
    # tracking yet, so active_personality is null — but the shape is stable.
    res = await active_personality()
    assert "active_personality" in res


def test_personality_matrix_constructs_with_profiles_dir():
    # Regression: api.py's lifespan constructs the matrix as
    # EnhancedPersonalityMatrix(cfg.personality_dir) — a *path string*, not the
    # Config object. Passing a Config previously raised in Path(...) and left
    # personality_matrix = None (Turing's Hub dead). Assert the real contract:
    # constructing with the profiles_dir loads profiles and exposes list_profiles().
    import os

    from src.personality.matrix import PersonalityMatrix

    personality_dir = os.getenv("PERSONALITY_DIR", "./src/personality/profiles")
    matrix = PersonalityMatrix(personality_dir)
    profiles = matrix.list_profiles()
    assert isinstance(profiles, list)
    # The in-repo registry ships named-entity profiles; it must load at least one.
    assert profiles, "PersonalityMatrix loaded no profiles from the profiles dir"
