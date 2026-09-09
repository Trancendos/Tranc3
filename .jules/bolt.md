## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** In pure Python (when `numpy` is unavailable), calculating dot product and vector norms in three separate `sum(...)` generator expressions requires three passes over the vector and three generator overheads. The current implementation uses three separate `sum(map(operator.mul, ...))` passes: one for the dot product, and one each for norm_a_sq and norm_b_sq. Using `operator.mul` moves the loop execution to C for better performance (~30% faster). The return statement is optimized to compute `sqrt(norm_a_sq * norm_b_sq)` once instead of two separate square roots.
**Action:** When calculating vector similarity in pure Python, use `sum(map(operator.mul, ...))` for dot products and norm calculations to leverage C-level execution. Compute the square root of the product of squared norms rather than computing two separate square roots.
## 2024-05-26 - [Fast dot product]
**Learning:** `sum(map(operator.mul, a, b))` is ~1.3-1.6x faster than `sum(x * y for x, y in zip(a, b))` for pure Python dot products.
**Action:** Use `sum(map(operator.mul, a, b))` for vector dot products in Python code without numpy.
