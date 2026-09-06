import pytest

from src.skills.code_generator import (
    AdvancedCodeGenerator,
    CodeGenerationRequest,
    code_generator,
)


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


class TestGeneratedProgramsActuallyRun:
    """Execute the generated logic instead of asserting on its text.

    String assertions passed while the generated CLI was broken in two ways at
    once: CSV-in/JSON-out emitted `json.dump` having imported only `csv`, so the
    program died on NameError, and every CSV-out path wrote `str(data)` -- Python
    list syntax into a file named .csv. Neither is visible unless the code runs.
    """

    @staticmethod
    def _run(generated: str, tmp_path, source: str):
        """Exec the generated logic with input/output/verbose bound."""
        src = tmp_path / "in.dat"
        src.write_text(source, encoding="utf-8")
        dst = tmp_path / "out.dat"

        class _Typer:
            @staticmethod
            def echo(_msg):
                return None

        scope = {"input": str(src), "output": str(dst), "verbose": False, "typer": _Typer}
        # Running the generated program is the whole point: the NameError and
        # the str(data) CSV bug are both invisible to a string assertion. The
        # source comes from the function under test, built from a literal
        # description in this file; it reads and writes only inside tmp_path and
        # never sees user input.
        exec(compile(generated, "<generated>", "exec"), scope)  # noqa: S102  # nosec B102
        return dst

    def test_csv_in_json_out_runs_and_writes_json(self, tmp_path):
        """The NameError case: json.dump reached with only `csv` imported."""
        import json

        gen = AdvancedCodeGenerator()
        code = gen._translate_nl_to_cli_logic("read a CSV file and write JSON output")
        dst = self._run(code, tmp_path, "a,b\n1,2\n")
        assert json.loads(dst.read_text()) == [["a", "b"], ["1", "2"]]

    def test_csv_in_csv_out_round_trips(self, tmp_path):
        """str(data) previously wrote "[['a', 'b'], ['1', '2']]" into a .csv."""
        import csv
        import io

        gen = AdvancedCodeGenerator()
        code = gen._translate_nl_to_cli_logic("read a CSV file and write CSV output")
        dst = self._run(code, tmp_path, "a,b\n1,2\n")
        assert list(csv.reader(io.StringIO(dst.read_text()))) == [["a", "b"], ["1", "2"]]

    def test_json_in_csv_out_runs(self, tmp_path):
        import csv
        import io

        gen = AdvancedCodeGenerator()
        code = gen._translate_nl_to_cli_logic("read a JSON file and write CSV output")
        dst = self._run(code, tmp_path, '[["a", "b"], ["1", "2"]]')
        assert list(csv.reader(io.StringIO(dst.read_text()))) == [["a", "b"], ["1", "2"]]

    def test_text_in_json_out_runs(self, tmp_path):
        import json

        gen = AdvancedCodeGenerator()
        code = gen._translate_nl_to_cli_logic("read the file and write JSON output")
        dst = self._run(code, tmp_path, "hello")
        assert json.loads(dst.read_text()) == "hello"


class TestFilenameTokensAreNotOutputVerbs:
    def test_a_file_named_output_csv_is_read_as_csv(self):
        """ "output" inside a filename previously split the clause.

        The description asks only to count. It named a CSV file, so the parser
        must read CSV -- and must not invent a writer nobody asked for.
        """
        gen = AdvancedCodeGenerator()
        code = gen._translate_nl_to_cli_logic("read output.csv and count rows")
        assert "csv.reader" in code
        assert "open(output" not in code, "no output was requested"

    def test_a_real_output_verb_still_writes(self):
        gen = AdvancedCodeGenerator()
        code = gen._translate_nl_to_cli_logic("read a JSON file and write JSON output")
        assert "json.dump" in code

    def test_an_inflected_verb_still_writes(self):
        """ "saves" must keep matching; a bare word boundary would not match it."""
        gen = AdvancedCodeGenerator()
        code = gen._translate_nl_to_cli_logic("reads a JSON file and saves the output")
        assert "json.dump" in code
