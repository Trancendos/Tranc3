"""Holographic Data Storage — Phase 11

5D optical holographic storage simulation for the Tranc3 ecosystem.
Implements volume holographic recording with angular, wavelength,
and spatial multiplexing for ultra-high-density data storage
with simulated diffraction-based read/write operations.

Models the physics of reference/object beam interference patterns,
photorefractive crystal dynamics, Bragg selectivity, and
multi-layer volumetric storage with realistic capacity calculations.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Enums ────────────────────────────────────────────────────────────────

class StorageMedium(Enum):
    """Holographic storage medium types."""
    LITHIUM_NIOBATE = "lithium_niobate"
    PHOTOPOLYMER = "photopolymer"
    PHOTOREFRACTIVE_POLYMER = "photorefractive_polymer"
    DICHROMATED_GELATIN = "dichromated_gelatin"
    BACTERIORHODOPSIN = "bacteriorhodopsin"
    PQ_DOPED_POLYMER = "pq_doped_polymer"


class MultiplexingMethod(Enum):
    """Holographic multiplexing strategies."""
    ANGULAR = "angular"
    WAVELENGTH = "wavelength"
    PHASE_CODED = "phase_coded"
    SPECKLE = "speckle"
    PERISTROPHIC = "peristrophic"
    SHIFT = "shift"
    CORRELATION = "correlation"
    COMBINED = "combined"


class DataEncoding(Enum):
    """Data encoding schemes for holographic storage."""
    BINARY_AMPLITUDE = "binary_amplitude"
    BINARY_PHASE = "binary_phase"
    GRAY_SCALE = "gray_scale"
    COMPLEX_AMPLITUDE = "complex_amplitude"
    DIFFRACTION_EFFICIENCY = "diffraction_efficiency"


class StorageState(Enum):
    """Storage volume states."""
    EMPTY = "empty"
    RECORDING = "recording"
    READING = "reading"
    ERASING = "erasing"
    FULL = "full"
    DEGRADED = "degraded"
    ERROR = "error"


# ─── Data Models ──────────────────────────────────────────────────────────

@dataclass
class HolographicPage:
    """A single holographic data page."""
    page_id: str
    angular_offset: float = 0.0  # degrees
    wavelength_nm: float = 532.0
    data_matrix: List[List[int]] = field(default_factory=list)
    page_size_bits: int = 1024 * 1024  # 1 Mbit per page
    diffraction_efficiency: float = 0.01
    signal_to_noise: float = 10.0
    bit_error_rate: float = 1e-6
    is_recorded: bool = False
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_id": self.page_id,
            "angular_offset": self.angular_offset,
            "wavelength_nm": self.wavelength_nm,
            "page_size_bits": self.page_size_bits,
            "diffraction_efficiency": self.diffraction_efficiency,
            "signal_to_noise": self.signal_to_noise,
            "bit_error_rate": self.bit_error_rate,
            "is_recorded": self.is_recorded,
        }


@dataclass
class StorageVolume:
    """A volumetric holographic storage medium."""
    volume_id: str
    medium: StorageMedium = StorageMedium.LITHIUM_NIOBATE
    thickness_mm: float = 1.0
    area_mm2: float = 100.0  # 10mm x 10mm
    refractive_index: float = 2.3
    max_pages: int = 10000
    bragg_selectivity: float = 0.01  # degrees
    dynamic_range: float = 10.0  # M/# (photorefractive figure of merit)
    state: StorageState = StorageState.EMPTY
    pages: Dict[str, HolographicPage] = field(default_factory=dict)

    def total_capacity_bits(self) -> int:
        """Calculate total storage capacity."""
        return self.max_pages * 1024 * 1024

    def total_capacity_tb(self) -> float:
        """Calculate capacity in terabytes."""
        return self.total_capacity_bits() / (8 * 1024 ** 4)

    def used_capacity_bits(self) -> int:
        """Calculate used capacity."""
        return sum(p.page_size_bits for p in self.pages.values() if p.is_recorded)

    def utilization(self) -> float:
        """Calculate storage utilization."""
        if self.max_pages == 0:
            return 0.0
        return len([p for p in self.pages.values() if p.is_recorded]) / self.max_pages

    def to_dict(self) -> Dict[str, Any]:
        return {
            "volume_id": self.volume_id,
            "medium": self.medium.value,
            "thickness_mm": self.thickness_mm,
            "area_mm2": self.area_mm2,
            "max_pages": self.max_pages,
            "recorded_pages": len([p for p in self.pages.values() if p.is_recorded]),
            "total_capacity_tb": self.total_capacity_tb(),
            "utilization": self.utilization(),
            "state": self.state.value,
        }


@dataclass
class HolographicChannel:
    """A channel for holographic read/write operations."""
    channel_id: str
    laser_wavelength_nm: float = 532.0
    laser_power_mw: float = 100.0
    beam_diameter_mm: float = 2.0
    reference_angle: float = 45.0  # degrees
    spatial_light_modulator: str = "DMD"
    detector: str = "CMOS"
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "wavelength_nm": self.laser_wavelength_nm,
            "power_mw": self.laser_power_mw,
            "reference_angle": self.reference_angle,
            "is_active": self.is_active,
        }


# ─── Holographic Storage Engine ───────────────────────────────────────────

class HolographicStorageEngine:
    """Simulates holographic data storage operations.

    Models the physics of volume holographic recording and reading
    including Bragg selectivity, M/# dynamic range, diffraction
    efficiency scheduling, and error correction.
    """

    # Medium properties
    MEDIUM_PROPERTIES: Dict[StorageMedium, Dict[str, float]] = {
        StorageMedium.LITHIUM_NIOBATE: {
            "refractive_index": 2.3,
            "dynamic_range": 10.0,
            "sensitivity_cm2_j": 0.1,
            "response_time_s": 1.0,
            "persistence_hours": 87600,  # 10 years
        },
        StorageMedium.PHOTOPOLYMER: {
            "refractive_index": 1.5,
            "dynamic_range": 30.0,
            "sensitivity_cm2_j": 0.01,
            "response_time_s": 0.1,
            "persistence_hours": 876000,  # 100 years
        },
        StorageMedium.PHOTOREFRACTIVE_POLYMER: {
            "refractive_index": 1.6,
            "dynamic_range": 20.0,
            "sensitivity_cm2_j": 0.05,
            "response_time_s": 0.5,
            "persistence_hours": 43800,
        },
        StorageMedium.DICHROMATED_GELATIN: {
            "refractive_index": 1.52,
            "dynamic_range": 50.0,
            "sensitivity_cm2_j": 0.001,
            "response_time_s": 0.01,
            "persistence_hours": 876000,
        },
        StorageMedium.PQ_DOPED_POLYMER: {
            "refractive_index": 1.55,
            "dynamic_range": 15.0,
            "sensitivity_cm2_j": 0.02,
            "response_time_s": 0.2,
            "persistence_hours": 438000,
        },
    }

    def __init__(self, volume: StorageVolume):
        self.volume = volume
        self.properties = self.MEDIUM_PROPERTIES.get(
            volume.medium, self.MEDIUM_PROPERTIES[StorageMedium.LITHIUM_NIOBATE]
        )
        self._diffraction_scheduler: List[float] = []

    def calculate_bragg_selectivity(self) -> float:
        """Calculate angular Bragg selectivity."""
        n = self.volume.refractive_index
        d = self.volume.thickness_mm * 1e-3  # Convert to meters
        wavelength = 532e-9  # Green laser wavelength
        # Bragg selectivity: Δθ ≈ λ/(n*d*sin(θ))
        return wavelength / (n * d * math.sin(math.radians(45)))

    def calculate_max_pages(self) -> int:
        """Calculate maximum number of multiplexed pages."""
        bragg = self.calculate_bragg_selectivity()
        angular_range = 30.0  # Available angular range in degrees
        if bragg > 0:
            return int(angular_range / math.degrees(bragg))
        return 10000

    def schedule_recording(self, num_pages: int) -> List[float]:
        """Schedule exposure times using M/# for uniform diffraction.

        Uses the scheduling algorithm: t_n = t_1 * (M/#)^(2*(n-1)/N)
        """
        m_number = self.properties["dynamic_range"]
        eta_target = 1e-3  # Target diffraction efficiency

        schedule = []
        for n in range(1, num_pages + 1):
            # Exposure time decreases for later pages
            t_n = eta_target * (m_number / num_pages) ** 2
            # Each page gets less time to maintain uniform diffraction efficiency
            t_n *= math.exp(2.0 * n / num_pages)
            schedule.append(max(t_n, 1e-6))

        self._diffraction_scheduler = schedule
        return schedule

    def write_page(
        self,
        data: bytes,
        multiplexing: MultiplexingMethod = MultiplexingMethod.ANGULAR,
        page_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Write a holographic data page."""
        pid = page_id or str(uuid.uuid4())[:8]

        if len(self.volume.pages) >= self.volume.max_pages:
            return {"error": "Volume is full", "page_id": pid}

        # Calculate angular offset
        page_num = len(self.volume.pages)
        bragg = self.calculate_bragg_selectivity()
        angular_offset = page_num * math.degrees(bragg) if bragg > 0 else page_num * 0.01

        # Create data matrix (2D pixel array)
        data_bits = len(data) * 8
        page_size = max(1, int(math.sqrt(data_bits)))
        data_matrix = [
            [1 if (data[i * page_size + j] if i * page_size + j < len(data) else 0) & (1 << k) else 0
             for j in range(page_size)]
            for i in range(page_size)
            for k in [0]
        ]

        # Simulate diffraction efficiency
        m_number = self.properties["dynamic_range"]
        num_pages = max(1, len(self.volume.pages) + 1)
        eta = (m_number / num_pages) ** 2 * 1e-3

        # Signal-to-noise ratio decreases with more pages
        snr = 10.0 * math.sqrt(m_number / num_pages)

        # Bit error rate
        ber = 0.5 * math.exp(-snr / 2.0)

        page = HolographicPage(
            page_id=pid,
            angular_offset=angular_offset,
            data_matrix=data_matrix[:min(len(data_matrix), page_size)],
            page_size_bits=data_bits,
            diffraction_efficiency=eta,
            signal_to_noise=snr,
            bit_error_rate=ber,
            is_recorded=True,
        )
        self.volume.pages[pid] = page
        self.volume.state = StorageState.RECORDING

        return {
            "page_id": pid,
            "data_bits_written": data_bits,
            "angular_offset": angular_offset,
            "diffraction_efficiency": eta,
            "signal_to_noise": snr,
            "bit_error_rate": ber,
            "success": True,
        }

    def read_page(self, page_id: str) -> Dict[str, Any]:
        """Read a holographic data page."""
        page = self.volume.pages.get(page_id)
        if not page:
            return {"error": f"Page {page_id} not found"}
        if not page.is_recorded:
            return {"error": f"Page {page_id} not recorded"}

        # Simulate read noise
        import random
        read_ber = page.bit_error_rate * (1.0 + random.gauss(0, 0.1))
        read_snr = page.signal_to_noise * (1.0 + random.gauss(0, 0.05))

        return {
            "page_id": page_id,
            "data_retrieved": True,
            "diffraction_efficiency": page.diffraction_efficiency,
            "read_snr": read_snr,
            "read_ber": max(0, read_ber),
            "angular_offset": page.angular_offset,
        }

    def erase_page(self, page_id: str) -> Dict[str, Any]:
        """Erase a holographic page (thermal or optical erasure)."""
        page = self.volume.pages.get(page_id)
        if not page:
            return {"error": f"Page {page_id} not found"}

        page.is_recorded = False
        page.diffraction_efficiency = 0.0
        return {"page_id": page_id, "erased": True}

    def get_volume_status(self) -> Dict[str, Any]:
        """Get volume status."""
        return self.volume.to_dict()


# ─── Main Service ─────────────────────────────────────────────────────────

class HolographicStorageService:
    """Holographic Data Storage Service for the Tranc3 ecosystem.

    Provides ultra-high-density holographic data storage with
    volume recording, angular/wavelength multiplexing, and
    simulated diffraction-based read/write operations.
    """

    def __init__(self, medium: StorageMedium = StorageMedium.PHOTOPOLYMER):
        self._service_id = str(uuid.uuid4())
        self.volumes: Dict[str, StorageVolume] = {}
        self.engines: Dict[str, HolographicStorageEngine] = {}
        self.default_medium = medium

    def create_volume(
        self,
        volume_id: Optional[str] = None,
        medium: Optional[StorageMedium] = None,
        thickness_mm: float = 1.0,
        area_mm2: float = 100.0,
    ) -> Dict[str, Any]:
        """Create a new holographic storage volume."""
        vid = volume_id or str(uuid.uuid4())[:8]
        med = medium or self.default_medium
        volume = StorageVolume(
            volume_id=vid,
            medium=med,
            thickness_mm=thickness_mm,
            area_mm2=area_mm2,
        )
        engine = HolographicStorageEngine(volume)
        self.volumes[vid] = volume
        self.engines[vid] = engine

        return {
            "volume_id": vid,
            "medium": med.value,
            "max_pages": volume.max_pages,
            "capacity_tb": volume.total_capacity_tb(),
        }

    def write_data(
        self,
        volume_id: str,
        data: bytes,
        multiplexing: MultiplexingMethod = MultiplexingMethod.ANGULAR,
    ) -> Dict[str, Any]:
        """Write data to a volume."""
        engine = self.engines.get(volume_id)
        if not engine:
            return {"error": f"Volume {volume_id} not found"}
        return engine.write_page(data, multiplexing)

    def read_data(self, volume_id: str, page_id: str) -> Dict[str, Any]:
        """Read data from a volume."""
        engine = self.engines.get(volume_id)
        if not engine:
            return {"error": f"Volume {volume_id} not found"}
        return engine.read_page(page_id)

    def list_volumes(self) -> List[Dict[str, Any]]:
        """List all storage volumes."""
        return [v.to_dict() for v in self.volumes.values()]

    def get_holographic_storage_status(self) -> Dict[str, Any]:
        """Get service status."""
        total_pages = sum(
            len([p for p in v.pages.values() if p.is_recorded])
            for v in self.volumes.values()
        )
        total_capacity = sum(v.total_capacity_tb() for v in self.volumes.values())
        return {
            "service_id": self._service_id,
            "service_type": "holographic_storage",
            "volumes": len(self.volumes),
            "total_pages_written": total_pages,
            "total_capacity_tb": total_capacity,
            "supported_media": [m.value for m in StorageMedium],
            "status": "operational",
        }
