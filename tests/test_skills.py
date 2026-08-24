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
