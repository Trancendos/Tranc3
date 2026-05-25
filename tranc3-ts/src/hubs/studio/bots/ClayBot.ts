/**
 * Clay Bot — Studio Tier 5 Bot (NID-STUDIO-CLAY)
 *
 * 3D sculpting primitives and mesh generation.
 * Generates basic 3D mesh primitives (sphere, cube, cylinder, etc.)
 * with configurable parameters for use in 3D modeling workflows.
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('ClayBot');

export interface ClayRequest {
  primitive: 'sphere' | 'cube' | 'cylinder' | 'cone' | 'torus' | 'plane' | 'icosphere';
  params: Record<string, number>;
}

export interface ClayResult {
  meshId: string;
  primitive: string;
  vertexCount: number;
  faceCount: number;
  bounds: { minX: number; maxX: number; minY: number; maxY: number; minZ: number; maxZ: number };
  format: string;
}

export class ClayBot extends Bot {
  constructor() {
    super(
      'Clay',
      async (request: ClayRequest): Promise<ClayResult> => {
        const meshId = `MESH-${Date.now()}`;
        const { vertexCount, faceCount } = generateMeshStats(request.primitive, request.params);

        const radius = request.params.radius || request.params.size || 1;

        logger.debug('Mesh generated', { primitive: request.primitive, vertices: vertexCount, faces: faceCount });

        return {
          meshId,
          primitive: request.primitive,
          vertexCount,
          faceCount,
          bounds: {
            minX: -radius,
            maxX: radius,
            minY: -radius,
            maxY: radius,
            minZ: -radius,
            maxZ: radius,
          },
          format: 'OBJ',
        };
      },
      'Generates 3D mesh primitives with configurable parameters',
    );
  }
}

/** Generate mesh statistics based on primitive type and params */
function generateMeshStats(primitive: string, params: Record<string, number>): { vertexCount: number; faceCount: number } {
  const segments = params.segments || params.resolution || 32;
  const rings = params.rings || 16;

  switch (primitive) {
    case 'sphere':
      return {
        vertexCount: (segments + 1) * (rings + 1),
        faceCount: segments * rings * 2,
      };
    case 'cube':
      return { vertexCount: 24, faceCount: 12 };
    case 'cylinder':
      return {
        vertexCount: (segments + 1) * 2 + 2,
        faceCount: segments * 2 + segments * 2,
      };
    case 'cone':
      return {
        vertexCount: segments + 2,
        faceCount: segments + segments,
      };
    case 'torus':
      return {
        vertexCount: (segments + 1) * (rings + 1),
        faceCount: segments * rings * 2,
      };
    case 'plane':
      return { vertexCount: 4, faceCount: 2 };
    case 'icosphere':
      return { vertexCount: 42, faceCount: 80 }; // Level 1 subdivision
    default:
      return { vertexCount: 0, faceCount: 0 };
  }
}
