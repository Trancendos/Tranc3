"""Platform-wide deployment, infrastructure mode, entity rotation, scanning, and detection."""

from src.platform.infrastructure_mode import (
    PlatformInfraMode,
    get_infrastructure_mode,
    infrastructure_status,
    is_cloud_only,
    is_hybrid,
    is_local_only,
)
from src.platform.layer_rotator import PlatformLayer, get_layer_rotator, layer_rotation_enabled
from src.platform.entity_rotation import EntityID, EntityRotator, get_entity_rotator
from src.platform.intelligent_scanner import IntelligentScanner, get_scanner
from src.platform.smart_detector import SmartDetector, get_detector, AlertType

__all__ = [
    # Infrastructure mode
    "PlatformInfraMode",
    "PlatformLayer",
    "get_infrastructure_mode",
    "get_layer_rotator",
    "infrastructure_status",
    "is_cloud_only",
    "is_hybrid",
    "is_local_only",
    "layer_rotation_enabled",
    # Entity rotation (all 43 entities, zero-cost, AI agent preserved)
    "EntityID",
    "EntityRotator",
    "get_entity_rotator",
    # Intelligent scanning
    "IntelligentScanner",
    "get_scanner",
    # Smart detection
    "AlertType",
    "SmartDetector",
    "get_detector",
]
