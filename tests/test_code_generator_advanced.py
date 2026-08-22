import pytest
from src.skills.code_generator import AdvancedCodeGenerator, CodeGenerationRequest

@pytest.fixture
def generator():
    return AdvancedCodeGenerator()

def test_extract_pydantic_fields_no_fields(generator):
    req = CodeGenerationRequest(description="Just a simple router")
    fields = generator._extract_pydantic_fields(req.description)
    assert fields == "pass"

def test_extract_pydantic_fields_with_fields(generator):
    req = CodeGenerationRequest(description="Create a model with name: str, age: int, and is_active (bool)")
    fields = generator._extract_pydantic_fields(req.description)
    assert "name: str" in fields
    assert "age: int" in fields
    assert "is_active: bool" in fields

def test_apply_substitutions_with_fields(generator):
    template = """
    class {Model}Request(BaseModel):
        # TODO: define fields
        pass
    class {Model}Response(BaseModel):
        # TODO: define response fields
    """
    req = CodeGenerationRequest(description="Create a user model with name: str, age: int")
    result = generator._apply_substitutions(template, req)

    # Check that placeholders were replaced
    assert "name: str" in result
    assert "age: int" in result
    assert "# TODO: define fields" not in result
    assert "# TODO: define response fields" not in result

def test_apply_substitutions_no_fields(generator):
    template = """
    class {Model}Request(BaseModel):
        # TODO: define fields
        pass
    class {Model}Response(BaseModel):
        # TODO: define response fields
    """
    req = CodeGenerationRequest(description="Create a generic handler")
    result = generator._apply_substitutions(template, req)

    assert "pass" in result
