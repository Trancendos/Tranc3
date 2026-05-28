"""
AeonMind Adaptive Meta-Learning — Python Implementation.

Implements L-BFGS (Limited-memory Broyden–Fletcher–Goldfarb–Shanno)
two-loop recursion for Hessian approximation with momentum, gradient
clipping, and adaptive learning rate scheduling.
"""

from __future__ import annotations

import math  # noqa: F401
from dataclasses import dataclass, field
from typing import Callable, List, Optional  # noqa: UP035

import numpy as np


@dataclass
class AdaptiveConfig:
    """Configuration for the AdaptiveMetaLearner."""
    learning_rate: float = 0.01
    memory_size: int = 10
    max_iterations: int = 1000
    tolerance: float = 1e-8
    gradient_clip: float = 1.0
    momentum: float = 0.9
    beta1: float = 0.9
    beta2: float = 0.999
    epsilon: float = 1e-8
    decay_rate: float = 0.95
    warmup_steps: int = 100
    use_lbfgs: bool = True


@dataclass
class LbfgsEntry:
    """Storage entry for L-BFGS two-loop recursion."""
    s: np.ndarray  # parameter difference
    y: np.ndarray  # gradient difference
    rho: float     # 1 / (y^T s)


@dataclass
class AdaptiveStep:
    """Result of a single optimization step."""
    iteration: int
    loss: float
    gradient_norm: float
    learning_rate: float
    step_size: float


@dataclass
class AdaptiveSummary:
    """Summary of the adaptive optimization process."""
    total_steps: int
    final_loss: float
    final_gradient_norm: float
    initial_loss: float
    best_loss: float
    best_iteration: int
    converged: bool
    learning_rate_history: List[float] = field(default_factory=list)  # noqa: UP006
    loss_history: List[float] = field(default_factory=list)  # noqa: UP006


