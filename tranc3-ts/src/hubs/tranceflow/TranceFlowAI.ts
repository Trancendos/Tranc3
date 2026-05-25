/**
 * TranceFlowAI — Lead AI for the TranceFlow Hub
 *
 * Identity:  AID-TRANCEFLOW
 * Pillar:    Voxx
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    3D rendering, physics simulation, voxel processing,
 *            collision detection, ray tracing, sprite management
 *
 * Pipeline:  Voxel1 → MeshWeaver → Physicist → RayTracer
 *            Collider runs parallel for spatial queries
 *            Sprite handles 2D overlay compositing
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions';
import { MeshWeaverAgent } from './agents/MeshWeaverAgent';
import { PhysicistAgent } from './agents/PhysicistAgent';
import { Voxel1Bot } from './bots/Voxel1Bot';
import { ColliderBot } from './bots/ColliderBot';
import { RayTracerBot } from './bots/RayTracerBot';
import { SpriteBot } from './bots/SpriteBot';

// ───────────────────────────────────────────
// Domain Interfaces
// ───────────────────────────────────────────

export interface VoxelGrid {
  id: string;
  dimensions: { x: number; y: number; z: number };
  resolution: number;
  data: Float32Array;
  origin: { x: number; y: number; z: number };
  metadata: Record<string, unknown>;
}

export interface SceneDescriptor {
  id: string;
  name: string;
  meshes: MeshDescriptor[];
  lights: LightDescriptor[];
  camera: CameraDescriptor;
  environment?: EnvironmentDescriptor;
  physics?: PhysicsConfig;
}

export interface MeshDescriptor {
  id: string;
  type: 'voxel' | 'procedural' | 'imported' | 'primitive';
  vertices?: number;
  faces?: number;
  material?: string;
  transform?: Transform3D;
}

export interface LightDescriptor {
  id: string;
  type: 'point' | 'directional' | 'spot' | 'ambient' | 'area';
  intensity: number;
  color: string;
  position?: { x: number; y: number; z: number };
  direction?: { x: number; y: number; z: number };
}

export interface CameraDescriptor {
  type: 'perspective' | 'orthographic';
  fov: number;
  near: number;
  far: number;
  position: { x: number; y: number; z: number };
  target: { x: number; y: number; z: number };
}

export interface Transform3D {
  position: { x: number; y: number; z: number };
  rotation: { x: number; y: number; z: number; w: number };
  scale: { x: number; y: number; z: number };
}

export interface EnvironmentDescriptor {
  skybox?: string;
  fogDensity?: number;
  fogColor?: string;
  ambientOcclusion?: boolean;
  globalIllumination?: boolean;
}

export interface PhysicsConfig {
  gravity: { x: number; y: number; z: number };
  timeStep: number;
  solverIterations: number;
  collisionMargin: number;
}

export interface RenderJob {
  id: string;
  scene: SceneDescriptor;
  resolution: { width: number; height: number };
  samples: number;
  bounces: number;
  denoise: boolean;
  outputFormat: 'png' | 'exr' | 'hdr';
  priority: 'low' | 'normal' | 'high' | 'critical';
  status: 'queued' | 'rendering' | 'completed' | 'failed';
  progress: number;
  createdAt: number;
  startedAt?: number;
  completedAt?: number;
}

export interface PhysicsStep {
  sceneId: string;
  deltaTime: number;
  collisions: CollisionResult[];
  forces: AppliedForce[];
  totalEnergy: number;
  stepNumber: number;
}

export interface CollisionResult {
  objectA: string;
  objectB: string;
  contactPoint: { x: number; y: number; z: number };
  contactNormal: { x: number; y: number; z: number };
  penetrationDepth: number;
}

export interface AppliedForce {
  targetObject: string;
  force: { x: number; y: number; z: number };
  type: 'gravity' | 'impulse' | 'spring' | 'drag' | 'custom';
}

export interface SpriteLayer {
  id: string;
  sprites: SpriteDescriptor[];
  zIndex: number;
  opacity: number;
  blendMode: 'normal' | 'additive' | 'multiply' | 'screen';
}

export interface SpriteDescriptor {
  id: string;
  texture: string;
  position: { x: number; y: number };
  size: { width: number; height: number };
  rotation: number;
  flipX: boolean;
  flipY: boolean;
  frame?: number;
  animation?: string;
}

// ───────────────────────────────────────────
// TranceFlowAI Implementation
// ───────────────────────────────────────────

export class TranceFlowAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private scenes: Map<string, SceneDescriptor>;
  private renderQueue: RenderJob[];
  private voxelGrids: Map<string, VoxelGrid>;
  private spriteLayers: Map<string, SpriteLayer>;
  private physicsState: Map<string, PhysicsStep[]>;

  constructor() {
    super(
      'AID-TRANCEFLOW',
      'TranceFlow',
      'tranceflow',
      'Voxx',
      3
    );

    this.log = new Logger('TranceFlowAI');
    this.audit = AuditLedger.getInstance();
    this.scenes = new Map();
    this.renderQueue = [];
    this.voxelGrids = new Map();
    this.spriteLayers = new Map();
    this.physicsState = new Map();

    // ── Register Agents ──
    this.registerAgent(new MeshWeaverAgent());
    this.registerAgent(new PhysicistAgent());

    // ── Register Bots ──
    this.registerBot(new Voxel1Bot());
    this.registerBot(new ColliderBot());
    this.registerBot(new RayTracerBot());
    this.registerBot(new SpriteBot());

    this.log.info('TranceFlowAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
    });
  }

  // ───────────────────────────────────────
  // Scene Management
  // ───────────────────────────────────────

  /**
   * Create a new 3D scene descriptor and register it.
   */
  createScene(descriptor: Omit<SceneDescriptor, 'id'>): SceneDescriptor {
    const id = `SCENE-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();
    const scene: SceneDescriptor = { ...descriptor, id };
    this.scenes.set(id, scene);

    this.audit.append({
      actor: this.id,
      action: 'SCENE_CREATED',
      entity: id,
      details: { name: scene.name, meshCount: scene.meshes.length },
      timestamp: Date.now(),
    });

    this.log.info('Scene created', { sceneId: id, name: scene.name });
    return scene;
  }

  /**
   * Retrieve a scene by its identifier.
   */
  getScene(sceneId: string): SceneDescriptor | undefined {
    return this.scenes.get(sceneId);
  }

  /**
   * Remove a scene and its associated physics state.
   */
  removeScene(sceneId: string): boolean {
    const removed = this.scenes.delete(sceneId);
    this.physicsState.delete(sceneId);
    if (removed) {
      this.log.info('Scene removed', { sceneId });
    }
    return removed;
  }

  // ───────────────────────────────────────
  // Voxel Processing
  // ───────────────────────────────────────

  /**
   * Create a new voxel grid and delegate initial processing to Voxel1Bot.
   */
  async processVoxels(
    dimensions: { x: number; y: number; z: number },
    resolution: number
  ): Promise<VoxelGrid> {
    const voxelBot = this.getBot('Voxel1')!;
    const result = await voxelBot.execute({
      operation: 'CREATE',
      dimensions,
      resolution,
    });

    const grid: VoxelGrid = {
      id: `VOXEL-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase(),
      dimensions,
      resolution,
      data: new Float32Array(dimensions.x * dimensions.y * dimensions.z),
      origin: { x: 0, y: 0, z: 0 },
      metadata: result as Record<string, unknown>,
    };

    this.voxelGrids.set(grid.id, grid);
    this.log.info('Voxel grid created', { gridId: grid.id, dimensions, resolution });
    return grid;
  }

  /**
   * Fill a region of a voxel grid with a density value.
   */
  async fillVoxelRegion(
    gridId: string,
    region: { min: { x: number; y: number; z: number }; max: { x: number; y: number; z: number } },
    density: number
  ): Promise<VoxelGrid | null> {
    const grid = this.voxelGrids.get(gridId);
    if (!grid) {
      this.log.warn('Voxel grid not found', { gridId });
      return null;
    }

    const voxelBot = this.getBot('Voxel1')!;
    await voxelBot.execute({
      operation: 'FILL',
      gridId,
      region,
      density,
    });

    // Fill the region in the data array
    for (let z = region.min.z; z < region.max.z; z++) {
      for (let y = region.min.y; y < region.max.y; y++) {
        for (let x = region.min.x; x < region.max.x; x++) {
          const idx = x + y * grid.dimensions.x + z * grid.dimensions.x * grid.dimensions.y;
          if (idx >= 0 && idx < grid.data.length) {
            grid.data[idx] = density;
          }
        }
      }
    }

    this.log.info('Voxel region filled', { gridId, density, region });
    return grid;
  }

  // ───────────────────────────────────────
  // Mesh Composition
  // ───────────────────────────────────────

  /**
   * Delegate mesh composition to MeshWeaverAgent.
   * Converts voxel data or procedural parameters into mesh descriptors.
   */
  async composeMesh(
    source: 'voxel' | 'procedural' | 'primitive',
    params: Record<string, unknown>
  ): Promise<MeshDescriptor> {
    const meshAgent = this.getAgent('SID-TRANCEFLOW-MESHWEAVER') as MeshWeaverAgent;
    const mesh = await meshAgent.runCycle({ source, params });

    this.audit.append({
      actor: this.id,
      action: 'MESH_COMPOSED',
      entity: mesh.id,
      details: { source, type: mesh.type, vertices: mesh.vertices, faces: mesh.faces },
      timestamp: Date.now(),
    });

    this.log.info('Mesh composed', { meshId: mesh.id, source, type: mesh.type });
    return mesh;
  }

  // ───────────────────────────────────────
  // Physics Simulation
  // ───────────────────────────────────────

  /**
   * Run a physics simulation step for a scene, delegating to PhysicistAgent.
   * ColliderBot provides collision detection data.
   */
  async simulatePhysics(
    sceneId: string,
    deltaTime: number = 1 / 60
  ): Promise<PhysicsStep> {
    const scene = this.scenes.get(sceneId);
    if (!scene) {
      throw new Error(`Scene not found: ${sceneId}`);
    }

    // Gather collision data first
    const colliderBot = this.getBot('Collider')!;
    const collisionData = await colliderBot.execute({
      operation: 'DETECT',
      sceneId,
      objects: scene.meshes.map(m => m.id),
    });

    // Delegate physics step to PhysicistAgent
    const physicistAgent = this.getAgent('SID-TRANCEFLOW-PHYSICIST') as PhysicistAgent;
    const step = await physicistAgent.runCycle({
      scene,
      deltaTime,
      collisions: collisionData,
    });

    // Record physics state
    if (!this.physicsState.has(sceneId)) {
      this.physicsState.set(sceneId, []);
    }
    this.physicsState.get(sceneId)!.push(step);

    this.log.info('Physics step completed', {
      sceneId,
      step: step.stepNumber,
      collisionCount: step.collisions.length,
      totalEnergy: step.totalEnergy.toFixed(2),
    });

    return step;
  }

  // ───────────────────────────────────────
  // Collision Detection
  // ───────────────────────────────────────

  /**
   * Perform collision detection for a set of objects via ColliderBot.
   */
  async detectCollisions(
    sceneId: string,
    objectIds: string[]
  ): Promise<CollisionResult[]> {
    const colliderBot = this.getBot('Collider')!;
    const result = await colliderBot.execute({
      operation: 'DETECT',
      sceneId,
      objects: objectIds,
    });

    this.log.info('Collision detection completed', {
      sceneId,
      objectCount: objectIds.length,
      collisionCount: Array.isArray(result) ? result.length : 0,
    });

    return result as CollisionResult[];
  }

  // ───────────────────────────────────────
  // Ray Tracing / Rendering
  // ───────────────────────────────────────

  /**
   * Submit a render job to the ray tracing queue.
   */
  submitRenderJob(
    scene: SceneDescriptor,
    resolution: { width: number; height: number },
    options: { samples?: number; bounces?: number; denoise?: boolean; outputFormat?: 'png' | 'exr' | 'hdr'; priority?: 'low' | 'normal' | 'high' | 'critical' } = {}
  ): RenderJob {
    const job: RenderJob = {
      id: `RENDER-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase(),
      scene,
      resolution,
      samples: options.samples ?? 64,
      bounces: options.bounces ?? 3,
      denoise: options.denoise ?? true,
      outputFormat: options.outputFormat ?? 'png',
      priority: options.priority ?? 'normal',
      status: 'queued',
      progress: 0,
      createdAt: Date.now(),
    };

    // Insert in priority order
    const priorityOrder = { critical: 0, high: 1, normal: 2, low: 3 };
    const insertIdx = this.renderQueue.findIndex(
      j => priorityOrder[j.priority] > priorityOrder[job.priority]
    );
    if (insertIdx === -1) {
      this.renderQueue.push(job);
    } else {
      this.renderQueue.splice(insertIdx, 0, job);
    }

    this.audit.append({
      actor: this.id,
      action: 'RENDER_JOB_SUBMITTED',
      entity: job.id,
      details: { sceneId: scene.id, resolution, samples: job.samples, priority: job.priority },
      timestamp: Date.now(),
    });

    this.log.info('Render job submitted', { jobId: job.id, sceneId: scene.id, priority: job.priority });
    return job;
  }

  /**
   * Process the next render job in the queue using RayTracerBot.
   */
  async processNextRenderJob(): Promise<RenderJob | null> {
    if (this.renderQueue.length === 0) {
      this.log.debug('No render jobs in queue');
      return null;
    }

    const job = this.renderQueue.shift()!;
    job.status = 'rendering';
    job.startedAt = Date.now();

    const rayTracer = this.getBot('RayTracer')!;
    const result = await rayTracer.execute({
      operation: 'RENDER',
      scene: job.scene,
      resolution: job.resolution,
      samples: job.samples,
      bounces: job.bounces,
      denoise: job.denoise,
      outputFormat: job.outputFormat,
    });

    job.status = 'completed';
    job.progress = 100;
    job.completedAt = Date.now();

    this.audit.append({
      actor: this.id,
      action: 'RENDER_JOB_COMPLETED',
      entity: job.id,
      details: {
        duration: job.completedAt - job.startedAt!,
        outputFormat: job.outputFormat,
      },
      timestamp: Date.now(),
    });

    this.log.info('Render job completed', {
      jobId: job.id,
      duration: `${((job.completedAt - job.startedAt!) / 1000).toFixed(2)}s`,
    });

    return job;
  }

  /**
   * Get the current render queue status.
   */
  getRenderQueueStatus(): { total: number; queued: number; byPriority: Record<string, number> } {
    const byPriority: Record<string, number> = { critical: 0, high: 0, normal: 0, low: 0 };
    for (const job of this.renderQueue) {
      byPriority[job.priority]++;
    }
    return {
      total: this.renderQueue.length,
      queued: this.renderQueue.filter(j => j.status === 'queued').length,
      byPriority,
    };
  }

  // ───────────────────────────────────────
  // Sprite / 2D Compositing
  // ───────────────────────────────────────

  /**
   * Create a new sprite layer for 2D overlay compositing.
   */
  createSpriteLayer(zIndex: number, blendMode: SpriteLayer['blendMode'] = 'normal'): SpriteLayer {
    const layer: SpriteLayer = {
      id: `SPRITE-LAYER-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase(),
      sprites: [],
      zIndex,
      opacity: 1.0,
      blendMode,
    };

    this.spriteLayers.set(layer.id, layer);
    this.log.info('Sprite layer created', { layerId: layer.id, zIndex, blendMode });
    return layer;
  }

  /**
   * Add a sprite to a layer, delegating to SpriteBot.
   */
  async addSprite(
    layerId: string,
    sprite: Omit<SpriteDescriptor, 'id'>
  ): Promise<SpriteDescriptor | null> {
    const layer = this.spriteLayers.get(layerId);
    if (!layer) {
      this.log.warn('Sprite layer not found', { layerId });
      return null;
    }

    const spriteBot = this.getBot('Sprite')!;
    const result = await spriteBot.execute({
      operation: 'ADD',
      layerId,
      sprite,
    });

    const descriptor: SpriteDescriptor = {
      ...sprite,
      id: `SPRITE-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase(),
    };

    layer.sprites.push(descriptor);
    this.log.info('Sprite added to layer', { layerId, spriteId: descriptor.id, texture: sprite.texture });
    return descriptor;
  }

  // ───────────────────────────────────────
  // Health & Diagnostics
  // ───────────────────────────────────────

  /**
   * Perform a health check across all TranceFlow subsystems.
   */
  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    scenes: number;
    voxelGrids: number;
    renderQueueLength: number;
    spriteLayers: number;
    agents: number;
    bots: number;
    timestamp: number;
  } {
    return {
      status: 'healthy',
      scenes: this.scenes.size,
      voxelGrids: this.voxelGrids.size,
      renderQueueLength: this.renderQueue.length,
      spriteLayers: this.spriteLayers.size,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: Date.now(),
    };
  }
}
