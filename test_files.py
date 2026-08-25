def _cosine_opt(a, b):
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

    import math
    return dot / math.sqrt(norm_a_sq * norm_b_sq)
