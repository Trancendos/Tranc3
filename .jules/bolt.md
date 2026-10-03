## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** Measure performance claims. PR #1237 settled 21 competing pull requests with actual benchmarks: `sum(map(operator.mul, v, v))` for norms is 29-32% faster than generator expressions (not the claimed "30%+" for a single-pass loop, which measured only 11-17% faster). Claims without measurements can be misleading.
**Action:** For vector norms in pure Python, use `sum(map(operator.mul, v, v))`. Measure performance changes rather than relying on assumptions.
## 2024-05-26 - [Fast dot product]
**Learning:** `sum(map(operator.mul, a, b))` is ~1.3-1.6x faster than `sum(x * y for x, y in zip(a, b))` for pure Python dot products.
**Action:** Use `sum(map(operator.mul, a, b))` for vector dot products in Python code without numpy.
## 2024-05-27 - [Fast Mean Squared Error Optimization]
**Learning:** `sum(map(operator.mul, diffs, diffs))` after `diffs = list(map(operator.sub, a, b))` is ~30% faster than `sum((p - t) ** 2 for p, t in zip(a, b))` for computing squared errors in pure Python due to eliminating generator expression overhead.
**Action:** When calculating sum of squared differences or MSE in pure Python without `numpy`, use `map(operator.sub, ...)` combined with `sum(map(operator.mul, ...))` instead of generator expressions with `zip` and `**2`.
