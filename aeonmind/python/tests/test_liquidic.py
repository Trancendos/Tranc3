"""
Tests for AeonMind Fluidic-Liquidic Reservoir.
"""

import pytest  # noqa: I001
import numpy as np

from aeonmind.core.fluidic_liquidic import LiquidReservoir, ReservoirConfig, FluidicState


class TestLiquidReservoir:
    """Tests for the LiquidReservoir."""

    def test_reservoir_creation(self):
        reservoir = LiquidReservoir(ReservoirConfig(input_size=5, reservoir_size=50))
        assert reservoir is not None
        assert reservoir.config.reservoir_size == 50

    def test_step(self):
        reservoir = LiquidReservoir(ReservoirConfig(input_size=5, reservoir_size=50))
        input_data = np.random.randn(5)
        state = reservoir.step(input_data)
        assert len(state) == 50

    def test_process_sequence(self):
        reservoir = LiquidReservoir(ReservoirConfig(input_size=5, reservoir_size=50))
        inputs = np.random.randn(10, 5)
        states = reservoir.process_sequence(inputs)
        assert states.shape == (10, 50)

    def test_reset(self):
        reservoir = LiquidReservoir(ReservoirConfig(input_size=5, reservoir_size=50))
        reservoir.step(np.random.randn(5))
        reservoir.reset()
        assert np.allclose(reservoir._state, 0.0)

    def test_warmup(self):
        reservoir = LiquidReservoir(ReservoirConfig(input_size=5, reservoir_size=50))
        reservoir.warmup(10)
        # After warmup, state should be non-zero
        assert not np.allclose(reservoir._state, 0.0)

    def test_get_state_features(self):
        reservoir = LiquidReservoir(ReservoirConfig(input_size=5, reservoir_size=50))
        reservoir.step(np.random.randn(5))
        features = reservoir.get_state_features()
        # State features include reservoir state + 8 fluidic features
        assert len(features) == 50 + 8

    def test_adapt_spectral_radius(self):
        reservoir = LiquidReservoir(ReservoirConfig(input_size=5, reservoir_size=50, spectral_radius=0.5))  # noqa: E501
        reservoir.adapt_spectral_radius(0.9)
        # Spectral radius should be updated
        assert abs(reservoir.config.spectral_radius - 0.9) < 0.1

    def test_fluidic_state(self):
        reservoir = LiquidReservoir(ReservoirConfig(input_size=5, reservoir_size=50))
        reservoir.step(np.random.randn(5))
        fluidic = reservoir.fluidic_state()
        assert isinstance(fluidic, FluidicState)
        assert fluidic.energy > 0

    def test_reservoir_state(self):
        reservoir = LiquidReservoir(ReservoirConfig(input_size=5, reservoir_size=50))
        reservoir.step(np.random.randn(5))
        state = reservoir.reservoir_state()
        assert state.spectral_radius > 0
        assert state.connectivity >= 0


class TestFluidicState:
    """Tests for the FluidicState."""

    def test_fluidic_creation(self):
        state = FluidicState()
        assert state.energy == 1.0
        assert state.coherence == 1.0

    def test_fluidic_update(self):
        state = FluidicState()
        new_data = np.random.randn(8)
        state.update(new_data)
        assert state.timestamp > 0

    def test_fluidic_compress(self):
        state = FluidicState()
        state.update(np.random.randn(8))
        compressed = state.compress()
        assert len(compressed) == 8

    def test_fluidic_decay(self):
        state = FluidicState()
        state.update(np.ones(8) * 5.0)
        old_energy = state.energy
        state.decay(0.5)
        assert state.energy < old_energy
