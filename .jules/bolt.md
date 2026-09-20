## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** In pure Python (when `numpy` is unavailable), calculating dot product and vector norms in three separate `sum(...)` generator expressions requires three passes over the vector and three generator overheads. Doing it in a single loop (`for x, y in zip(a, b)`) is 30%+ faster.
**Action:** When calculating vector similarity in pure Python, use a single loop to calculate dot product and norms simultaneously instead of multiple generator expressions.
## 2024-05-26 - [Fast dot product]
**Learning:** `sum(map(operator.mul, a, b))` is ~1.3-1.6x faster than `sum(x * y for x, y in zip(a, b))` for pure Python dot products.
**Action:** Use `sum(map(operator.mul, a, b))` for vector dot products in Python code without numpy.
## 2024-05-27 - [Fast Mean Squared Error Optimization]
**Learning:** `sum(map(operator.mul, diffs, diffs))` after `diffs = list(map(operator.sub, a, b))` is ~30% faster than `sum((p - t) ** 2 for p, t in zip(a, b))` for computing squared errors in pure Python due to eliminating generator expression overhead.
**Action:** When calculating sum of squared differences or MSE in pure Python without `numpy`, use `map(operator.sub, ...)` combined with `sum(map(operator.mul, ...))` instead of generator expressions with `zip` and `**2`.
## 2024-05-27 - [Fast OLS Regression Optimization]
**Learning:** Calculating OLS regressions in Python using multiple `sum()` generator expressions over sequences requires multiple O(N) passes. Replacing them with a single loop maintaining accumulator variables (for sums of y, xy, y^2) and evaluating algebraic equations for sum-of-squares (`ss_xx` and `ss_res`) can yield a 3-5x execution speedup.
**Action:** When calculating statistics or linear regressions iteratively without numpy, use a single accumulator loop rather than iterating with multiple list-comprehensions or generators, while utilizing math equations to derive required components (like `ss_xx = sum(x^2) - n * x_mean^2`).
