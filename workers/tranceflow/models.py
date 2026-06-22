"""TranceFlow — Pydantic models"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GameEngine(str, Enum):
    godot = "godot"
    godot_wasm = "godot-wasm"
    offline = "offline"


class ProcessingBackend(str, Enum):
    godot = "godot"
    blender = "blender"
    trimesh = "trimesh"
    meshio = "meshio"
    open3d = "open3d"
    pyvista = "pyvista"
    offline = "offline"


class ProjectType(str, Enum):
    game_2d = "game_2d"
    game_3d = "game_3d"
    simulation = "simulation"
    interactive_3d = "interactive_3d"
    vr_experience = "vr_experience"


class ExportFormat(str, Enum):
    gltf = "gltf"
    glb = "glb"
    obj = "obj"
    fbx = "fbx"
    stl = "stl"
    ply = "ply"
    wasm = "wasm"
    pck = "pck"


class Asset3D(BaseModel):
    asset_id: str
    name: str
    format: ExportFormat
    file_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProjectCreate(BaseModel):
    name: str
    project_type: ProjectType = ProjectType.game_3d
    description: Optional[str] = None
    engine: GameEngine = GameEngine.godot
    assets: List[Asset3D] = Field(default_factory=list)
    settings: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    project_type: ProjectType
    description: Optional[str] = None
    engine: GameEngine
    assets: List[Asset3D]
    settings: Dict[str, Any]
    metadata: Dict[str, Any]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ExportRequest(BaseModel):
    project_id: Optional[str] = None
    source_path: Optional[str] = None
    source_format: ExportFormat
    target_format: ExportFormat
    asset_data_b64: Optional[str] = None
    optimize: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExportResponse(BaseModel):
    job_id: str
    project_id: Optional[str]
    source_format: ExportFormat
    target_format: ExportFormat
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


class TranceFlowStatus(BaseModel):
    active_backend: ProcessingBackend
    backends: List[BackendStatus]
    project_count: int
    engine: str
