import pytest

from src.skills.code_generator import CodeGenerationRequest, code_generator


@pytest.mark.asyncio
async def test_code_generator_cli_logic_csv_count():
    request = CodeGenerationRequest(
        description="A Typer CLI app that reads a CSV file and prints the number of rows.",
        language="python",
    )
    result = await code_generator.generate(request)
    assert "import csv" in result.code
    assert "data = list(csv.reader(f))" in result.code
    assert "Count:" in result.code


@pytest.mark.asyncio
async def test_code_generator_cli_logic_json_write():
    request = CodeGenerationRequest(
        description="A Typer CLI app that reads a JSON file, modifies it, and saves the output.",
        language="python",
    )
    result = await code_generator.generate(request)
    assert "import json" in result.code
    assert "data = json.load(f)" in result.code
    assert "json.dump(data, f, indent=2)" in result.code
    assert "Saved JSON to" in result.code


@pytest.mark.asyncio
async def test_code_generator_cli_logic_default():
    request = CodeGenerationRequest(description="A generic CLI tool.", language="python")
    result = await code_generator.generate(request)
    assert "data = f.read()" in result.code
    assert "pass" in result.code


@pytest.mark.asyncio
async def test_code_generator_cli_logic_text_write():
    request = CodeGenerationRequest(
        description="A generic CLI tool that writes output.", language="python"
    )
    result = await code_generator.generate(request)
    assert "data = f.read()" in result.code
    assert "f.write(str(data))" in result.code
