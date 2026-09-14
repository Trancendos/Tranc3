## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** In pure Python (when `numpy` is unavailable), replacing generator expressions like `sum(x * x for x in v)` with `sum(map(operator.mul, v, v))` pushes both iteration and multiplication into optimized C code, eliminating bytecode evaluation overhead and generator yield time. While a single loop (`for x, y in zip(a, b)`) has cache locality benefits by calculating dot product and norms together, using separate `map(operator.mul, ...)` calls prioritizes eliminating Python interpreter overhead over cache locality, achieving 30%+ performance improvement.
**Action:** When calculating vector similarity in pure Python, use `sum(map(operator.mul, a, b))` for dot products and `sum(map(operator.mul, v, v))` for squared norms. This pattern has been applied across vector_plan_cache.py, hyperdimensional_lattice.py, transcendent_fusion.py, attention_router.py, and enhanced_registry.py.
## 2024-05-26 - [Fast dot product]
**Learning:** `sum(map(operator.mul, a, b))` is ~1.3-1.6x faster than `sum(x * y for x, y in zip(a, b))` for pure Python dot products.
**Action:** Use `sum(map(operator.mul, a, b))` for vector dot products in Python code without numpy.
## 2024-05-27 - [Fast Mean Squared Error Optimization]
**Learning:** `sum(map(operator.mul, diffs, diffs))` after `diffs = list(map(operator.sub, a, b))` is ~30% faster than `sum((p - t) ** 2 for p, t in zip(a, b))` for computing squared errors in pure Python due to eliminating generator expression overhead.
**Action:** When calculating sum of squared differences or MSE in pure Python without `numpy`, use `map(operator.sub, ...)` combined with `sum(map(operator.mul, ...))` instead of generator expressions with `zip` and `**2`.
