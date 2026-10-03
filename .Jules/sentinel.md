## 2024-10-04 - [Python Sandbox Escape via getattr]
**Vulnerability:** The Python sandbox execution tool (`execute_code` in `src/mcp/tools.py`) allowed `getattr`, `dir`, and `type` in its `_SAFE_BUILTINS` list.
**Learning:** Even simple functions like `getattr` can be chained in Python (e.g., `getattr(obj, "__class__")`) to bypass static string checks and escape restricted execution environments, leading to Arbitrary Code Execution (ACE).
**Prevention:** Never include `getattr`, `type`, or `dir` in safe allowlists for dynamically evaluated or executed Python code (like `__builtins__`).
