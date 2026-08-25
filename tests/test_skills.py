import pytest

from src.skills.code_generator import AdvancedCodeGenerator, CodeGenerationRequest


@pytest.mark.asyncio
async def test_code_generator_fastapi_handler():
    generator = AdvancedCodeGenerator()
    request = CodeGenerationRequest(
        description="handler for user login web request",
        language="python",
        context="",
        max_tokens=100,
        constraints=[],
    )
    result = await generator.generate(request)
    code = result.code

    assert "def handle_handler" in code
    assert 'logger.info("Processing handler request")' in code
    assert 'raise ValueError("Empty payload")' in code
    assert "return JSONResponse" in code

def test_enhanced_registry_cosine() -> None:
    from src.skills.enhanced_registry import EnhancedSkillRegistry
    registry = EnhancedSkillRegistry()
    assert registry._cosine([], []) == 0.0
    assert registry._cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert round(registry._cosine([1.0, 2.0], [1.0, 2.0]), 5) == 1.00000
    res = registry._cosine([1.0, 2.0, 3.0], [1.0, 2.0])
    assert isinstance(res, float)
