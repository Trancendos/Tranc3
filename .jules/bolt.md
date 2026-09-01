## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** In pure Python (when `numpy` is unavailable), calculating dot product and vector norms in three separate `sum(...)` generator expressions requires three passes over the vector and three generator overheads. Doing it in a single loop (`for x, y in zip(a, b)`) is 30%+ faster.
**Action:** When calculating vector similarity in pure Python, use a single loop to calculate dot product and norms simultaneously instead of multiple generator expressions.
## 2024-05-26 - [Fast dot product]
**Learning:** `sum(map(operator.mul, a, b))` is ~1.3-1.6x faster than `sum(x * y for x, y in zip(a, b))` for pure Python dot products.
**Action:** Use `sum(map(operator.mul, a, b))` for vector dot products in Python code without numpy.
## 2023-10-27 - [Optimize Vector Math]
**Learning:** Pure Python performance for vector distance calculations (like dot products) is significantly faster (1.3-1.6x) using `sum(map(operator.mul, a, b))` over standard list comprehensions/generator expressions because it pushes iteration and multiplication to C.
**Action:** Always prefer `map` with `operator` functions instead of explicit Python loops/generators for repetitive numerical/vector operations in pure Python.
