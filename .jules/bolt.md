## 2024-05-26 - [Python Cosine Similarity Optimization]
**Learning:** In pure Python (when `numpy` is unavailable), calculating dot product and vector norms in three separate `sum(...)` generator expressions requires three passes over the vector and three generator overheads. Doing it in a single loop (`for x, y in zip(a, b)`) is 30%+ faster.
**Action:** When calculating vector similarity in pure Python, use a single loop to calculate dot product and norms simultaneously instead of multiple generator expressions.
## 2024-05-26 - [Fast dot product]
**Learning:** For cosine similarity calculations in pure Python, the overhead of separate generator passes (`sum(map(operator.mul, ...))` for dot product, `math.sqrt(sum(x*x...))` for each norm) adds up. A single consolidated loop computing all metrics simultaneously is ~30% faster.
**Action:** For cosine similarity in pure Python, use a single loop:
```python
dot = norm_a_sq = norm_b_sq = 0.0
for x, y in zip(a, b):
    dot += x * y
    norm_a_sq += x * x
    norm_b_sq += y * y
return dot / math.sqrt(norm_a_sq * norm_b_sq)
```
