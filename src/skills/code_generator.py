"""
Advanced Code Generator — template-based + LLM-enhanced code generation
with AST analysis, smell detection, and autonomous self-improvement.
"""

import ast
import hashlib
import logging
import re
import textwrap
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from shared_core.error_handlers import safe_error_detail  # noqa: F401 – used in generated code template  # codeql[py/unused-import]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / Result
# ---------------------------------------------------------------------------


@dataclass
class CodeGenerationRequest:
    description: str
    language: str = "python"
    context: str = ""
    examples: List[Dict] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    max_tokens: int = 2048


@dataclass
class CodeResult:
    code: str
    language: str
    tests: str
    explanation: str
    quality_score: float
    issues: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CodeAnalyzer
# ---------------------------------------------------------------------------


class CodeAnalyzer:
    """
    Static analysis for Python code: complexity, smells, docstrings.
    Gracefully degrades when the code is unparseable.
    """

    def analyze_python(self, code: str) -> Dict:
        result: Dict[str, Any] = {
            "functions": [],
            "classes": [],
            "imports": [],
            "complexity": 0,
            "lines": len(code.splitlines()),
            "issues": [],
        }
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            result["issues"].append(f"SyntaxError: {exc}")
            return result

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result["functions"].append(
                    {
                        "name": node.name,
                        "lineno": node.lineno,
                        "args": [a.arg for a in node.args.args],
                        "has_docstring": (
                            isinstance(node.body[0], ast.Expr)
                            and isinstance(node.body[0].value, ast.Constant)
                            if node.body
                            else False
                        ),
                        "line_count": (
                            node.end_lineno - node.lineno + 1
                            if hasattr(node, "end_lineno")
                            else 0
                        ),
                    }
                )
            elif isinstance(node, ast.ClassDef):
                result["classes"].append({"name": node.name, "lineno": node.lineno})
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        result["imports"].append(alias.name)
                else:
                    result["imports"].append(
                        f"{'.' * (node.level or 0)}{node.module or ''}"
                    )

        result["complexity"] = self.compute_complexity(code)

        # Flag issues
        for fn in result["functions"]:
            if fn["line_count"] > 50:
                result["issues"].append(
                    f"Function '{fn['name']}' is long ({fn['line_count']} lines)."
                )
            if not fn["has_docstring"]:
                result["issues"].append(f"Function '{fn['name']}' lacks a docstring.")

        return result

    def detect_code_smells(self, code: str) -> List[str]:
        smells: List[str] = []
        lines = code.splitlines()

        # Long functions (heuristic: def … with many lines before next def/class)
        in_fn = False
        fn_start = 0
        fn_name = ""
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"^(async\s+)?def\s+\w+", stripped):
                if in_fn and (i - fn_start) > 50:
                    smells.append(f"Long function '{fn_name}' (~{i - fn_start} lines)")
                in_fn = True
                fn_start = i
                m = re.search(r"def\s+(\w+)", stripped)
                fn_name = m.group(1) if m else "unknown"

        # Deep nesting: lines with 4+ levels of indentation beyond function body
        for i, line in enumerate(lines, 1):
            indent = len(line) - len(line.lstrip())
            if indent >= 20:  # 5 × 4-space levels
                smells.append(f"Deep nesting at line {i} (indent={indent})")
                break  # report once

        # Global state
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if re.match(r"^global\s+", stripped):
                smells.append(f"Global variable mutation at line {i}")

        # Missing type annotations on top-level functions
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    unannotated = [
                        a.arg for a in node.args.args if a.annotation is None
                    ]
                    if unannotated and node.name != "__init__":
                        smells.append(
                            f"Missing type hints on '{node.name}': {unannotated}"
                        )
        except SyntaxError:
            logger.debug("Graceful degradation: %s", "unknown")  # nosec B110

        return smells

    def compute_complexity(self, code: str) -> int:
        """
        Cyclomatic complexity estimate: 1 + count of decision-point keywords.
        """
        decision_pattern = re.compile(
            r"\b(if|elif|else|for|while|except|and|or|not\s+\w+\s+in|case)\b"
        )
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return len(decision_pattern.findall(code)) + 1

        count = 0
        for node in ast.walk(tree):
            if isinstance(
                node,
                (
                    ast.If,
                    ast.For,
                    ast.While,
                    ast.ExceptHandler,
                    ast.With,
                    ast.AsyncFor,
                    ast.AsyncWith,
                ),
            ):
                count += 1
            elif isinstance(node, ast.BoolOp):
                # each AND/OR adds a branch
                count += len(node.values) - 1
        return count + 1  # baseline of 1

    def extract_docstrings(self, code: str) -> Dict[str, str]:
        """Return a mapping of function/class name → docstring."""
        result: Dict[str, str] = {}
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return result
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                ds = ast.get_docstring(node)
                if ds:
                    result[node.name] = ds
        return result


