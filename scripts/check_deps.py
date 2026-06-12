#!/usr/bin/env python3
"""Dependency health check — verifies all optional ML/AI packages are functional.

Run: python scripts/check_deps.py
Exits 0 if all required packages work, 1 if any critical package fails.
"""

from __future__ import annotations

import sys
from typing import Callable

CHECKS: list[tuple[str, str, Callable[[], str]]] = []


def check(name: str, critical: bool = True):
    def decorator(fn: Callable[[], str]) -> Callable[[], str]:
        CHECKS.append((name, "critical" if critical else "optional", fn))
        return fn
    return decorator


@check("torch", critical=True)
def _torch():
    import torch
    x = torch.randn(2, 2) @ torch.randn(2, 2)
    return f"v{torch.__version__} cuda={torch.cuda.is_available()}"


@check("ncps (CfC LNN)", critical=True)
def _ncps():
    import torch
    from ncps.torch import CfC
    from ncps.wirings import AutoNCP
    wiring = AutoNCP(32, 3)
    model = CfC(4, wiring, batch_first=True)
    x = torch.randn(1, 5, 4)
    out, _ = model(x)
    assert out.shape == (1, 5, 3)
    return f"CfC output shape {tuple(out.shape)}"


@check("deap", critical=True)
def _deap():
    from deap import base, creator, tools
    import random
    creator.create("_TestFit", base.Fitness, weights=(-1.0,))
    creator.create("_TestInd", list, fitness=creator.FitnessMin if hasattr(creator, "FitnessMin") else creator._TestFit)
    tb = base.Toolbox()
    tb.register("attr", random.random)
    tb.register("individual", tools.initRepeat, creator._TestInd, tb.attr, n=3)
    tb.register("pop", tools.initRepeat, list, tb.individual)
    pop = tb.pop(n=5)
    return f"population={len(pop)} individuals"


@check("pyswarms", critical=True)
def _pyswarms():
    import pyswarms as ps
    import numpy as np
    opt = ps.single.GlobalBestPSO(
        n_particles=5, dimensions=3,
        options={"c1": 0.5, "c2": 0.3, "w": 0.9}
    )
    cost, pos = opt.optimize(lambda x, **kw: np.sum(x**2, axis=1), iters=5, verbose=False)
    return f"PSO converged cost={cost:.6f}"


@check("PersonalityLNN (integrated)", critical=True)
def _personality_lnn():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from src.personality.lnn import PersonalityLNN, LNNInput, _USING_LNN
    lnn = PersonalityLNN()
    out = lnn.step(LNNInput(0.5, 0.8, 0.3, 0.5))
    mode = "CfC" if _USING_LNN else "EMA"
    return f"shaper={mode} temp_delta={out.temperature_delta:.4f}"


@check("GeneticOptimizer (integrated)", critical=True)
def _genetic_optimizer():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from src.nanoservices.genetic_optimizer.genetic_optimizer import (
        GeneticOptimizer, GeneSpec, Objective, ObjectiveType
    )
    specs = [GeneSpec("lr", 0.0001, 0.1), GeneSpec("batch", 8.0, 128.0)]
    objs = [Objective("latency", ObjectiveType.MINIMIZE)]
    go = GeneticOptimizer(specs, objs)
    return "GeneticOptimizer ready"


def main() -> int:
    width = 36
    print("\n  Tranc3 — ML/AI Dependency Health Check")
    print("  " + "=" * 52)
    failures: list[str] = []
    for name, level, fn in CHECKS:
        try:
            detail = fn()
            status = "PASS"
            marker = "✓"
        except Exception as e:
            detail = str(e)[:60]
            status = "FAIL"
            marker = "✗"
            if level == "critical":
                failures.append(name)
        label = f"{name} [{level}]"
        print(f"  {marker} {label:<{width}} {status}  {detail}")

    print("  " + "=" * 52)
    if failures:
        print(f"\n  FAIL — {len(failures)} critical check(s) failed: {', '.join(failures)}")
        print("  Install: pip install torch ncps deap pyswarms\n")
        return 1
    else:
        print(f"\n  PASS — all {len(CHECKS)} checks passed\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
