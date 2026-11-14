## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** In pure Python (when `numpy` is unavailable), calculating dot product and vector norms in three separate `sum(...)` generator expressions requires three passes over the vector and three generator overheads. Doing it in a single loop (`for x, y in zip(a, b)`) is 30%+ faster.
**Action:** When calculating vector similarity in pure Python, use a single loop to calculate dot product and norms simultaneously instead of multiple generator expressions.
## 2024-05-26 - [Fast dot product]
**Learning:** `sum(map(operator.mul, a, b))` is ~1.3-1.6x faster than `sum(x * y for x, y in zip(a, b))` for pure Python dot products.
**Action:** Use `sum(map(operator.mul, a, b))` for vector dot products in Python code without numpy.
## 2024-05-27 - [Fast Mean Squared Error Optimization]
**Learning:** `sum(map(operator.mul, diffs, diffs))` after `diffs = list(map(operator.sub, a, b))` is ~30% faster than `sum((p - t) ** 2 for p, t in zip(a, b))` for computing squared errors in pure Python due to eliminating generator expression overhead.
**Action:** When calculating sum of squared differences or MSE in pure Python without `numpy`, use `map(operator.sub, ...)` combined with `sum(map(operator.mul, ...))` instead of generator expressions with `zip` and `**2`.
## 2024-05-18 - Avoid pure Python loops for multiple-pass optimizations
**Learning:** Fusing multi-pass iterative calculations into a single `for` loop in CPython (e.g., computing a dot product and two norms at the same time to avoid multiple iterations) can actually be *slower* than running multiple separate C-optimized iterations (like `sum(map(operator.mul, ...))`). The interpreter overhead for each iteration in Python is greater than the cost of iterating over the list multiple times in C.
**Action:** When trying to speed up numeric calculations in pure Python, prioritize C-level primitives (like `sum` + `map` + `operator.mul`) for each stage of the calculation, rather than writing a single manual Python loop that tries to compute everything at once.
## 2024-05-27 - [Fast Euclidean and Manhattan Distance Optimization]
**Learning:** `list(map(operator.sub, a, b))` combined with `sum(map(operator.mul, diff, diff))` is ~30% faster for Euclidean distance, and `sum(map(abs, map(operator.sub, a, b)))` is ~28% faster for Manhattan distance compared to pure Python generator expressions with indexing. For multiple operations like `MSE`, materializing the `map` into a `list` is required to prevent iterator exhaustion.
**Action:** When calculating Euclidean or Manhattan distances in pure Python without `numpy`, use `map` with `operator.sub`, `operator.mul`, and `abs` instead of index-based generator comprehensions.
## 2024-05-28 - [Fast Tensor Dot Product for SNNs]
**Learning:** `sum(map(operator.mul, row, inputs))` combined with an inline ternary conditional `current if current > 0.0 else 0.0` is ~2-3x faster than a generator comprehension like `sum(int(w) * x for w, x in zip(row, inputs))` paired with `max(0.0, current)` in pure Python hot loops (like INT8 SNN layers). The speedup stems from offloading iteration and multiplication to C and avoiding Python function-call overhead (`max()`).
**Action:** When implementing pure Python fallback for mathematically intensive tensor or array operations, avoid generator expressions and Python-level function calls (`max`, `min`, `abs` inside loops). Use `map` with the `operator` module and inline ternary operators instead.
