/**
 * MeshWeaverAgent — 3D Mesh Composition Agent for TranceFlow
 *
 * Identity:  SID-TRANCEFLOW-MESHWEAVER
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TranceFlowAI (AID-TRANCEFLOW)
 *
 * Responsibilities:
 *   - Compose 3D mesh descriptors from voxel data, procedural rules, or primitives
 *   - Apply materials, transforms, and subdivision rules
 *   - Manage mesh topology (vertices, edges, faces, normals)
 *   - Optimize mesh through decimation and LOD generation
 *   - Weave multiple mesh sources into unified scene geometry
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions';

// ───────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────

export interface MeshSource {
  type: 'voxel' | 'procedural' | 'primitive' | 'imported';
  params: Record<string, unknown>;
}

export interface MeshTopology {
  vertices: number;
  edges: number;
  faces: number;
  normals: boolean;
  uvs: boolean;
  tangents: boolean;
}

export interface MaterialDescriptor {
  id: string;
  name: string;
  type: 'pbr' | 'unlit' | 'phong' | 'toon';
  albedo?: string;
  metallic?: number;
  roughness?: number;
  emissive?: string;
  opacity?: number;
  normalMap?: string;
}

export interface LODLevel {
  level: number;
  vertexCount: number;
  faceCount: number;
  reductionRatio: number;
  screenCoverage: number;
}

export interface SubdivisionRule {
  algorithm: 'catmull-clark' | 'loop' | 'doo-sabin';
  iterations: number;
  creaseWeight: number;
}

export interface MeshWeaveResult {
  id: string;
  type: MeshSource['type'];
  topology: MeshTopology;
  material?: MaterialDescriptor;
  transform?: {
    position: { x: number; y: number; z: number };
    rotation: { x: number; y: number; z: number; w: number };
    scale: { x: number; y: number; z: number };
  };
  lods: LODLevel[];
  subdivisionApplied: boolean;
  optimizationApplied: boolean;
  source: MeshSource;
}

type MeshWeaverDecision =
  | 'COMPOSE_PRIMITIVE'
  | 'COMPOSE_VOXEL'
  | 'COMPOSE_PROCEDURAL'
  | 'APPLY_SUBDIVISION'
  | 'OPTIMIZE_DECIMATE'
  | 'GENERATE_LODS'
  | 'APPLY_MATERIAL'
  | 'WEAVE_COMPOSITE';

interface MeshWeaverState {
  composedMeshes: number;
  optimizedMeshes: number;
  totalVertices: number;
  totalFaces: number;
  subdivisionCount: number;
  lodGenerations: number;
}

// ───────────────────────────────────────────
// MeshWeaverAgent Implementation
// ───────────────────────────────────────────

export class MeshWeaverAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private meshRegistry: Map<string, MeshWeaveResult>;
  private materials: Map<string, MaterialDescriptor>;
  private agentState: MeshWeaverState;

  constructor() {
    super(
      'SID-TRANCEFLOW-MESHWEAVER',
      'MeshWeaverAgent',
      'TranceFlow'
    );

    this.log = new Logger('MeshWeaverAgent');
    this.audit = AuditLedger.getInstance();
    this.meshRegistry = new Map();
    this.materials = new Map();
    this.agentState = {
      composedMeshes: 0,
      optimizedMeshes: 0,
      totalVertices: 0,
      totalFaces: 0,
      subdivisionCount: 0,
      lodGenerations: 0,
    };

    // Register tools
    this.registerTool('composePrimitive', this.composePrimitive.bind(this));
    this.registerTool('composeFromVoxels', this.composeFromVoxels.bind(this));
    this.registerTool('composeProcedural', this.composeProcedural.bind(this));
    this.registerTool('applySubdivision', this.applySubdivision.bind(this));
    this.registerTool('optimizeMesh', this.optimizeMesh.bind(this));
    this.registerTool('generateLODs', this.generateLODs.bind(this));
    this.registerTool('applyMaterial', this.applyMaterial.bind(this));
    this.registerTool('weaveComposite', this.weaveComposite.bind(this));

    this.log.info('MeshWeaverAgent initialised', { toolCount: 7 });
  }

  // ───────────────────────────────────────
  // Abstract Method Implementations
  // ───────────────────────────────────────

  protected async perceive(input: unknown): Promise<unknown> {
    const meshSource = input as MeshSource;
    this.log.debug('Perceiving mesh source', { type: meshSource.type });

    // Analyze the source to determine complexity and requirements
    const analysis = {
      sourceType: meshSource.type,
      params: meshSource.params,
      estimatedComplexity: this.estimateComplexity(meshSource),
      requiresSubdivision: this.checkSubdivisionNeeded(meshSource),
      requiresOptimization: this.checkOptimizationNeeded(meshSource),
      timestamp: Date.now(),
    };

    this.memory.push(analysis);
    return analysis;
  }

  protected async decide(perception: unknown): Promise<MeshWeaverDecision> {
    const analysis = perception as {
      sourceType: MeshSource['type'];
      estimatedComplexity: number;
      requiresSubdivision: boolean;
      requiresOptimization: boolean;
    };

    // Decision logic based on source type and requirements
    if (analysis.sourceType === 'primitive') {
      if (analysis.requiresSubdivision) return 'APPLY_SUBDIVISION';
      return 'COMPOSE_PRIMITIVE';
    }

    if (analysis.sourceType === 'voxel') {
      return 'COMPOSE_VOXEL';
    }

    if (analysis.sourceType === 'procedural') {
      return 'COMPOSE_PROCEDURAL';
    }

    if (analysis.requiresOptimization) {
      return 'OPTIMIZE_DECIMATE';
    }

    if (analysis.requiresSubdivision) {
      return 'APPLY_SUBDIVISION';
    }

    // Default: compose from the given source
    return 'COMPOSE_PRIMITIVE';
  }

  protected async act(decision: MeshWeaverDecision, perception: unknown): Promise<MeshWeaveResult> {
    const analysis = perception as { sourceType: MeshSource['type']; params: Record<string, unknown> };
    const source: MeshSource = { type: analysis.sourceType, params: analysis.params };

    this.log.info('Acting on mesh decision', { decision, sourceType: source.type });

    let result: MeshWeaveResult;

    switch (decision) {
      case 'COMPOSE_PRIMITIVE':
        result = this.composePrimitive(source.params);
        break;
      case 'COMPOSE_VOXEL':
        result = this.composeFromVoxels(source.params);
        break;
      case 'COMPOSE_PROCEDURAL':
        result = this.composeProcedural(source.params);
        break;
      case 'APPLY_SUBDIVISION':
        result = this.composePrimitive(source.params);
        result = this.applySubdivision(result, {
          algorithm: 'catmull-clark',
          iterations: 2,
          creaseWeight: 0.5,
        });
        break;
      case 'OPTIMIZE_DECIMATE':
        result = this.composePrimitive(source.params);
        result = this.optimizeMesh(result, 0.5);
        break;
      default:
        result = this.composePrimitive(source.params);
    }

    // Register the result
    this.meshRegistry.set(result.id, result);
    this.agentState.composedMeshes++;
    this.agentState.totalVertices += result.topology.vertices;
    this.agentState.totalFaces += result.topology.faces;

    this.audit.append({
      actor: this.id,
      action: 'MESH_COMPOSED',
      entity: result.id,
      details: {
        decision,
        sourceType: source.type,
        vertices: result.topology.vertices,
        faces: result.topology.faces,
      },
      timestamp: Date.now(),
    });

    this.episodeCount++;
    return result;
  }

  // ───────────────────────────────────────
  // Tool Implementations
  // ───────────────────────────────────────

  /**
   * Compose a primitive mesh (sphere, cube, cylinder, cone, torus, plane, icosphere).
   */
  private composePrimitive(params: Record<string, unknown>): MeshWeaveResult {
    const primitive = (params.primitive as string) ?? 'cube';
    const segments = (params.segments as number) ?? 16;
    const rings = (params.rings as number) ?? 16;

    const topology = this.computePrimitiveTopology(primitive, segments, rings);

    const result: MeshWeaveResult = {
      id: `MESH-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase(),
      type: 'primitive',
      topology,
      transform: {
        position: { x: 0, y: 0, z: 0 },
        rotation: { x: 0, y: 0, z: 0, w: 1 },
        scale: { x: 1, y: 1, z: 1 },
      },
      lods: [],
      subdivisionApplied: false,
      optimizationApplied: false,
      source: { type: 'primitive', params },
    };

    this.log.debug('Primitive mesh composed', { primitive, vertices: topology.vertices, faces: topology.faces });
    return result;
  }

  /**
   * Compose a mesh from voxel data via marching cubes algorithm (scaffold).
   */
  private composeFromVoxels(params: Record<string, unknown>): MeshWeaveResult {
    const dimensions = params.dimensions as { x: number; y: number; z: number } ?? { x: 32, y: 32, z: 32 };
    const isoLevel = (params.isoLevel as number) ?? 0.5;

    // Marching cubes estimate: approximately 3 triangles per voxel on the surface
    // Assume ~20% of voxels are on the surface
    const totalVoxels = dimensions.x * dimensions.y * dimensions.z;
    const surfaceVoxels = Math.floor(totalVoxels * 0.2);
    const faces = surfaceVoxels * 3;
    const vertices = faces * 3; // 3 vertices per triangle (non-indexed)

    const topology: MeshTopology = {
      vertices,
      edges: Math.floor(faces * 1.5),
      faces,
      normals: true,
      uvs: true,
      tangents: false,
    };

    const result: MeshWeaveResult = {
      id: `MESH-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase(),
      type: 'voxel',
      topology,
      transform: {
        position: { x: 0, y: 0, z: 0 },
        rotation: { x: 0, y: 0, z: 0, w: 1 },
        scale: { x: 1, y: 1, z: 1 },
      },
      lods: [],
      subdivisionApplied: false,
      optimizationApplied: false,
      source: { type: 'voxel', params },
    };

    this.log.debug('Voxel mesh composed via marching cubes', {
      dimensions,
      isoLevel,
      vertices: topology.vertices,
      faces: topology.faces,
    });

    return result;
  }

  /**
   * Compose a procedural mesh using algorithmic generation rules.
   */
  private composeProcedural(params: Record<string, unknown>): MeshWeaveResult {
    const algorithm = (params.algorithm as string) ?? 'terrain';
    const complexity = (params.complexity as number) ?? 5;
    const seed = (params.seed as number) ?? 42;

    // Estimate topology based on algorithm and complexity
    const baseVertices = Math.pow(2, complexity + 4);
    let vertices: number;
    let faces: number;

    switch (algorithm) {
      case 'terrain':
        vertices = baseVertices * baseVertices;
        faces = (baseVertices - 1) * (baseVertices - 1) * 2;
        break;
      case 'fractal':
        vertices = baseVertices * 20;
        faces = vertices * 2;
        break;
      case 'l-system':
        vertices = baseVertices * 4;
        faces = vertices;
        break;
      default:
        vertices = baseVertices * 8;
        faces = vertices * 2;
    }

    const topology: MeshTopology = {
      vertices,
      edges: Math.floor(faces * 1.5),
      faces,
      normals: true,
      uvs: algorithm === 'terrain',
      tangents: algorithm === 'terrain',
    };

    const result: MeshWeaveResult = {
      id: `MESH-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase(),
      type: 'procedural',
      topology,
      transform: {
        position: { x: 0, y: 0, z: 0 },
        rotation: { x: 0, y: 0, z: 0, w: 1 },
        scale: { x: 1, y: 1, z: 1 },
      },
      lods: [],
      subdivisionApplied: false,
      optimizationApplied: false,
      source: { type: 'procedural', params },
    };

    this.log.debug('Procedural mesh composed', { algorithm, complexity, seed, vertices, faces });
    return result;
  }

  /**
   * Apply subdivision surface to smooth a mesh.
   */
  private applySubdivision(mesh: MeshWeaveResult, rule: SubdivisionRule): MeshWeaveResult {
    let { vertices, faces } = mesh.topology;

    for (let i = 0; i < rule.iterations; i++) {
      // Catmull-Clark: each face produces (n + 1) new faces where n = face sides
      // Simplified: each quad face produces 4 new quad faces
      if (rule.algorithm === 'catmull-clark') {
        vertices = vertices * 4;
        faces = faces * 4;
      } else if (rule.algorithm === 'loop') {
        // Loop subdivision: each triangle produces 4 triangles
        vertices = Math.floor(vertices * 3);
        faces = faces * 4;
      } else {
        // Doo-Sabin: each face produces n new faces
        vertices = vertices * 2;
        faces = faces * 2;
      }
    }

    const result: MeshWeaveResult = {
      ...mesh,
      topology: {
        ...mesh.topology,
        vertices,
        edges: Math.floor(faces * 1.5),
        faces,
      },
      subdivisionApplied: true,
    };

    this.agentState.subdivisionCount++;
    this.log.debug('Subdivision applied', {
      algorithm: rule.algorithm,
      iterations: rule.iterations,
      newVertices: vertices,
      newFaces: faces,
    });

    return result;
  }

  /**
   * Optimize a mesh through decimation, reducing geometry while preserving shape.
   */
  private optimizeMesh(mesh: MeshWeaveResult, targetRatio: number): MeshWeaveResult {
    const reducedVertices = Math.floor(mesh.topology.vertices * targetRatio);
    const reducedFaces = Math.floor(mesh.topology.faces * targetRatio);

    const result: MeshWeaveResult = {
      ...mesh,
      topology: {
        ...mesh.topology,
        vertices: reducedVertices,
        edges: Math.floor(reducedFaces * 1.5),
        faces: reducedFaces,
      },
      optimizationApplied: true,
    };

    this.agentState.optimizedMeshes++;
    this.log.debug('Mesh optimized via decimation', {
      originalVertices: mesh.topology.vertices,
      reducedVertices,
      reductionRatio: ((1 - targetRatio) * 100).toFixed(1) + '%',
    });

    return result;
  }

  /**
   * Generate LOD (Level of Detail) levels for a mesh.
   */
  private generateLODs(mesh: MeshWeaveResult, levels: number = 3): MeshWeaveResult {
    const lods: LODLevel[] = [];

    for (let i = 0; i < levels; i++) {
      const reductionRatio = Math.pow(0.5, i + 1);
      const screenCoverage = 1 / Math.pow(2, i);
      lods.push({
        level: i,
        vertexCount: Math.floor(mesh.topology.vertices * reductionRatio),
        faceCount: Math.floor(mesh.topology.faces * reductionRatio),
        reductionRatio,
        screenCoverage,
      });
    }

    const result: MeshWeaveResult = {
      ...mesh,
      lods,
    };

    this.agentState.lodGenerations++;
    this.log.debug('LODs generated', { levels, lodVertexCounts: lods.map(l => l.vertexCount) });

    return result;
  }

  /**
   * Apply a material descriptor to a mesh.
   */
  private applyMaterial(mesh: MeshWeaveResult, material: MaterialDescriptor): MeshWeaveResult {
    this.materials.set(material.id, material);
    const result: MeshWeaveResult = { ...mesh, material };
    this.log.debug('Material applied', { meshId: mesh.id, materialId: material.id, materialName: material.name });
    return result;
  }

  /**
   * Weave multiple meshes into a composite mesh.
   */
  private weaveComposite(meshes: MeshWeaveResult[]): MeshWeaveResult {
    const totalVertices = meshes.reduce((sum, m) => sum + m.topology.vertices, 0);
    const totalFaces = meshes.reduce((sum, m) => sum + m.topology.faces, 0);

    const result: MeshWeaveResult = {
      id: `MESH-COMPOSITE-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase(),
      type: 'imported', // composite treated as imported
      topology: {
        vertices: totalVertices,
        edges: Math.floor(totalFaces * 1.5),
        faces: totalFaces,
        normals: meshes.every(m => m.topology.normals),
        uvs: meshes.every(m => m.topology.uvs),
        tangents: meshes.every(m => m.topology.tangents),
      },
      lods: [],
      subdivisionApplied: meshes.some(m => m.subdivisionApplied),
      optimizationApplied: meshes.some(m => m.optimizationApplied),
      source: { type: 'imported', params: { meshCount: meshes.length, sourceIds: meshes.map(m => m.id) } },
    };

    this.log.debug('Composite mesh woven', { meshCount: meshes.length, totalVertices, totalFaces });
    return result;
  }

  // ───────────────────────────────────────
  // Helpers
  // ───────────────────────────────────────

  private computePrimitiveTopology(primitive: string, segments: number, rings: number): MeshTopology {
    switch (primitive) {
      case 'sphere':
        return {
          vertices: (segments + 1) * (rings + 1),
          edges: segments * rings * 2,
          faces: segments * rings * 2,
          normals: true,
          uvs: true,
          tangents: true,
        };
      case 'cube':
        return { vertices: 24, edges: 12, faces: 12, normals: true, uvs: true, tangents: false };
      case 'cylinder':
        return {
          vertices: (segments + 1) * 2 + segments * 2,
          edges: segments * 6,
          faces: segments * 4,
          normals: true,
          uvs: true,
          tangents: false,
        };
      case 'cone':
        return {
          vertices: segments + 2,
          edges: segments * 2,
          faces: segments * 2,
          normals: true,
          uvs: true,
          tangents: false,
        };
      case 'torus':
        return {
          vertices: (segments + 1) * (rings + 1),
          edges: segments * rings * 2,
          faces: segments * rings * 2,
          normals: true,
          uvs: true,
          tangents: true,
        };
      case 'plane':
        return {
          vertices: (segments + 1) * (segments + 1),
          edges: segments * segments * 2,
          faces: segments * segments * 2,
          normals: true,
          uvs: true,
          tangents: false,
        };
      case 'icosphere':
        // Icosphere starts with 12 vertices, 20 faces; each subdivision quadruples faces
        const subdivisions = Math.min(Math.floor(Math.log2(rings)), 5);
        let icoVertices = 12;
        let icoFaces = 20;
        for (let i = 0; i < subdivisions; i++) {
          icoVertices = icoVertices * 4 - 6;
          icoFaces *= 4;
        }
        return { vertices: icoVertices, edges: Math.floor(icoFaces * 1.5), faces: icoFaces, normals: true, uvs: false, tangents: false };
      default:
        return { vertices: 24, edges: 12, faces: 12, normals: true, uvs: true, tangents: false };
    }
  }

  private estimateComplexity(source: MeshSource): number {
    switch (source.type) {
      case 'primitive': return 1;
      case 'voxel': return 5;
      case 'procedural': return 3;
      case 'imported': return 2;
      default: return 2;
    }
  }

  private checkSubdivisionNeeded(source: MeshSource): boolean {
    return source.type === 'primitive' && source.params.primitive === 'icosphere';
  }

  private checkOptimizationNeeded(source: MeshSource): boolean {
    if (source.type === 'voxel') {
      const dims = source.params.dimensions as { x: number; y: number; z: number } | undefined;
      if (dims) {
        return dims.x * dims.y * dims.z > 100000;
      }
    }
    return false;
  }

  // ───────────────────────────────────────
  // Agent State Accessors
  // ───────────────────────────────────────

  getStats(): MeshWeaverState {
    return { ...this.agentState };
  }

  getMeshCount(): number {
    return this.meshRegistry.size;
  }

  getMaterialCount(): number {
    return this.materials.size;
  }
}
