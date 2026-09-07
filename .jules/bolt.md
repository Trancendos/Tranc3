## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** In pure Python (when `numpy` is unavailable), calculating dot product and vector norms in three separate `sum(...)` generator expressions requires three passes over the vector and three generator overheads. Doing it in a single loop (`for x, y in zip(a, b)`) is 30%+ faster.
**Action:** When calculating vector similarity in pure Python, use a single loop to calculate dot product and norms simultaneously instead of multiple generator expressions.
## 2024-05-26 - [Fast dot product]
**Learning:** `sum(map(operator.mul, a, b))` is ~1.3-1.6x faster than `sum(x * y for x, y in zip(a, b))` for pure Python dot products.
**Action:** Use `sum(map(operator.mul, a, b))` for vector dot products in Python code without numpy.
## 2025-02-18 - Multi-Metric Python Loop Optimization
**Learning:** While `sum(map(operator.mul, a, b))` is ~1.3-1.6x faster for isolated dot products because it executes in C, it's inefficient when computing multi-metric values like cosine similarity (which needs dot product + two norms). Using a single `for x, y in zip(a, b)` loop to calculate all metrics simultaneously is ~30% faster than multiple `sum()` generator passes.
**Action:** Always prefer a single `zip()` loop over multiple C-optimized map generators when calculating multiple related metrics (like dot product + norms) simultaneously in pure Python to minimize iteration overhead.
