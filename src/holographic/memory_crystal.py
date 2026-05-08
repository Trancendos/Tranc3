# src/holographic/memory_crystal.py

import numpy as np
import torch
from typing import Dict, List

try:
    from scipy.fft import fftn, ifftn
except ImportError:
    from numpy.fft import fftn, ifftn  # type: ignore[assignment]

class HolographicMemoryCrystal:
    """
    6D holographic data storage using quantum-optical crystals
    Stores entire experiences as holographic interference patterns
    """
    
    def __init__(self, dimensions=(100, 100, 100, 50, 50, 50)):
        """
        6D memory structure:
        - 3D spatial (x, y, z)
        - 1D temporal (t)
        - 1D frequency/energy (f)
        - 1D consciousness/quantum phase (φ)
        """
        self.dimensions = dimensions
        self.crystal = np.zeros(dimensions, dtype=np.complex128)
        self.reference_beam = self._generate_reference()
        self.coherence_length = 1e12  # Picoseconds
        
    def _generate_reference(self):
        """Generate coherent reference beam for holographic encoding"""
        dims = self.dimensions
        ref = np.ones(dims, dtype=np.complex128)
        # Add phase gradients for each dimension
        for i, dim_size in enumerate(dims):
            axis_phases = np.linspace(0, 2*np.pi, dim_size)
            ref *= np.exp(1j * axis_phases.reshape(
                [1]*i + [dim_size] + [1]*(len(dims)-i-1)
            ))
        return ref
    
    def store_experience(self, experience: Dict[str, torch.Tensor]) -> np.ndarray:
        """
        Store complete experience as holographic patterns
        Includes all sensory, emotional, and conscious states
        """
        # Encode different aspects in different dimensions
        spatial_data = experience.get('spatial', torch.randn(3, 100))
        temporal_data = experience.get('temporal', torch.randn(50))
        frequency_data = experience.get('frequency', torch.randn(50))
        consciousness_data = experience.get('consciousness', torch.randn(50))
        
        # Create interference pattern
        data = self._encode_6d(spatial_data, temporal_data, 
                                frequency_data, consciousness_data)
        
        # Generate hologram
        hologram = data * self.reference_beam
        
        # Store in crystal with superposition
        self.crystal += hologram
        
        return hologram
    
    def recall_by_association(self, partial_cue: torch.Tensor,
                            dimensions_known: List[str]) -> Dict:
        """
        Holographic associative recall
        Reconstructs complete memory from partial cues
        """
        # Create probe beam from partial information
        probe = self._create_probe_beam(partial_cue, dimensions_known)
        
        # Holographic reconstruction
        reconstruction = ifftn(fftn(self.crystal) * fftn(probe))
        
        # Extract different components
        experience = self._decode_6d(reconstruction)
        
        # Error correction using quantum codes
        experience = self._quantum_error_correction(experience)
        
        return experience
    
    def parallel_search(self, query: torch.Tensor) -> List[Dict]:
        """Search all memories simultaneously using quantum parallelism."""
        query_hologram = self._create_query_hologram(query)
        correlations = fftn(self.crystal * np.conj(query_hologram))
        peaks = self._find_correlation_peaks(correlations)
        return [self._reconstruct_at_peak(peak) for peak in peaks]

    # ------------------------------------------------------------------ #
    # HELPER METHODS — 5 Whys #3 root cause fix                           #
    # ------------------------------------------------------------------ #

    def _encode_6d(
        self,
        spatial: torch.Tensor,
        temporal: torch.Tensor,
        frequency: torch.Tensor,
        consciousness: torch.Tensor,
    ) -> np.ndarray:
        """Encode multi-modal data into a 6D holographic array."""
        dims    = self.dimensions
        encoded = np.zeros(dims, dtype=np.complex128)

        # Spatial → axes 0,1,2
        s = spatial.detach().cpu().numpy().flatten()
        for i in range(min(3, len(s))):
            encoded[i % dims[0]] += s[i]

        # Temporal → axis 3
        t = temporal.detach().cpu().numpy().flatten()
        for i in range(min(dims[3], len(t))):
            encoded[:, :, :, i, :, :] += t[i]

        # Frequency → axis 4
        f = frequency.detach().cpu().numpy().flatten()
        for i in range(min(dims[4], len(f))):
            encoded[:, :, :, :, i, :] += f[i]

        # Consciousness phase → axis 5
        c = consciousness.detach().cpu().numpy().flatten()
        for i in range(min(dims[5], len(c))):
            encoded[:, :, :, :, :, i] += c[i] * np.exp(1j * c[i] * np.pi)

        return encoded

    def _decode_6d(self, reconstruction: np.ndarray) -> Dict:
        """Decode a 6D holographic array back into experience components."""
        real = reconstruction.real
        return {
            "spatial":       torch.tensor(real[:3, 0, 0, 0, 0, 0].flatten(), dtype=torch.float32),
            "temporal":      torch.tensor(real[0, 0, 0, :, 0, 0].flatten(), dtype=torch.float32),
            "frequency":     torch.tensor(real[0, 0, 0, 0, :, 0].flatten(), dtype=torch.float32),
            "consciousness": torch.tensor(np.abs(reconstruction[0, 0, 0, 0, 0, :]).flatten(), dtype=torch.float32),
            "raw":           torch.tensor(real.flatten()[:768], dtype=torch.float32),
        }

    def _create_probe_beam(self, partial_cue: torch.Tensor, dimensions_known: List[str]) -> np.ndarray:
        """Create a probe beam from partial cue for associative recall."""
        probe = np.ones(self.dimensions, dtype=np.complex128)
        cue_np = partial_cue.detach().cpu().numpy().flatten()

        dim_map = {"spatial": 0, "temporal": 3, "frequency": 4, "consciousness": 5}
        for dim_name in dimensions_known:
            axis = dim_map.get(dim_name, 0)
            size = self.dimensions[axis]
            values = cue_np[:size]
            shape = [1] * 6
            shape[axis] = size
            probe *= np.exp(1j * values[:size].reshape(shape))

        return probe

    def _quantum_error_correction(self, experience: Dict) -> Dict:
        """Apply simplified quantum error correction (repetition code)."""
        corrected = {}
        for key, tensor in experience.items():
            if isinstance(tensor, torch.Tensor) and tensor.numel() > 2:
                # Majority vote over triplets
                t = tensor.float()
                if len(t) >= 3:
                    t_corrected = torch.stack([t[:-2], t[1:-1], t[2:]]).median(dim=0).values
                    corrected[key] = t_corrected
                else:
                    corrected[key] = t
            else:
                corrected[key] = tensor
        return corrected

    def _create_query_hologram(self, query: torch.Tensor) -> np.ndarray:
        """Create a query hologram for parallel search correlation."""
        q = query.detach().cpu().numpy().flatten()
        hologram = np.zeros(self.dimensions, dtype=np.complex128)
        size = min(len(q), self.dimensions[0])
        for i in range(size):
            hologram[i % self.dimensions[0], :, :, :, :, :] = q[i] * np.exp(1j * q[i])
        return hologram * self.reference_beam

    def _find_correlation_peaks(self, correlations: np.ndarray, threshold: float = 0.1, max_peaks: int = 5) -> List[tuple]:
        """Find peak correlation indices in the holographic correlation map."""
        magnitude = np.abs(correlations)
        flat = magnitude.flatten()
        threshold_val = flat.max() * threshold
        peak_indices = np.argwhere(magnitude > threshold_val)

        # Sort by magnitude descending, return top N
        scored = sorted(
            [tuple(idx) for idx in peak_indices],
            key=lambda idx: magnitude[idx],
            reverse=True,
        )
        return scored[:max_peaks]

    def _reconstruct_at_peak(self, peak: tuple) -> Dict:
        """Reconstruct a memory experience at a given correlation peak."""
        reconstruction = ifftn(self.crystal)
        # Shift reconstruction to align with peak
        shifted = np.roll(reconstruction, peak[0], axis=0)
        return self._decode_6d(shifted)