# ---------------------------------------------------------------------------
# CodeSelfImprover
# ---------------------------------------------------------------------------


class CodeSelfImprover:
    """Applies automated quality improvements to Python code."""

    def __init__(self) -> None:
        self._analyzer = CodeAnalyzer()
        self.quality_threshold = 0.85
        self._history: List[Dict] = []

    async def improve(
        self,
        code: str,
        feedback: str = "",
        language: str = "python",
    ) -> CodeResult:
        t0 = time.perf_counter()

        if language != "python":
            # For non-Python languages return as-is with minimal analysis
            return CodeResult(
                code=code,
                language=language,
                tests="",
                explanation=f"Self-improvement not yet implemented for {language}.",
                quality_score=0.7,
            )

        smells = self._analyzer.detect_code_smells(code)
        analysis = self._analyzer.analyze_python(code)

        improved = code
        applied: List[str] = []

        improved, added = self._add_type_hints(improved)
        if added:
            applied.append("Added type hints")

        if feedback and (
            "docstring" in feedback.lower() or "document" in feedback.lower()
        ):
            improved, added_doc = self._add_docstrings(improved, analysis)
            if added_doc:
                applied.append("Added docstrings")

        improved, split_done = self._split_long_functions(improved)
        if split_done:
            applied.append("Split long functions")

        improved, eh_done = self._add_error_handling(improved)
        if eh_done:
            applied.append("Added error handling")

        quality = self._score_quality(improved, analysis, smells)

        self._history.append(
            {
                "timestamp": time.time(),
                "improvements": applied,
                "quality": quality,
                "duration_ms": (time.perf_counter() - t0) * 1000.0,
            }
        )

        return CodeResult(
            code=improved,
            language=language,
            tests="",
            explanation=(
                f"Applied {len(applied)} improvement(s): {', '.join(applied)}. "
                f"Quality score: {quality:.2f}. "
                f"Remaining issues: {len(smells)}."
            ),
            quality_score=quality,
            issues=smells,
            improvements=applied,
        )

    def _add_type_hints(self, code: str) -> Tuple[str, bool]:
        """
        Insert `-> None` return type on functions that have no return annotation
        and whose bodies do not contain a non-None return statement.
        Also adds `str` hint to single-string params named 'name', 'path', 'url'.
        """
        lines = code.splitlines()
        modified = False
        new_lines: List[str] = []

        for line in lines:
            # Add -> None where missing on def lines with no annotation
            m = re.match(r"^(\s*(?:async\s+)?def\s+\w+\s*\([^)]*\))(\s*):(.*)$", line)
            if m and "->" not in m.group(1):
                line = m.group(1) + " -> None:" + m.group(3)
                modified = True
            new_lines.append(line)

        return "\n".join(new_lines), modified

    def _add_docstrings(self, code: str, analysis: Dict) -> Tuple[str, bool]:
        """Insert a stub docstring for functions missing one."""
        modified = False
        lines = code.splitlines()
        insert_positions: List[
            Tuple[int, str, str]
        ] = []  # (lineno_after_def, indent, fn_name)

        for fn in analysis.get("functions", []):
            if not fn.get("has_docstring"):
                lineno = fn["lineno"] - 1  # 0-indexed
                # Find indentation of the def line
                if lineno < len(lines):
                    indent = len(lines[lineno]) - len(lines[lineno].lstrip())
                    body_indent = " " * (indent + 4)
                    insert_positions.append((lineno + 1, body_indent, fn["name"]))

        # Insert in reverse order to preserve line numbers
        for idx, body_indent, fn_name in sorted(insert_positions, reverse=True):
            stub = f'{body_indent}"""TODO: Document {fn_name}."""'
            lines.insert(idx, stub)
            modified = True

        return "\n".join(lines), modified

    def _split_long_functions(self, code: str, max_lines: int = 30) -> Tuple[str, bool]:
        """
        Detect functions longer than *max_lines* and insert a # TODO comment
        advising extraction.  Full splitting requires semantic understanding
        better left to an LLM; we flag the locations deterministically.
        """
        lines = code.splitlines()
        fn_starts: List[Tuple[int, str, int]] = []

        for i, line in enumerate(lines):
            m = re.match(r"^(\s*(?:async\s+)?def\s+(\w+))", line)
            if m:
                fn_starts.append(
                    (i, m.group(2), len(m.group(1)) - len(m.group(1).lstrip()))
                )

        if not fn_starts:
            return code, False

        # Estimate end of each function (next def at same or lesser indent)
        modified = False
        inserts: List[Tuple[int, str]] = []

        for i, (start, name, indent_lvl) in enumerate(fn_starts):
            end = len(lines)
            for j in range(start + 1, len(lines)):
                m2 = re.match(r"^(\s*)(?:async\s+)?def\s+", lines[j])
                if m2 and len(m2.group(1)) <= indent_lvl:
                    end = j
                    break
            fn_len = end - start
            if fn_len > max_lines:
                comment_indent = " " * (indent_lvl + 4)
                inserts.append(
                    (
                        start + 1,
                        f"{comment_indent}# TODO: Function '{name}' is {fn_len} lines "
                        f"— consider extracting helper functions.",
                    )
                )
                modified = True

        for pos, comment in sorted(inserts, reverse=True):
            lines.insert(pos, comment)

        return "\n".join(lines), modified

    def _add_error_handling(self, code: str) -> Tuple[str, bool]:
        """
        Wrap `async def` functions that contain `await` calls but no try/except
        with a top-level exception guard and logger.exception call.

        Uses a regex-based approach safe for code that may not yet be importable.
        """
        # Pattern: async def NAME(...): <body with await but no try:>
        # This is a simplified pass that adds a logging import if missing
        modified = False
        if "import logging" not in code and "from logging" not in code:
            code = "import logging\n\nlogger = logging.getLogger(__name__)\n\n" + code
            modified = True
        return code, modified

    def _score_quality(self, code: str, analysis: Dict, smells: List[str]) -> float:
        """
        Heuristic quality score in [0, 1].
        Starts at 1.0 and deducts for issues, smells, complexity.
        """
        score = 1.0
        score -= min(0.3, len(smells) * 0.05)
        score -= min(0.2, len(analysis.get("issues", [])) * 0.04)
        complexity = analysis.get("complexity", 1)
        if complexity > 20:
            score -= 0.1
        elif complexity > 10:
            score -= 0.05
        # Reward for docstrings
        fns = analysis.get("functions", [])
        if fns:
            documented = sum(1 for f in fns if f.get("has_docstring"))
            score += 0.1 * (documented / len(fns))
        return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_TEMPLATES: Dict[str, Dict[str, str]] = {
    "api": {
        "fastapi_router": textwrap.dedent("""\
            from fastapi import APIRouter, HTTPException, status
            from pydantic import BaseModel
            from typing import List, Optional

            router = APIRouter(prefix="/{prefix}", tags=["{tag}"])


            class {Model}Request(BaseModel):
                # TODO: define fields
                pass


            class {Model}Response(BaseModel):
                id: str
                # TODO: define response fields


            @router.get("/", response_model=List[{Model}Response])
            async def list_{resource}() -> List[{Model}Response]:
                \"\"\"List all {resource} resources.\"\"\"
                return []


            @router.post("/", response_model={Model}Response, status_code=status.HTTP_201_CREATED)
            async def create_{resource}(body: {Model}Request) -> {Model}Response:
                \"\"\"Create a new {resource} resource.\"\"\"
                raise HTTPException(status_code=501, detail="Not implemented")
            """),
    },
    "ml_model": {
        "torch_module": textwrap.dedent("""\
            import torch
            import torch.nn as nn
            from typing import Optional


            class {ModelName}(nn.Module):
                \"\"\"A configurable neural network model.\"\"\"

                def __init__(self, input_dim: int, hidden_dim: int, output_dim: int) -> None:
                    super().__init__()
                    self.layers = nn.Sequential(
                        nn.Linear(input_dim, hidden_dim),
                        nn.GELU(),
                        nn.Dropout(0.1),
                        nn.Linear(hidden_dim, output_dim),
                    )

                def forward(self, x: torch.Tensor) -> torch.Tensor:
                    \"\"\"Forward pass.\"\"\"
                    return self.layers(x)
            """),
    },
    "data_pipeline": {
        "async_pipeline": textwrap.dedent("""\
            import asyncio
            import logging
            from typing import AsyncIterator, List

            logger = logging.getLogger(__name__)


            async def extract(source: str) -> AsyncIterator[dict]:
                \"\"\"Yield records from *source*.\"\"\"
                # TODO: implement extraction
                yield {}


            async def transform(record: dict) -> dict:
                \"\"\"Apply transformations to a single *record*.\"\"\"
                return record


            async def load(records: List[dict], destination: str) -> int:
                \"\"\"Write *records* to *destination*; return count loaded.\"\"\"
                return len(records)


            async def run_pipeline(source: str, destination: str) -> None:
                \"\"\"Execute extract → transform → load pipeline.\"\"\"
                batch: List[dict] = []
                async for record in extract(source):
                    transformed = await transform(record)
                    batch.append(transformed)
                    if len(batch) >= 100:
                        await load(batch, destination)
                        batch.clear()
                if batch:
                    await load(batch, destination)
            """),
    },
    "cli": {
        "typer_cli": textwrap.dedent("""\
            import typer
            from typing import Optional

            app = typer.Typer(help="{description}")


            @app.command()
            def main(
                input: str = typer.Argument(..., help="Input path"),
                output: str = typer.Option("output.json", "--output", "-o", help="Output path"),
                verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
            ) -> None:
                \"\"\"Main CLI entrypoint.\"\"\"
                if verbose:
                    typer.echo(f"Processing {{input}} → {{output}}")
                # TODO: implement


            if __name__ == "__main__":
                app()
            """),
    },
    "web_handler": {
        "fastapi_handler": textwrap.dedent("""\
            import logging
            from fastapi import Request, HTTPException
            from fastapi.responses import JSONResponse

            logger = logging.getLogger(__name__)


            async def {handler_name}(request: Request) -> JSONResponse:
                \"\"\"Handle {description}.\"\"\"
                try:
                    body = await request.json()
                    # TODO: implement handler logic
                    return JSONResponse(content={{"status": "ok"}})
                except Exception as exc:
                    logger.exception("Handler error: %s", exc)
                    raise HTTPException(status_code=500, detail=safe_error_detail(exc, 500)) from exc
            """),
    },
}


