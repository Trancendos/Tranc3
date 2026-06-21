"""Echo State Network — reservoir computing for temporal routing intelligence.

Architecture:
  input(u) → reservoir(x) [fixed, random, recurrent] → readout(y) [trained]

Only the readout weights W_out are trained (ridge regression — no backprop).
The reservoir itself is never updated, giving extreme training speed.

Used in Trancendos to predict: which provider will be fastest/available
for the NEXT request, based on the last N request outcomes.
"""

from __future__ import annotations

import logging
import math
import random
from typing import List

logger = logging.getLogger("tranc3.dimensional.reservoir.esn")


class EchoStateNetwork:
    """Minimal ESN with online ridge regression readout.

    Args:
        input_dim: number of input features per timestep
        reservoir_size: number of reservoir neurons (100-500 typical)
        output_dim: number of output predictions
        spectral_radius: controls reservoir dynamics (0.9 = near edge of chaos)
        leaking_rate: neuron leak rate (0.3 = slow dynamics)
        sparsity: fraction of reservoir connections that are zero
        ridge_param: L2 regularisation for readout
    """

    def __init__(
        self,
        input_dim: int = 8,
        reservoir_size: int = 128,
        output_dim: int = 8,
        spectral_radius: float = 0.9,
        leaking_rate: float = 0.3,
        sparsity: float = 0.9,
        ridge_param: float = 1e-6,
    ) -> None:
        self.input_dim = input_dim
        self.N = reservoir_size
        self.output_dim = output_dim
        self.alpha = leaking_rate
        self.ridge = ridge_param

        rng = random.Random(42)

        # Input weights W_in: (N × input_dim), uniform [-1, 1]
        self.W_in = [[rng.uniform(-1, 1) for _ in range(input_dim)] for _ in range(reservoir_size)]

        # Reservoir weights W: (N × N), sparse random
        W_raw = []
        for _ in range(reservoir_size):
            row = []
            for _j in range(reservoir_size):
                if rng.random() > sparsity:
                    row.append(rng.uniform(-1, 1))
                else:
                    row.append(0.0)
            W_raw.append(row)

        # Scale to desired spectral radius
        sr = self._spectral_radius(W_raw)
        scale = spectral_radius / sr if sr > 0 else 1.0
        self.W = [[w * scale for w in row] for row in W_raw]

        # Reservoir state x: (N,)
        self.x: List[float] = [0.0] * reservoir_size

        # Readout weights W_out: (output_dim × N), init zeros
        self.W_out: List[List[float]] = [[0.0] * reservoir_size for _ in range(output_dim)]
        self._trained = False

        # Collected states for batch training
        self._X_buf: List[List[float]] = []
        self._Y_buf: List[List[float]] = []

    def step(self, u: List[float]) -> List[float]:
        """Run one timestep. Returns readout output."""
        # x_new = (1-alpha)*x + alpha*tanh(W_in*u + W*x)
        x_new = [0.0] * self.N
        for i in range(self.N):
            lin = sum(self.W_in[i][j] * u[j] for j in range(self.input_dim))
            lin += sum(self.W[i][j] * self.x[j] for j in range(self.N))
            x_new[i] = (1 - self.alpha) * self.x[i] + self.alpha * math.tanh(lin)
        self.x = x_new
        return self._readout()

    def _readout(self) -> List[float]:
        if not self._trained:
            # Untrained: return uniform distribution
            v = 1.0 / self.output_dim
            return [v] * self.output_dim
        out = []
        for row in self.W_out:
            out.append(sum(row[j] * self.x[j] for j in range(self.N)))
        # Softmax
        mx = max(out)
        exps = [math.exp(v - mx) for v in out]
        s = sum(exps)
        return [e / s for e in exps]

    def collect(self, u: List[float], y_target: List[float]) -> None:
        """Collect (input, target) pair for batch training."""
        self.step(u)
        self._X_buf.append(list(self.x))
        self._Y_buf.append(list(y_target))

    def train(self) -> None:
        """Fit readout via ridge regression: W_out = Y * X^T (X X^T + ridge I)^-1."""
        if len(self._X_buf) < 2:
            return
        X = self._X_buf
        Y = self._Y_buf
        n = len(X)
        N = self.N
        try:
            import numpy as np

            X_np = np.array(X)  # (n, N)
            Y_np = np.array(Y)  # (n, output_dim)
            XtX = X_np.T @ X_np + self.ridge * np.eye(N)
            XtY = X_np.T @ Y_np
            W_out_T = np.linalg.solve(XtX, XtY)  # (N, output_dim)
            self.W_out = W_out_T.T.tolist()
        except ImportError:
            # Pure-Python fallback: diagonal approximation (less accurate for correlated states)
            logger.warning("numpy unavailable — ESN using diagonal ridge approximation")
            XtX = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in range(N)] for i in range(N)]
            for i in range(N):
                XtX[i][i] += self.ridge
            XtX_inv_diag = [1.0 / max(XtX[i][i], 1e-10) for i in range(N)]
            for d in range(self.output_dim):
                for i in range(N):
                    self.W_out[d][i] = sum(Y[k][d] * X[k][i] for k in range(n)) * XtX_inv_diag[i]
        self._trained = True
        self._X_buf.clear()
        self._Y_buf.clear()
        logger.info("ESN readout trained on %d samples", n)

    @staticmethod
    def _spectral_radius(W: List[List[float]]) -> float:
        """Approximate spectral radius via power iteration."""
        n = len(W)
        if n == 0:
            return 1.0
        v = [1.0 / n] * n
        for _ in range(20):
            v_new = [sum(W[i][j] * v[j] for j in range(n)) for i in range(n)]
            norm = math.sqrt(sum(x**2 for x in v_new)) or 1.0
            v = [x / norm for x in v_new]
        # Rayleigh quotient
        Av = [sum(W[i][j] * v[j] for j in range(n)) for i in range(n)]
        return math.sqrt(sum(x**2 for x in Av))