class AdaptiveMetaLearner:
    """Adaptive Meta-Learner with L-BFGS two-loop recursion.

    Uses limited-memory BFGS for Hessian approximation, combined
    with momentum-based gradient descent and adaptive learning rate
    scheduling for efficient optimization.
    """

    def __init__(self, n_params: int, config: Optional[AdaptiveConfig] = None):  # noqa: UP045
        self.n_params = n_params
        self.config = config or AdaptiveConfig()
        self.parameters = np.random.randn(n_params) * 0.01
        self._velocity = np.zeros(n_params)
        self._moment_estimates_m = np.zeros(n_params)
        self._moment_estimates_v = np.zeros(n_params)
        self._lbfgs_history: List[LbfgsEntry] = []  # noqa: UP006
        self._prev_gradient: Optional[np.ndarray] = None  # noqa: UP045
        self._step_count = 0
        self._best_loss = float("inf")
        self._best_params: Optional[np.ndarray] = None  # noqa: UP045
        self._best_iteration = 0
        self._initial_loss: Optional[float] = None  # noqa: UP045
        self._loss_history: List[float] = []  # noqa: UP006
        self._lr_history: List[float] = []  # noqa: UP006

    @classmethod
    def with_parameters(cls, parameters: np.ndarray, config: Optional[AdaptiveConfig] = None) -> AdaptiveMetaLearner:  # noqa: UP045
        """Create a learner initialized with specific parameters."""
        learner = cls(len(parameters), config)
        learner.parameters = parameters.copy()
        return learner

    def lbfgs_direction(self, gradient: np.ndarray) -> np.ndarray:
        """Compute search direction using L-BFGS two-loop recursion.

        The two-loop recursion approximates the inverse Hessian-vector
        product without storing the full Hessian matrix.
        """
        direction = -gradient.copy()
        q = direction.copy()

        # First loop: traverse from most recent to oldest
        alphas = []
        for entry in reversed(self._lbfgs_history):
            alpha = entry.rho * np.dot(entry.s, q)
            alphas.append(alpha)
            q = q - alpha * entry.y

        # Apply initial Hessian approximation (scaled identity)
        if self._lbfgs_history:
            latest = self._lbfgs_history[-1]
            gamma = np.dot(latest.s, latest.y) / (np.dot(latest.y, latest.y) + 1e-10)
            q = gamma * q

        # Second loop: traverse from oldest to most recent
        for entry, alpha in zip(self._lbfgs_history, reversed(alphas)):
            beta = entry.rho * np.dot(entry.y, q)
            q = q + entry.s * (alpha - beta)

        return q

    def _update_lbfgs_history(self, s: np.ndarray, y: np.ndarray) -> None:
        """Update L-BFGS history with new curvature pair."""
        ys = np.dot(y, s)
        if ys > 1e-10:
            rho = 1.0 / ys
            self._lbfgs_history.append(LbfgsEntry(s=s, y=y, rho=rho))
            if len(self._lbfgs_history) > self.config.memory_size:
                self._lbfgs_history.pop(0)

    def step(self, gradient: np.ndarray) -> AdaptiveStep:
        """Perform a single optimization step.

        Combines L-BFGS direction with momentum and adaptive learning rate.
        """
        # Clip gradient
        grad_norm = np.linalg.norm(gradient)
        if grad_norm > self.config.gradient_clip:
            gradient = gradient * (self.config.gradient_clip / grad_norm)

        # Compute direction
        if self.config.use_lbfgs and len(self._lbfgs_history) > 0:
            direction = self.lbfgs_direction(gradient)
        else:
            direction = -gradient

        # Update momentum estimates (Adam-style)
        self._moment_estimates_m = (
            self.config.beta1 * self._moment_estimates_m
            + (1 - self.config.beta1) * direction
        )
        self._moment_estimates_v = (
            self.config.beta2 * self._moment_estimates_v
            + (1 - self.config.beta2) * direction ** 2
        )

        # Bias correction
        m_hat = self._moment_estimates_m / (1 - self.config.beta1 ** (self._step_count + 1))
        v_hat = self._moment_estimates_v / (1 - self.config.beta2 ** (self._step_count + 1))

        # Compute update
        lr = self._current_learning_rate()
        update = lr * m_hat / (np.sqrt(v_hat) + self.config.epsilon)

        # Update L-BFGS history
        if self._prev_gradient is not None:
            s = -update  # parameter change
            y = gradient - self._prev_gradient  # gradient change
            self._update_lbfgs_history(s, y)

        # Apply velocity with momentum
        self._velocity = self.config.momentum * self._velocity + update
        self.parameters = self.parameters - self._velocity

        self._prev_gradient = gradient.copy()
        self._step_count += 1

        return AdaptiveStep(
            iteration=self._step_count,
            loss=0.0,  # caller should compute
            gradient_norm=float(np.linalg.norm(gradient)),
            learning_rate=lr,
            step_size=float(np.linalg.norm(update)),
        )

    def optimize(
        self,
        loss_fn: Callable[[np.ndarray], float],
        grad_fn: Callable[[np.ndarray], np.ndarray],
        callback: Optional[Callable[[int, float, float], None]] = None,  # noqa: UP045
    ) -> AdaptiveSummary:
        """Run full optimization loop."""
        self._initial_loss = loss_fn(self.parameters)
        self._best_loss = self._initial_loss

        for i in range(self.config.max_iterations):
            loss = loss_fn(self.parameters)
            gradient = grad_fn(self.parameters)

            step_result = self.step(gradient)
            step_result.loss = loss

            self._loss_history.append(loss)
            self._lr_history.append(step_result.learning_rate)

            if loss < self._best_loss:
                self._best_loss = loss
                self._best_params = self.parameters.copy()
                self._best_iteration = i

            if callback:
                callback(i, loss, step_result.gradient_norm)

            if step_result.gradient_norm < self.config.tolerance:
                break

        return AdaptiveSummary(
            total_steps=self._step_count,
            final_loss=self._loss_history[-1] if self._loss_history else 0.0,
            final_gradient_norm=step_result.gradient_norm if 'step_result' in dir() else 0.0,
            initial_loss=self._initial_loss or 0.0,
            best_loss=self._best_loss,
            best_iteration=self._best_iteration,
            converged=step_result.gradient_norm < self.config.tolerance if 'step_result' in dir() else False,  # noqa: E501
            learning_rate_history=self._lr_history.copy(),
            loss_history=self._loss_history.copy(),
        )

    def _current_learning_rate(self) -> float:
        """Compute current learning rate with warmup and decay."""
        if self._step_count < self.config.warmup_steps:
            scale = (self._step_count + 1) / self.config.warmup_steps
            return self.config.learning_rate * scale
        return self.config.learning_rate * (self.config.decay_rate ** (self._step_count - self.config.warmup_steps))  # noqa: E501

    def adapt_learning_rate(self, loss: float) -> float:
        """Adapt learning rate based on loss progress."""
        if len(self._loss_history) >= 2:
            recent = self._loss_history[-5:] if len(self._loss_history) >= 5 else self._loss_history
            if len(recent) >= 2 and recent[-1] > recent[-2]:
                return self.config.learning_rate * 0.5
        return self.config.learning_rate

    def parameters_array(self) -> np.ndarray:
        """Return a copy of current parameters."""
        return self.parameters.copy()

    def summary(self) -> AdaptiveSummary:
        """Get summary of the optimization process."""
        return AdaptiveSummary(
            total_steps=self._step_count,
            final_loss=self._loss_history[-1] if self._loss_history else 0.0,
            final_gradient_norm=float(np.linalg.norm(self._prev_gradient)) if self._prev_gradient is not None else 0.0,  # noqa: E501
            initial_loss=self._initial_loss or 0.0,
            best_loss=self._best_loss,
            best_iteration=self._best_iteration,
            converged=False,
            learning_rate_history=self._lr_history.copy(),
            loss_history=self._loss_history.copy(),
        )

    def reset(self) -> None:
        """Reset the learner state."""
        self.parameters = np.random.randn(self.n_params) * 0.01
        self._velocity = np.zeros(self.n_params)
        self._moment_estimates_m = np.zeros(self.n_params)
        self._moment_estimates_v = np.zeros(self.n_params)
        self._lbfgs_history = []
        self._prev_gradient = None
        self._step_count = 0
        self._best_loss = float("inf")
        self._best_params = None
        self._best_iteration = 0
        self._initial_loss = None
        self._loss_history = []
        self._lr_history = []
