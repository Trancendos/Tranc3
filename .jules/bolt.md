## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** For dot products, use `sum(map(operator.mul, a, b))` (~1.3-1.6x faster than generator expressions). For vector norms, use `sum(map(operator.mul, v, v))` instead of `sum(x * x for x in v)` for the same bytecode overhead reduction. The `map(operator.mul)` pattern pushes both iteration and multiplication to C code, avoiding Python bytecode overhead in tight loops.
**Action:** Use `sum(map(operator.mul, a, b))` for dot products and `sum(map(operator.mul, v, v))` for norm calculations (e.g., `math.sqrt(sum(map(operator.mul, v, v)))`) in pure Python vector operations.

