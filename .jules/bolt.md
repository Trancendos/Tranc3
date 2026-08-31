## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** In pure Python (when `numpy` is unavailable), calculating dot product and vector norms in three separate `sum(...)` generator expressions requires three passes over the vector and three generator overheads. Doing it in a single loop (`for x, y in zip(a, b)`) is 30%+ faster.
**Action:** When calculating vector similarity in pure Python, use a single loop to calculate dot product and norms simultaneously instead of multiple generator expressions.
## 2024-05-26 - [Fast dot product]
**Learning:** `sum(map(operator.mul, a, b))` is ~1.3-1.6x faster than `sum(x * y for x, y in zip(a, b))` for pure Python dot products.
**Action:** Use `sum(map(operator.mul, a, b))` for vector dot products in Python code without numpy.
## 2024-08-28 - Fast pure Python vector comparisons
**Learning:** In pure Python components (like `HyperdimensionalVectorOps`) that perform repeated mathematical operations over arrays without NumPy, using `sum(map(operator.mul, a, b))` or `sum(map(operator.eq, a, b))` leverages C-level loops and yields ~1.3-1.6x faster execution than explicit generator expressions like `sum(a[i] * b[i] for i in range(len(a)))`.
**Action:** Always favor `map(operator...)` pipelines or built-in zip comprehensions without explicit index lookup when implementing pure Python math operations across arrays to squeeze out free performance gains.
