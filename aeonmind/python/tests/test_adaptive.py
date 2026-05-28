"""
Tests for AeonMind Adaptive Meta-Learner.
"""

import pytest  # noqa: I001
import numpy as np

from aeonmind.core.adaptive import AdaptiveMetaLearner, AdaptiveConfig


class TestAdaptiveMetaLearner:
    """Tests for the AdaptiveMetaLearner."""

    def test_learner_creation(self):
        learner = AdaptiveMetaLearner(32)
        assert learner.n_params == 32
        assert len(learner.parameters) == 32

    def test_with_parameters(self):
        params = np.ones(16)
        learner = AdaptiveMetaLearner.with_parameters(params)
        assert np.allclose(learner.parameters, 1.0)

    def test_step(self):
        learner = AdaptiveMetaLearner(16, AdaptiveConfig(learning_rate=0.01))
        gradient = np.random.randn(16)
        result = learner.step(gradient)
        assert result.iteration == 1
        assert result.gradient_norm > 0

    def test_gradient_clipping(self):
        config = AdaptiveConfig(gradient_clip=0.1)
        learner = AdaptiveMetaLearner(8, config)
        large_gradient = np.ones(8) * 100.0
        result = learner.step(large_gradient)
        # Gradient should have been clipped
        assert result.gradient_norm <= 0.1 + 1e-6

    def test_optimize_quadratic(self):
        """Test optimization on a simple quadratic function."""
        n = 4
        learner = AdaptiveMetaLearner(n, AdaptiveConfig(
            learning_rate=0.1,
            max_iterations=200,
            tolerance=1e-6,
        ))

        def loss_fn(params):
            return float(np.sum(params ** 2))

        def grad_fn(params):
            return 2.0 * params

        summary = learner.optimize(loss_fn, grad_fn)
        assert summary.best_loss < 1.0  # Should reduce from initial
        assert summary.total_steps > 0

    def test_lbfgs_direction(self):
        learner = AdaptiveMetaLearner(8, AdaptiveConfig(memory_size=5))
        # Populate history by doing a few steps
        for _ in range(3):
            gradient = np.random.randn(8)
            learner.step(gradient)

        gradient = np.random.randn(8)
        direction = learner.lbfgs_direction(gradient)
        assert len(direction) == 8

    def test_summary(self):
        learner = AdaptiveMetaLearner(8)
        summary = learner.summary()
        assert summary.total_steps == 0

    def test_parameters_array(self):
        learner = AdaptiveMetaLearner(8)
        params = learner.parameters_array()
        assert len(params) == 8
        # Should be a copy
        params[0] = 999.0
        assert learner.parameters[0] != 999.0

    def test_reset(self):
        learner = AdaptiveMetaLearner(8)
        gradient = np.random.randn(8)
        learner.step(gradient)
        assert learner._step_count > 0
        learner.reset()
        assert learner._step_count == 0
