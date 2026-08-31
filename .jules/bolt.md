## 2023-10-27 - [Optimize Vector Math]
**Learning:** Pure Python performance for vector distance calculations (like dot products) is significantly faster (1.3-1.6x) using `sum(map(operator.mul, a, b))` over standard list comprehensions/generator expressions because it pushes iteration and multiplication to C.
**Action:** Always prefer `map` with `operator` functions instead of explicit Python loops/generators for repetitive numerical/vector operations in pure Python.
## 2023-10-27 - [Optimize Vector Math]
**Learning:** Pure Python performance for vector distance calculations (like dot products) is significantly faster (1.3-1.6x) using `sum(map(operator.mul, a, b))` over standard list comprehensions/generator expressions because it pushes iteration and multiplication to C.
**Action:** Always prefer `map` with `operator` functions instead of explicit Python loops/generators for repetitive numerical/vector operations in pure Python.
