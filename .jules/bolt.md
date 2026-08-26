## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** In pure Python (when `numpy` is unavailable), calculating dot product and vector norms in three separate `sum(...)` generator expressions requires three passes over the vector and three generator overheads. Doing it in a single loop (`for x, y in zip(a, b)`) is 30%+ faster.
**Action:** When calculating vector similarity in pure Python, use a single loop to calculate dot product and norms simultaneously instead of multiple generator expressions.
## 2025-05-19 - Vector Dot Product Optimization
**Learning:** In pure Python (without NumPy), calculating vector distance metrics or dot products using `sum(map(operator.mul, a, b))` is significantly faster (~1.3-1.6x) than using manual loops or generator expressions like `sum(x * y for x, y in zip(a, b))`. The map operation executes in C and automatically terminates on the shortest sequence (acting like `zip`).
**Action:** Use `sum(map(operator.mul, a, b))` for dot products and vector multiplications across the codebase to maximize C-extension speedup in critical paths.
