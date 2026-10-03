## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** In pure Python (when `numpy` is unavailable), calculating dot product and vector norms in three separate `sum(...)` generator expressions requires three passes over the vector and three generator overheads. Doing it in a single loop (`for x, y in zip(a, b)`) is 30%+ faster.
**Action:** When calculating vector similarity in pure Python, use a single loop to calculate dot product and norms simultaneously instead of multiple generator expressions.
## 2024-05-26 - [Fast dot product]
**Learning:** `sum(map(operator.mul, a, b))` is ~1.3-1.6x faster than `sum(x * y for x, y in zip(a, b))` for pure Python dot products.
**Action:** Use `sum(map(operator.mul, a, b))` for vector dot products in Python code without numpy.
## 2024-05-27 - [Fast Mean Squared Error Optimization]
**Learning:** `sum(map(operator.mul, diffs, diffs))` after `diffs = list(map(operator.sub, a, b))` is ~30% faster than `sum((p - t) ** 2 for p, t in zip(a, b))` for computing squared errors in pure Python due to eliminating generator expression overhead.
**Action:** When calculating sum of squared differences or MSE in pure Python without `numpy`, use `map(operator.sub, ...)` combined with `sum(map(operator.mul, ...))` instead of generator expressions with `zip` and `**2`.
## 2024-05-28 - [Cosine Similarity Optimization Edge Case]
**Learning:** When refactoring multiple generator `sum()` functions into a single `zip()` loop to calculate dot products and magnitudes simultaneously, be aware of `zip`'s inherent behavior of truncating to the shortest list. Although passing unequal length vectors to cosine similarity is invalid mathematically, replacing independent magnitude calculations with a zipped iteration truncates the magnitude if vectors are unequal, altering edge-case behavior.
**Action:** Be mindful of list length assumptions when fusing independent loops into a single `zip()` iteration for performance. A purely C-optimized `math.sqrt(sum(map(operator.mul, a, a)))` avoids this truncation entirely while still being highly performant.