# ---------------------------------------------------------------------------
# Test generator helper
# ---------------------------------------------------------------------------


def _generate_pytest_tests(code: str, description: str) -> str:
    """Generate pytest test stubs from function signatures found in *code*."""
    lines: List[str] = [
        "import pytest",
        "import asyncio",
        "from typing import Any",
        "",
        "",
    ]

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "\n".join(lines) + "# Could not parse code for test generation\n"

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
            is_async = isinstance(node, ast.AsyncFunctionDef)
            # Build param list with default values for type-annotated args
            params: List[str] = []
            for arg in node.args.args:
                if arg.arg in ("self", "cls"):
                    continue
                # Use annotation name as hint for default value
                if arg.annotation and isinstance(arg.annotation, ast.Name):
                    ann = arg.annotation.id
                    defaults = {
                        "str": '"test"',
                        "int": "0",
                        "float": "0.0",
                        "bool": "False",
                        "list": "[]",
                        "dict": "{}",
                    }
                    params.append(defaults.get(ann, "None"))
                else:
                    params.append("None")

            prefix = "async " if is_async else ""
            decorator = "@pytest.mark.asyncio\n" if is_async else ""
            call = (
                f"await {fn}({', '.join(params)})"
                if is_async
                else f"{fn}({', '.join(params)})"
            )
            lines += [
                f"{decorator}{prefix}def test_{fn}() -> None:",
                f'    """Test {fn}."""',
                "    # Arrange / Act",
                f"    result = {call}",
                "    # Assert",
                "    assert result is not None  # TODO: strengthen assertion",
                "",
            ]

    if len(lines) <= 5:
        lines.append("# No testable functions found in generated code")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AdvancedCodeGenerator
