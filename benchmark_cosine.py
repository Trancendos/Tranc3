import math
import random
import time
from typing import List


def _cosine_original(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _cosine_optimized(a: List[float], b: List[float]) -> float:
    # Optimized implementation using a single explicit loop
    if not a or not b:
        return 0.0

    dot = 0.0
    norm_a_sq = 0.0
    norm_b_sq = 0.0

    # Process paired elements
    for x, y in zip(a, b):
        dot += x * y
        norm_a_sq += x * x
        norm_b_sq += y * y

    # Handle remaining elements if vectors have different lengths
    if len(a) > len(b):
        for i in range(len(b), len(a)):
            norm_a_sq += a[i] * a[i]
    elif len(b) > len(a):
        for i in range(len(a), len(b)):
            norm_b_sq += b[i] * b[i]

    if norm_a_sq == 0.0 or norm_b_sq == 0.0:
        return 0.0

    return dot / math.sqrt(norm_a_sq * norm_b_sq)


# Test correctness
a = [1.0, 2.0, 3.0, 4.0, 5.0]
b = [1.0, 2.0, 3.0]

print(
    f"Correctness test (unequal len): Orig={_cosine_original(a, b)}, Opt={_cosine_optimized(a, b)}"
)

a2 = [1.0, 2.0, 3.0]
b2 = [2.0, 3.0, 4.0]
print(
    f"Correctness test (equal len): Orig={_cosine_original(a2, b2)}, Opt={_cosine_optimized(a2, b2)}"
)

# Benchmark
a_large = [random.random() for _ in range(1536)]
b_large = [random.random() for _ in range(1536)]

n_iter = 10000

t0 = time.time()
for _ in range(n_iter):
    _cosine_original(a_large, b_large)
t1 = time.time()
orig_time = t1 - t0

t0 = time.time()
for _ in range(n_iter):
    _cosine_optimized(a_large, b_large)
t1 = time.time()
opt_time = t1 - t0

print(f"\nOriginal time for {n_iter} iterations: {orig_time:.4f}s")
print(f"Optimized time for {n_iter} iterations: {opt_time:.4f}s")
print(f"Speedup: {orig_time / opt_time:.2f}x")
