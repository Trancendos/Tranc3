import time
import math
import random

def fusion_attention_orig(q_slice, k_slice):
    dot = sum(a * b for a, b in zip(q_slice, k_slice))
    return dot

def fusion_attention_opt(q_slice, k_slice):
    dot = 0.0
    for a, b in zip(q_slice, k_slice):
        dot += a * b
    return dot

q = [random.random() for _ in range(128)]
k = [random.random() for _ in range(128)]

n = 50000
t0 = time.time()
for _ in range(n):
    fusion_attention_orig(q, k)
orig_time = time.time() - t0

t0 = time.time()
for _ in range(n):
    fusion_attention_opt(q, k)
opt_time = time.time() - t0

print(f"Orig: {orig_time:.4f}s")
print(f"Opt:  {opt_time:.4f}s")
print(f"Speedup: {orig_time / opt_time:.2f}x")
