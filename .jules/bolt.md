## 2024-05-26 - [Python Cosine Similarity Optimizaton]
**Learning:** In pure Python (when `numpy` is unavailable), calculating dot product and vector norms in three separate `sum(...)` generator expressions requires three passes over the vector and three generator overheads. Doing it in a single loop (`for x, y in zip(a, b)`) is 30%+ faster.
**Action:** When calculating vector similarity in pure Python, use a single loop to calculate dot product and norms simultaneously instead of multiple generator expressions.
