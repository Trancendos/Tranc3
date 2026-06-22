"""VRAR3D — Pydantic models"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SceneEngine(str, Enum):
    threejs = "threejs"
    babylonjs = "babylonjs"
    aframe = "aframe"
    model_viewer = "model-viewer"
    godot_wasm = "godot-wasm"
    offline = "offline"


class ProcessingBackend(str, Enum):
    trimesh = "trimesh"
    open3d = "open3d"
    blender = "blender"
    godot = "godot"
    pyvista = "pyvista"
    meshio = "meshio"
    sketchfab = "sketchfab"
    offline = "offline"


class SceneType(str, Enum):
    vr = "vr"
    ar = "ar"
    xr = "xr"
    scene_3d = "3d"
    panorama = "panorama"
    spatial = "spatial"


class AssetFormat(str, Enum):
    gltf = "gltf"
    glb = "glb"
    obj = "obj"
    fbx = "fbx"
    stl = "stl"
    ply = "ply"
    usdz = "usdz"
    vrm = "vrm"


class SceneObject(BaseModel):
    object_id: str
    name: str
    type: str = "mesh"
    position: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    material: Optional[Dict[str, Any]] = None
    asset_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SceneCreate(BaseModel):
    name: str
    scene_type: SceneType = SceneType.scene_3d
    description: Optional[str] = None
    objects: List[SceneObject] = Field(default_factory=list)
    environment: Optional[Dict[str, Any]] = None
    physics_enabled: bool = False
    xr_enabled: bool = False
    preferred_engine: Optional[SceneEngine] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SceneResponse(BaseModel):
    scene_id: str
    name: str
    scene_type: SceneType
    description: Optional[str] = None
    objects: List[SceneObject]
    environment: Optional[Dict[str, Any]] = None
    physics_enabled: bool
    xr_enabled: bool
    preferred_engine: Optional[SceneEngine] = None
    renderer_hints: List[str] = Field(default_factory=list)
    cdn_urls: Dict[str, str] = Field(default_factory=dict)
    metadata: Dict[str, Any]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AssetProcessRequest(BaseModel):
    scene_id: Optional[str] = None
    source_format: AssetFormat
    target_format: AssetFormat
    asset_url: Optional[str] = None
    asset_data_b64: Optional[str] = None
    optimize: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AssetProcessResponse(BaseModel):
    job_id: str
    scene_id: Optional[str]
    source_format: AssetFormat
    target_format: AssetFormat
    backend: ProcessingBackend
    status: str
    output_url: Optional[str] = None
    latency_ms: Optional[float] = None
    created_at: Optional[str] = None


class BackendStatus(BaseModel):
    name: ProcessingBackend
    healthy: bool
    pheromone: float
    calls_in_window: int
    quota_remaining: int


class VRARStatus(BaseModel):
    active_backend: ProcessingBackend
    backends: List[BackendStatus]
    renderer_priority: List[str]
    cdn_urls: Dict[str, str]
    scene_count: int
