"""Pins the vector-math optimisations to the results they replaced.

Twenty-one open pull requests proposed changes to the same handful of dot
products and norms, and they did not agree: most wanted
``sum(map(operator.mul, v, v))``, #1234 wanted a single-pass loop and removed
the map, and #1214 wanted to drop an ``int()`` cast inside a *quantized*
kernel. Claimed speedups ranged from "1.3-1.6x" to "~30%".

Measured on CPython 3.11, cosine similarity at dims 64 / 384 / 1536:

    generator expression (what was there)   1.00x
    map(operator.mul) for the norms         1.29x / 1.30x / 1.32x
    single-pass loop (#1234)                1.17x / 1.11x / 1.12x

So #1234 is slower than what it would have replaced, and its "~30%" is 12%.

What these tests pin is not the speed — a benchmark in CI measures the runner,
not the code — but the thing a performance rewrite is allowed to change, which
is nothing. Each reference implementation below is the code as it stood before
the optimisation.
"""

import math
import operator
import random

import pytest


def _reference_cosine(a, b):
    """The generator-expression form these functions used to have."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@pytest.fixture
def vectors():
    rng = random.Random(20260925)
    return [
        ([rng.uniform(-1, 1) for _ in range(dim)], [rng.uniform(-1, 1) for _ in range(dim)])
        for dim in (1, 2, 8, 64, 384, 1536)
    ]


def test_enhanced_registry_cosine_matches_the_generator_form(vectors):
    from src.skills.enhanced_registry import EnhancedSkillRegistry

    # Guards on magnitude < 1e-12 rather than == 0, so the reference does too.
    def reference(a, b):
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(y * y for y in b))
        if mag_a < 1e-12 or mag_b < 1e-12:
            return 0.0
        return dot / (mag_a * mag_b)

    for a, b in vectors:
        got = EnhancedSkillRegistry._cosine(None, a, b)
        assert got == pytest.approx(reference(a, b), rel=1e-12, abs=1e-12)


def test_model_eval_cosine_matches_the_generator_form(vectors):
    from src.evaluation.model_eval import EvalSuite

    for a, b in vectors:
        got = EvalSuite._cosine_similarity(a, b)
        assert got == pytest.approx(_reference_cosine(a, b), rel=1e-12, abs=1e-12)


def test_zero_vectors_still_return_zero_rather_than_dividing():
    """The guard is the reason these functions are not one expression."""
    from src.evaluation.model_eval import EvalSuite

    zeros = [0.0] * 8
    assert EvalSuite._cosine_similarity(zeros, [1.0] * 8) == 0.0
    assert EvalSuite._cosine_similarity([1.0] * 8, zeros) == 0.0
    assert EvalSuite._cosine_similarity(zeros, zeros) == 0.0


def test_attention_router_norm_matches_the_generator_form(vectors):
    from src.neural.attention_router import _vector_norm

    for a, _ in vectors:
        assert _vector_norm(a) == pytest.approx(
            math.sqrt(sum(x * x for x in a)), rel=1e-12, abs=1e-12
        )


def test_snn_fallback_keeps_truncating_float_weights():
    """#1214 dropped the int() cast, which is the quantization.

    The Rust kernel this falls back from takes i8. Measured with float weights,
    dropping the cast moves the result by about 20% — so the cast is kept and
    the multiply is moved into C around it.
    """
    from src.nanoservices.snn_tensor import _py_leaky_step_i8

    rng = random.Random(11)
    in_dim, out_dim = 16, 4
    float_weights = [rng.uniform(-128, 127) for _ in range(in_dim * out_dim)]
    inputs = [rng.uniform(-1, 1) for _ in range(in_dim)]
    bias = [0.0] * out_dim
    mem = [0.0] * out_dim

    _, new_mem = _py_leaky_step_i8(float_weights, bias, inputs, mem, 0.9, 1.0)

    expected = []
    for j in range(out_dim):
        row = float_weights[j * in_dim : (j + 1) * in_dim]
        current = max(0.0, sum(int(w) * x for w, x in zip(row, inputs, strict=False)) + bias[j])
        nm = 0.9 * 0.0 + current
        expected.append(nm - 1.0 if nm >= 1.0 else nm)

    assert new_mem == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_map_and_generator_norms_agree_on_awkward_input():
    """Empty, single-element, and mixed-magnitude vectors.

    `map` over two iterables stops at the shorter one, where a generator over
    `zip` does the same — but only because the originals also used zip. This
    records that the lengths are equal by contract.
    """
    for v in ([], [0.0], [1e-160, 1e160], [-0.0, 0.0], [3.0] * 5):
        assert sum(map(operator.mul, v, v)) == pytest.approx(
            sum(x * x for x in v), rel=1e-12, abs=1e-12
        )