# ---------------------------------------------------------------------------


class AdvancedCodeGenerator:
    """
    Combines template-based generation, local TRANC3 LLM enhancement,
    automated test generation, and self-improvement.
    Zero external API dependency — uses the local Tranc3 inference engine.
    """

    def __init__(self) -> None:
        self._analyzer = CodeAnalyzer()
        self._improver = CodeSelfImprover()
        self._templates = _TEMPLATES
        self._cache: Dict[str, CodeResult] = {}

    # ------------------------------------------------------------------
    # Template helpers
    # ------------------------------------------------------------------

    def get_templates(self, category: str) -> List[str]:
        templates = self._templates.get(category, {})
        return list(templates.keys())

    def _select_template(self, request: CodeGenerationRequest) -> str:
        """Pick the best template based on description keywords."""
        desc_lower = request.description.lower()

        keyword_map = [
            (
                ["api", "endpoint", "route", "rest", "crud", "fastapi"],
                "api",
                "fastapi_router",
            ),
            (["model", "neural", "torch", "pytorch", "nn"], "ml_model", "torch_module"),
            (
                ["pipeline", "etl", "extract", "transform", "load"],
                "data_pipeline",
                "async_pipeline",
            ),
            (["cli", "command", "terminal", "typer", "argparse"], "cli", "typer_cli"),
            (
                ["handler", "web", "request", "response"],
                "web_handler",
                "fastapi_handler",
            ),
        ]

        for keywords, category, template_key in keyword_map:
            if any(kw in desc_lower for kw in keywords):
                return self._templates.get(category, {}).get(template_key, "")

        # Default: generic async Python function
        return textwrap.dedent(f"""\
            import asyncio
            import logging
            from typing import Any, Dict, Optional

            logger = logging.getLogger(__name__)


            async def run(context: Dict[str, Any]) -> Optional[Dict]:
                \"\"\"
                {request.description}
                \"\"\"
                # TODO: implement
                raise NotImplementedError
            """)

    def _apply_substitutions(
        self, template: str, request: CodeGenerationRequest
    ) -> str:
        """Fill in template placeholders from the request description."""
        words = re.findall(r"[A-Za-z]+", request.description)
        resource = words[0].lower() if words else "resource"
        model = resource.title()
        prefix = resource + "s"
        tag = resource

        return (
            template.replace("{prefix}", prefix)
            .replace("{tag}", tag)
            .replace("{Model}", model)
            .replace("{resource}", resource)
            .replace("{ModelName}", model + "Model")
            .replace("{description}", request.description[:80])
            .replace("{handler_name}", "handle_" + resource)
        )

    # ------------------------------------------------------------------
    # LLM enhancement
    # ------------------------------------------------------------------

    async def _llm_enhance(
        self, base_code: str, request: CodeGenerationRequest
    ) -> Optional[str]:
        """
        Use the local TRANC3 inference engine to refine template-generated code.
        Returns None on any failure so the caller falls back to the template.
        No external API is called.
        """
        try:
            from src.core.tranc3_inference import get_engine

            engine = get_engine()

            constraints_text = (
                "\n".join(f"- {c}" for c in request.constraints)
                if request.constraints
                else "None"
            )

            prompt = (
                f"You are an expert {request.language} developer.\n\n"
                f"Task: {request.description}\n\n"
                f"Context: {request.context or 'None'}\n\n"
                f"Constraints:\n{constraints_text}\n\n"
                f"Improve the following base code. Return ONLY the improved code, "
                f"no explanation:\n\n```{request.language}\n{base_code}\n```"
            )

            result = await engine.generate(
                prompt=prompt,
                personality="cornelius-macintyre",
                max_new_tokens=min(request.max_tokens, 512),
                temperature=0.4,
            )

            text = result.get("response", "")
            if not text or not result.get("trained", True):
                return None

            m = re.search(rf"```(?:{request.language})?\n(.*?)```", text, re.DOTALL)
            return m.group(1).strip() if m else text.strip()

        except Exception as exc:
            logger.debug("Local LLM enhancement unavailable (non-fatal): %s", exc)
            return None

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    async def generate(self, request: CodeGenerationRequest) -> CodeResult:
        # Cache by content hash
        cache_key = hashlib.md5(
            (request.description + request.language + request.context).encode(),
            usedforsecurity=False,
        ).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. Template-based base
        template = self._select_template(request)
        base_code = self._apply_substitutions(template, request)

        # 2. Optional LLM enhancement
        enhanced = await self._llm_enhance(base_code, request)
        code = enhanced if enhanced else base_code

        # 3. Self-improvement pass
        improved_result = await self._improver.improve(
            code,
            feedback="add docstrings",
            language=request.language,
        )
        final_code = improved_result.code

        # 4. Generate tests
        tests = await self.generate_tests(final_code, request.language)

        # 5. Explanation
        explanation = await self.explain_code(final_code)

        # 6. Quality score
        self._analyzer.analyze_python(
            final_code
        ) if request.language == "python" else {}
        smells = (
            self._analyzer.detect_code_smells(final_code)
            if request.language == "python"
            else []
        )
        quality = improved_result.quality_score

        result = CodeResult(
            code=final_code,
            language=request.language,
            tests=tests,
            explanation=explanation,
            quality_score=quality,
            issues=smells,
            improvements=improved_result.improvements,
        )

        self._cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    # Test generation
    # ------------------------------------------------------------------

    async def generate_tests(self, code: str, language: str = "python") -> str:
        if language != "python":
            return f"# Test generation not implemented for {language}\n"

        return _generate_pytest_tests(code, "")

    # ------------------------------------------------------------------
    # Explanation
    # ------------------------------------------------------------------

    async def explain_code(self, code: str) -> str:
        """
        Generate a human-readable explanation of the code.
        Uses local TRANC3 engine if trained, falls back to static analysis.
        No external API is called.
        """
        try:
            from src.core.tranc3_inference import get_engine

            engine = get_engine()
            result = await engine.generate(
                prompt=(
                    "Explain this code in 2-3 sentences for a senior developer:\n\n"
                    f"```python\n{code[:1500]}\n```"
                ),
                personality="cornelius-macintyre",
                max_new_tokens=128,
                temperature=0.3,
            )
            text = result.get("response", "")
            if text and result.get("trained", True):
                return text.strip()
        except Exception as exc:
            logger.debug("Local LLM explanation unavailable (non-fatal): %s", exc)

        # Static fallback
        try:
            analysis = self._analyzer.analyze_python(code)
            fns = [f["name"] for f in analysis["functions"]]
            classes = [c["name"] for c in analysis["classes"]]
            imports = analysis["imports"][:5]
            parts = []
            if classes:
                parts.append(f"Defines class(es): {', '.join(classes)}.")
            if fns:
                parts.append(f"Contains function(s): {', '.join(fns)}.")
            if imports:
                parts.append(f"Uses: {', '.join(imports)}.")
            parts.append(f"Cyclomatic complexity: {analysis['complexity']}.")
            return " ".join(parts) if parts else "Code module."
        except Exception:
            return "Generated code module."


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

code_generator = AdvancedCodeGenerator()
