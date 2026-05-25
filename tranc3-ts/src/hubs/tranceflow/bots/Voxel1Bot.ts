/**
 * Voxel1Bot — Voxel Processing Bot for TranceFlow
 *
 * Identity:  NID-TRANCEFLOW-VOXEL1
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TranceFlowAI (AID-TRANCEFLOW)
 *
 * Responsibilities:
 *   - Create and initialize voxel grids of arbitrary dimensions
 *   - Fill voxel regions with density values (scalar fields)
 *   - Sample voxel data at specific coordinates (trilinear interpolation)
 *   - Compute basic statistics over voxel data (min, max, mean, occupied ratio)
 *   - Apply morphological operations (dilate, erode, smooth)
 *   - Export voxel data in various formats (raw, binary, sparse)
 */

import { Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────

export interface VoxelCreateParams {
  operation: 'CREATE';
  dimensions: { x: number; y: number; z: number };
  resolution: number;
}

export interface VoxelFillParams {
  operation: 'FILL';
  gridId: string;
  region: {
    min: { x: number; y: number; z: number };
    max: { x: number; y: number; z: number };
  };
  density: number;
}

export interface VoxelSampleParams {
  operation: 'SAMPLE';
  gridId: string;
  coordinates: Array<{ x: number; y: number; z: number }>;
  interpolation?: 'nearest' | 'trilinear';
}

export interface VoxelStatsParams {
  operation: 'STATS';
  gridId: string;
  region?: {
    min: { x: number; y: number; z: number };
    max: { x: number; y: number; z: number };
  };
}

export interface VoxelMorphParams {
  operation: 'MORPH';
  gridId: string;
  morphType: 'dilate' | 'erode' | 'smooth';
  iterations: number;
  threshold?: number;
}

export interface VoxelExportParams {
  operation: 'EXPORT';
  gridId: string;
  format: 'raw' | 'binary' | 'sparse';
  threshold?: number;
}

export type VoxelOperation =
  | VoxelCreateParams
  | VoxelFillParams
  | VoxelSampleParams
  | VoxelStatsParams
  | VoxelMorphParams
  | VoxelExportParams;

export interface VoxelStatsResult {
  min: number;
  max: number;
  mean: number;
  occupiedVoxels: number;
  totalVoxels: number;
  occupancyRatio: number;
  centroid: { x: number; y: number; z: number };
}

export interface VoxelExportResult {
  format: string;
  sizeBytes: number;
  entries: number;
  compressed: boolean;
}

// ───────────────────────────────────────────
// In-memory Voxel Grid Storage (shared across operations)
// ───────────────────────────────────────────

const voxelGrids = new Map<string, {
  dimensions: { x: number; y: number; z: number };
  resolution: number;
  data: Float32Array;
}>();

// ───────────────────────────────────────────
// Voxel1Bot Implementation
// ───────────────────────────────────────────

export class Voxel1Bot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: VoxelOperation): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-TRANCEFLOW-VOXEL1',
      'Voxel1',
      handler,
      'Voxel grid creation, filling, sampling, statistics, morphological operations, and export'
    );

    this.log = new Logger('Voxel1Bot');
  }

  private async process(input: VoxelOperation): Promise<unknown> {
    switch (input.operation) {
      case 'CREATE':
        return this.createGrid(input);
      case 'FILL':
        return this.fillRegion(input);
      case 'SAMPLE':
        return this.samplePoints(input);
      case 'STATS':
        return this.computeStats(input);
      case 'MORPH':
        return this.applyMorphology(input);
      case 'EXPORT':
        return this.exportGrid(input);
      default:
        throw new Error(`Unknown voxel operation: ${(input as VoxelOperation).operation}`);
    }
  }

  // ───────────────────────────────────────
  // Operation Implementations
  // ───────────────────────────────────────

  private createGrid(params: VoxelCreateParams): { gridId: string; dimensions: { x: number; y: number; z: number }; resolution: number; totalVoxels: number } {
    const { dimensions, resolution } = params;
    const totalVoxels = dimensions.x * dimensions.y * dimensions.z;
    const data = new Float32Array(totalVoxels); // initialized to 0.0

    const gridId = `VOXEL-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();
    voxelGrids.set(gridId, { dimensions, resolution, data });

    this.log.info('Voxel grid created', { gridId, dimensions, resolution, totalVoxels });
    return { gridId, dimensions, resolution, totalVoxels };
  }

  private fillRegion(params: VoxelFillParams): { gridId: string; voxelsFilled: number; density: number } {
    const grid = voxelGrids.get(params.gridId);
    if (!grid) {
      throw new Error(`Voxel grid not found: ${params.gridId}`);
    }

    let voxelsFilled = 0;
    const { min, max } = params.region;

    for (let z = Math.max(0, min.z); z < Math.min(grid.dimensions.z, max.z); z++) {
      for (let y = Math.max(0, min.y); y < Math.min(grid.dimensions.y, max.y); y++) {
        for (let x = Math.max(0, min.x); x < Math.min(grid.dimensions.x, max.x); x++) {
          const idx = x + y * grid.dimensions.x + z * grid.dimensions.x * grid.dimensions.y;
          if (idx >= 0 && idx < grid.data.length) {
            grid.data[idx] = params.density;
            voxelsFilled++;
          }
        }
      }
    }

    this.log.info('Voxel region filled', { gridId: params.gridId, voxelsFilled, density: params.density });
    return { gridId: params.gridId, voxelsFilled, density: params.density };
  }

  private samplePoints(params: VoxelSampleParams): Array<{ x: number; y: number; z: number; value: number }> {
    const grid = voxelGrids.get(params.gridId);
    if (!grid) {
      throw new Error(`Voxel grid not found: ${params.gridId}`);
    }

    const interpolation = params.interpolation ?? 'trilinear';
    const results: Array<{ x: number; y: number; z: number; value: number }> = [];

    for (const coord of params.coordinates) {
      let value: number;

      if (interpolation === 'nearest') {
        const ix = Math.round(coord.x);
        const iy = Math.round(coord.y);
        const iz = Math.round(coord.z);

        if (ix < 0 || ix >= grid.dimensions.x || iy < 0 || iy >= grid.dimensions.y || iz < 0 || iz >= grid.dimensions.z) {
          value = 0;
        } else {
          const idx = ix + iy * grid.dimensions.x + iz * grid.dimensions.x * grid.dimensions.y;
          value = grid.data[idx] ?? 0;
        }
      } else {
        // Trilinear interpolation
        value = this.trilinearInterpolate(grid, coord.x, coord.y, coord.z);
      }

      results.push({ x: coord.x, y: coord.y, z: coord.z, value });
    }

    this.log.debug('Voxel sampling completed', { gridId: params.gridId, pointCount: params.coordinates.length, interpolation });
    return results;
  }

  private computeStats(params: VoxelStatsParams): VoxelStatsResult {
    const grid = voxelGrids.get(params.gridId);
    if (!grid) {
      throw new Error(`Voxel grid not found: ${params.gridId}`);
    }

    let min = Infinity;
    let max = -Infinity;
    let sum = 0;
    let occupiedVoxels = 0;
    let centroidX = 0;
    let centroidY = 0;
    let centroidZ = 0;

    const threshold = 0.0; // occupancy threshold
    const xStart = params.region?.min.x ?? 0;
    const xEnd = params.region?.max.x ?? grid.dimensions.x;
    const yStart = params.region?.min.y ?? 0;
    const yEnd = params.region?.max.y ?? grid.dimensions.y;
    const zStart = params.region?.min.z ?? 0;
    const zEnd = params.region?.max.z ?? grid.dimensions.z;

    let totalInRegion = 0;

    for (let z = zStart; z < zEnd; z++) {
      for (let y = yStart; y < yEnd; y++) {
        for (let x = xStart; x < xEnd; x++) {
          const idx = x + y * grid.dimensions.x + z * grid.dimensions.x * grid.dimensions.y;
          if (idx < 0 || idx >= grid.data.length) continue;

          const val = grid.data[idx];
          totalInRegion++;

          if (val < min) min = val;
          if (val > max) max = val;
          sum += val;

          if (val > threshold) {
            occupiedVoxels++;
            centroidX += x * val;
            centroidY += y * val;
            centroidZ += z * val;
          }
        }
      }
    }

    const totalVoxels = totalInRegion || 1;
    const totalMass = sum || 1;

    const result: VoxelStatsResult = {
      min: min === Infinity ? 0 : min,
      max: max === -Infinity ? 0 : max,
      mean: sum / totalVoxels,
      occupiedVoxels,
      totalVoxels,
      occupancyRatio: occupiedVoxels / totalVoxels,
      centroid: {
        x: centroidX / totalMass,
        y: centroidY / totalMass,
        z: centroidZ / totalMass,
      },
    };

    this.log.info('Voxel stats computed', { gridId: params.gridId, occupancyRatio: result.occupancyRatio.toFixed(3) });
    return result;
  }

  private applyMorphology(params: VoxelMorphParams): { gridId: string; morphType: string; iterations: number; voxelsAffected: number } {
    const grid = voxelGrids.get(params.gridId);
    if (!grid) {
      throw new Error(`Voxel grid not found: ${params.gridId}`);
    }

    const threshold = params.threshold ?? 0.5;
    let voxelsAffected = 0;

    for (let iter = 0; iter < params.iterations; iter++) {
      const sourceData = new Float32Array(grid.data);

      for (let z = 1; z < grid.dimensions.z - 1; z++) {
        for (let y = 1; y < grid.dimensions.y - 1; y++) {
          for (let x = 1; x < grid.dimensions.x - 1; x++) {
            const idx = x + y * grid.dimensions.x + z * grid.dimensions.x * grid.dimensions.y;
            const current = sourceData[idx];

            // Get 6-connected neighbors
            const neighbors = [
              sourceData[idx - 1],
              sourceData[idx + 1],
              sourceData[idx - grid.dimensions.x],
              sourceData[idx + grid.dimensions.x],
              sourceData[idx - grid.dimensions.x * grid.dimensions.y],
              sourceData[idx + grid.dimensions.x * grid.dimensions.y],
            ];
            const avgNeighbor = neighbors.reduce((a, b) => a + b, 0) / neighbors.length;

            switch (params.morphType) {
              case 'dilate':
                if (current < threshold && avgNeighbor > threshold) {
                  grid.data[idx] = avgNeighbor;
                  voxelsAffected++;
                }
                break;
              case 'erode':
                if (current > threshold && avgNeighbor < threshold) {
                  grid.data[idx] = avgNeighbor;
                  voxelsAffected++;
                }
                break;
              case 'smooth':
                grid.data[idx] = current * 0.5 + avgNeighbor * 0.5;
                if (Math.abs(grid.data[idx] - current) > 0.01) voxelsAffected++;
                break;
            }
          }
        }
      }
    }

    this.log.info('Morphological operation applied', {
      gridId: params.gridId,
      morphType: params.morphType,
      iterations: params.iterations,
      voxelsAffected,
    });

    return { gridId: params.gridId, morphType: params.morphType, iterations: params.iterations, voxelsAffected };
  }

  private exportGrid(params: VoxelExportParams): VoxelExportResult {
    const grid = voxelGrids.get(params.gridId);
    if (!grid) {
      throw new Error(`Voxel grid not found: ${params.gridId}`);
    }

    const threshold = params.threshold ?? 0.0;

    switch (params.format) {
      case 'raw': {
        const sizeBytes = grid.data.byteLength;
        return { format: 'raw', sizeBytes, entries: grid.data.length, compressed: false };
      }
      case 'binary': {
        const sizeBytes = grid.data.byteLength;
        return { format: 'binary', sizeBytes, entries: grid.data.length, compressed: false };
      }
      case 'sparse': {
        let entries = 0;
        for (let i = 0; i < grid.data.length; i++) {
          if (grid.data[i] > threshold) entries++;
        }
        // Sparse format: 4 bytes per coordinate (x,y,z) + 4 bytes per value = 16 bytes per entry
        const sizeBytes = entries * 16;
        return { format: 'sparse', sizeBytes, entries, compressed: false };
      }
      default:
        throw new Error(`Unknown export format: ${params.format}`);
    }
  }

  // ───────────────────────────────────────
  // Helpers
  // ───────────────────────────────────────

  private trilinearInterpolate(
    grid: { dimensions: { x: number; y: number; z: number }; data: Float32Array },
    x: number, y: number, z: number
  ): number {
    const x0 = Math.floor(x);
    const y0 = Math.floor(y);
    const z0 = Math.floor(z);
    const x1 = x0 + 1;
    const y1 = y0 + 1;
    const z1 = z0 + 1;

    // Check bounds
    if (x0 < 0 || x1 >= grid.dimensions.x || y0 < 0 || y1 >= grid.dimensions.y || z0 < 0 || z1 >= grid.dimensions.z) {
      return 0;
    }

    const dx = x - x0;
    const dy = y - y0;
    const dz = z - z0;

    const idx = (ix: number, iy: number, iz: number) =>
      ix + iy * grid.dimensions.x + iz * grid.dimensions.x * grid.dimensions.y;

    const c000 = grid.data[idx(x0, y0, z0)];
    const c100 = grid.data[idx(x1, y0, z0)];
    const c010 = grid.data[idx(x0, y1, z0)];
    const c110 = grid.data[idx(x1, y1, z0)];
    const c001 = grid.data[idx(x0, y0, z1)];
    const c101 = grid.data[idx(x1, y0, z1)];
    const c011 = grid.data[idx(x0, y1, z1)];
    const c111 = grid.data[idx(x1, y1, z1)];

    // Trilinear interpolation
    const c00 = c000 * (1 - dx) + c100 * dx;
    const c01 = c001 * (1 - dx) + c101 * dx;
    const c10 = c010 * (1 - dx) + c110 * dx;
    const c11 = c011 * (1 - dx) + c111 * dx;

    const c0 = c00 * (1 - dy) + c10 * dy;
    const c1 = c01 * (1 - dy) + c11 * dy;

    return c0 * (1 - dz) + c1 * dz;
  }
}
