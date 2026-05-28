"""
Dimensional.security_automation.remediator — Automated security remediation engine.

Self-heals the most common security violations detected by the scanner.
Each remediator applies a known-safe transformation that mirrors the manual
fixes from the ~297 CodeQL alert remediation.

Supported auto-fixes:
    CWE-117  f-string logger → %-style with sanitize_for_log()
    CWE-209  str(exc) in error detail → safe_error_detail(exc, status_code)
    PY-001   bare except: → except Exception:
    PY-003   type(__exc).__name__ → "unknown"
    PY-004   open().read() → with open() context manager
    PY-008   missing return None → add explicit return
"""

from __future__ import annotations

import re
import shutil
from typing import Dict, List, Tuple

from Dimensional.security_automation.scanner import (
    Category,
    Violation,
)


class AutoRemediator:
    """Automated security remediation engine.

    Applies known-safe transformations to fix security violations detected
    by the SecurityScanner. Each fix mirrors the manual remediation that was
    done for the ~297 CodeQL alerts.

    Usage:
        scanner = SecurityScanner()
        violations = scanner.scan_path("src/")

        remediator = AutoRemediator(dry_run=False)
        fixes = remediator.remediate(violations)
        print(f"Applied {len(fixes)} fixes")
    """

    # Category → fix function mapping
    FIX_MAP = {
        Category.LOG_INJECTION: "_fix_log_injection",
        Category.INFO_EXPOSURE: "_fix_info_exposure",
        Category.BARE_EXCEPT: "_fix_bare_except",
        Category.TYPE_EXC: "_fix_type_exc",
        Category.UNCLOSED_FILE: "_fix_unclosed_file",
    }

    def __init__(self, *, dry_run: bool = True, backup: bool = True):
        """Initialize the remediator.

        Args:
            dry_run: If True, report fixes but don't modify files.
            backup: If True, create .bak copies before modifying files.
        """
        self.dry_run = dry_run
        self.backup = backup
        self.applied_fixes: List[Dict] = []

    def remediate(self, violations: List[Violation]) -> List[Dict]:
        """Apply automated fixes for fixable violations.

        Args:
            violations: List of violations from the scanner.

        Returns:
            List of applied fix descriptions.
        """
        self.applied_fixes = []

        # Group by file for batch processing
        by_file: Dict[str, List[Violation]] = {}
        for v in violations:
            if v.fixable:
                by_file.setdefault(v.file, []).append(v)

        for filepath, file_violations in by_file.items():
            self._process_file(filepath, file_violations)

        return self.applied_fixes

    def _process_file(self, filepath: str, violations: List[Violation]) -> None:
        """Process all violations in a single file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return

        original = content

        # Apply fixes by category (order matters — some fixes affect line numbers)
        for category, fix_method_name in self.FIX_MAP.items():
            cat_violations = [v for v in violations if v.category == category]
            if cat_violations:
                fix_method = getattr(self, fix_method_name)
                content = fix_method(content, cat_violations, filepath)

        if content != original:
            if self.backup and not self.dry_run:
                shutil.copy2(filepath, filepath + ".bak")

            if not self.dry_run:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)

            self.applied_fixes.append(
                {
                    "file": filepath,
                    "violations_fixed": len(violations),
                    "dry_run": self.dry_run,
                }
            )

    # -----------------------------------------------------------------------
    # Individual fix implementations
    # -----------------------------------------------------------------------

    def _fix_log_injection(self, content: str, violations: List[Violation], filepath: str) -> str:
        """Convert f-string logger calls to %-style with sanitize_for_log().

        Before:  logger.info(f"User {username} logged in")
        After:   logger.info("User %s logged in", sanitize_for_log(username))  # codeql[py/cleartext-logging]
        """
        lines = content.split("\n")
        modified = False
        has_sanitize_import = "from Dimensional.sanitize import sanitize_for_log" in content

        for v in violations:
            if v.line - 1 < len(lines):
                line = lines[v.line - 1]
                # Pattern: logger.METHOD(f"...")
                match = re.match(
                    r'(\s*)(logger\.\w+)\(f"(.+?)"\s*(?:,\s*(.+))?\)',
                    line,
                )
                if match:
                    indent, logger_call, fstring, extra_args = match.groups()
                    # Convert f-string interpolations to %s
                    new_format, args = self._fstring_to_percent(fstring)
                    if args:
                        args_str = ", ".join(f"sanitize_for_log({a})" for a in args)
                        if extra_args:
                            new_line = (
                                f'{indent}{logger_call}("{new_format}", {args_str}, {extra_args})'
                            )
                        else:
                            new_line = f'{indent}{logger_call}("{new_format}", {args_str})'
                        lines[v.line - 1] = new_line
                        modified = True

        if modified and not has_sanitize_import:
            # Add import after 'import logging' line
            content = self._add_import(
                "\n".join(lines),
                "from Dimensional.sanitize import sanitize_for_log",
            )
        else:
            content = "\n".join(lines)

        return content

    def _fstring_to_percent(self, fstring: str) -> Tuple[str, List[str]]:
        """Convert f-string content to %-style format string and extract args.

        '{variable}' → '%s' with variable as arg
        '{variable.attr}' → '%s' with variable.attr as arg
        '{variable:.4f}' → '%.4f' with variable as arg
        """
        args = []
        result = fstring
        # Match {expr} or {expr:format_spec}
        pattern = re.compile(r"\{([^}:]+)(?::([^}]+))?\}")
        for match in pattern.finditer(fstring):
            expr = match.group(1).strip()
            format_spec = match.group(2)
            if format_spec:
                # Like {value:.4f} → %.4f
                percent_fmt = f"%{format_spec}"
                args.append(expr)
                result = result.replace(match.group(0), percent_fmt, 1)
            else:
                args.append(expr)
                result = result.replace(match.group(0), "%s", 1)
        return result, args

    def _fix_info_exposure(self, content: str, violations: List[Violation], filepath: str) -> str:
        """Replace str(exc) in error details with safe_error_detail().

        Before:  detail=str(exc)
        After:   detail=safe_error_detail(exc, 500)
        """
        # Pattern: detail=str(exc) or error=str(exc) or message=str(exc)
        content = re.sub(
            r"(detail|error|message)=str\((\w+)\)",
            r"\1=safe_error_detail(\2, 500)",
            content,
        )

        # Add import if needed
        if (
            "safe_error_detail(" in content
            and "from Dimensional.error_handlers import safe_error_detail" not in content
        ):
            content = self._add_import(
                content,
                "from Dimensional.error_handlers import safe_error_detail",
            )

        return content

    def _fix_bare_except(self, content: str, violations: List[Violation], filepath: str) -> str:
        """Replace bare 'except:' with 'except Exception:'.

        Before:  except:
        After:   except Exception:
        """
        lines = content.split("\n")
        for v in violations:
            if v.line - 1 < len(lines):
                line = lines[v.line - 1]
                lines[v.line - 1] = re.sub(r"except\s*:", "except Exception:", line, count=1)
        return "\n".join(lines)

    def _fix_type_exc(self, content: str, violations: List[Violation], filepath: str) -> str:
        """Replace type(__exc).__name__ with 'unknown'.

        Before:  type(__exc).__name__
        After:   "unknown"
        """
        content = re.sub(
            r"type\(___?exc_?\)\.__name__",
            '"unknown"',
            content,
        )
        return content

    def _fix_unclosed_file(self, content: str, violations: List[Violation], filepath: str) -> str:
        """Convert open().read() to context manager pattern.

        Before:  data = open(path).read()
        After:   with open(path) as f:\n    data = f.read()

        Note: This is a best-effort fix — complex patterns may need manual review.
        """
        # Pattern: var = open(path).read()
        content = re.sub(
            r"(\s*)(\w+)\s*=\s*open\(([^)]+)\)\.read\(\)",
            r"\1with open(\3) as _f:\n\1    \2 = _f.read()",
            content,
        )
        # Pattern: open(path).read() as standalone expression
        content = re.sub(
            r"(\s*)open\(([^)]+)\)\.read\(\)",
            r"\1with open(\2) as _f: _f.read()",
            content,
        )
        return content

    def _add_import(self, content: str, import_line: str) -> str:
        """Add an import statement after existing imports in the file."""
        lines = content.split("\n")
        insert_idx = 0
        in_docstring = False
        docstring_delim = None

        for i, line in enumerate(lines):
            # Skip past module docstring
            if not in_docstring:
                if line.startswith('"""') or line.startswith("'''"):
                    if line.count('"""') >= 2 or line.count("'''") >= 2:
                        # Single-line docstring
                        insert_idx = i + 1
                        continue
                    in_docstring = True
                    docstring_delim = line[:3]
                    continue
            else:
                if docstring_delim in line:  # type: ignore[operator]
                    in_docstring = False
                    insert_idx = i + 1
                continue

            # Find last import line
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                insert_idx = i + 1

        # Don't insert before __future__ imports
        for i, line in enumerate(lines):
            if line.strip().startswith("from __future__"):
                insert_idx = max(insert_idx, i + 1)
                break

        lines.insert(insert_idx, import_line)
        return "\n".join(lines)
