import pytest
import math
from src.skills.enhanced_registry import EnhancedSkillRegistry, Skill


@pytest.mark.asyncio
async def test_enhanced_registry_cosine():
    registry = EnhancedSkillRegistry()

    # Test identical vectors
    a = [1.0, 0.0]
    b = [1.0, 0.0]
    assert math.isclose(registry._cosine(a, b), 1.0)

    # Test orthogonal vectors
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert math.isclose(registry._cosine(a, b), 0.0)

    # Test unequal length vectors
    a = [1.0, 0.0, 1.0]
    b = [1.0, 0.0]

    # _cosine handles lengths dynamically
    # mag_a = sqrt(2), mag_b = sqrt(1) = 1
    # dot = 1
    # result = 1 / sqrt(2)
    expected = 1.0 / math.sqrt(2.0)
    assert math.isclose(registry._cosine(a, b), expected)

    # Reverse order for unequal lengths
    assert math.isclose(registry._cosine(b, a), expected)

    # Test small magnitudes
    assert registry._cosine([1e-13], [1e-13]) == 0.0


@pytest.mark.asyncio
async def test_enhanced_registry_search():
    registry = EnhancedSkillRegistry()
    registry.register(
        Skill(id="1", name="Test", category="test", description="desc", content="content")
    )
    results = await registry.search("test")
    assert len(results) == 1
    assert results[0].skill.id == "1"
