/**
 * TranceFlow Hub — Barrel Exports
 */

export { TranceFlowAI } from './TranceFlowAI';
export type {
  VoxelGrid,
  SceneDescriptor,
  MeshDescriptor,
  LightDescriptor,
  CameraDescriptor,
  Transform3D,
  EnvironmentDescriptor,
  PhysicsConfig,
  RenderJob,
  PhysicsStep,
  CollisionResult,
  AppliedForce,
  SpriteLayer,
  SpriteDescriptor,
} from './TranceFlowAI';

export { MeshWeaverAgent } from './agents/MeshWeaverAgent';
export type {
  MeshSource,
  MeshTopology,
  MaterialDescriptor,
  LODLevel,
  SubdivisionRule,
  MeshWeaveResult,
} from './agents/MeshWeaverAgent';

export { PhysicistAgent } from './agents/PhysicistAgent';
export type {
  PhysicsBody,
  ForceApplication,
  ConstraintDescriptor,
  PhysicsSceneState,
  PhysicsStepResult,
  IntegrationMethod,
} from './agents/PhysicistAgent';

export { Voxel1Bot } from './bots/Voxel1Bot';
export type {
  VoxelCreateParams,
  VoxelFillParams,
  VoxelSampleParams,
  VoxelStatsParams,
  VoxelMorphParams,
  VoxelExportParams,
  VoxelStatsResult,
  VoxelExportResult,
} from './bots/Voxel1Bot';

export { ColliderBot } from './bots/ColliderBot';
export type {
  AABB,
  Sphere,
  CollisionObject,
  ContactPoint,
  CollisionPair,
  Ray,
  RayHit,
} from './bots/ColliderBot';

export { RayTracerBot } from './bots/RayTracerBot';
export type {
  RenderResult,
  RenderEstimate,
  RenderStats,
} from './bots/RayTracerBot';

export { SpriteBot } from './bots/SpriteBot';
export type {
  SpriteData,
  SpriteSheetResult,
} from './bots/SpriteBot';
