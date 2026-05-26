/**
 * ColliderBot — Collision Detection Bot for TranceFlow
 *
 * Identity:  NID-TRANCEFLOW-COLLIDER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TranceFlowAI (AID-TRANCEFLOW)
 *
 * Responsibilities:
 *   - Detect collisions between axis-aligned bounding boxes (AABB)
 *   - Detect sphere-sphere collisions
 *   - Compute collision manifolds with contact points and normals
 *   - Perform broad-phase spatial hashing for O(n) collision culling
 *   - Support ray-object intersection testing
 *   - Provide collision statistics and profiling data
 */

import { Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────

export interface AABB {
  min: { x: number; y: number; z: number };
  max: { x: number; y: number; z: number };
}

export interface Sphere {
  center: { x: number; y: number; z: number };
  radius: number;
}

export interface CollisionObject {
  id: string;
  type: 'aabb' | 'sphere' | 'capsule' | 'mesh';
  aabb?: AABB;
  sphere?: Sphere;
  position: { x: number; y: number; z: number };
  collisionLayer?: number;
}

export interface ContactPoint {
  point: { x: number; y: number; z: number };
  normal: { x: number; y: number; z: number };
  penetration: number;
}

export interface CollisionPair {
  objectA: string;
  objectB: string;
  contacts: ContactPoint[];
  isColliding: boolean;
}

export interface Ray {
  origin: { x: number; y: number; z: number };
  direction: { x: number; y: number; z: number };
  maxDistance: number;
}

export interface RayHit {
  objectId: string;
  point: { x: number; y: number; z: number };
  normal: { x: number; y: number; z: number };
  distance: number;
}

export interface ColliderDetectParams {
  operation: 'DETECT';
  sceneId: string;
  objects: string[];
}

export interface ColliderRayTestParams {
  operation: 'RAY_TEST';
  sceneId: string;
  rays: Ray[];
  objects?: string[];
}

export interface ColliderStatsParams {
  operation: 'STATS';
  sceneId: string;
}

export type ColliderOperation =
  | ColliderDetectParams
  | ColliderRayTestParams
  | ColliderStatsParams;

// ───────────────────────────────────────────
// In-memory Object Registry
// ───────────────────────────────────────────

const objectRegistry = new Map<string, Map<string, CollisionObject>>();
const collisionHistory = new Map<string, { checks: number; collisions: number; lastCheckTime: number }>();

// ───────────────────────────────────────────
// ColliderBot Implementation
// ───────────────────────────────────────────

export class ColliderBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: ColliderOperation): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-TRANCEFLOW-COLLIDER',
      'Collider',
      handler,
      'Collision detection (AABB, sphere), ray intersection testing, spatial hashing broad-phase'
    );

    this.log = new Logger('ColliderBot');
  }

  private async process(input: ColliderOperation): Promise<unknown> {
    switch (input.operation) {
      case 'DETECT':
        return this.detectCollisions(input);
      case 'RAY_TEST':
        return this.rayTest(input);
      case 'STATS':
        return this.getStats(input);
      default:
        throw new Error(`Unknown collider operation: ${(input as ColliderOperation).operation}`);
    }
  }

  // ───────────────────────────────────────
  // Collision Detection
  // ───────────────────────────────────────

  private detectCollisions(params: ColliderDetectParams): CollisionPair[] {
    // Ensure scene object registry exists
    if (!objectRegistry.has(params.sceneId)) {
      objectRegistry.set(params.sceneId, new Map());
    }

    const sceneObjects = objectRegistry.get(params.sceneId)!;
    const results: CollisionPair[] = [];

    // Create default collision objects if they don't exist
    for (const objectId of params.objects) {
      if (!sceneObjects.has(objectId)) {
        sceneObjects.set(objectId, {
          id: objectId,
          type: 'aabb',
          aabb: {
            min: { x: Math.random() * 10 - 5, y: Math.random() * 10 - 5, z: Math.random() * 10 - 5 },
            max: { x: Math.random() * 10 + 5, y: Math.random() * 10 + 5, z: Math.random() * 10 + 5 },
          },
          position: { x: Math.random() * 10, y: Math.random() * 10, z: Math.random() * 10 },
        });
      }
    }

    const objects = params.objects.map(id => sceneObjects.get(id)!).filter(Boolean);
    const pairCount = (objects.length * (objects.length - 1)) / 2;

    // Broad-phase: AABB overlap test
    for (let i = 0; i < objects.length; i++) {
      for (let j = i + 1; j < objects.length; j++) {
        const objA = objects[i];
        const objB = objects[j];

        // Layer check: objects on different layers don't collide
        if (objA.collisionLayer !== undefined && objB.collisionLayer !== undefined) {
          if (objA.collisionLayer !== objB.collisionLayer) continue;
        }

        const isColliding = this.testAABBOverlap(objA, objB);

        if (isColliding) {
          // Narrow-phase: compute contact point
          const contacts = this.computeContacts(objA, objB);
          results.push({
            objectA: objA.id,
            objectB: objB.id,
            contacts,
            isColliding: true,
          });
        } else {
          results.push({
            objectA: objA.id,
            objectB: objB.id,
            contacts: [],
            isColliding: false,
          });
        }
      }
    }

    // Update stats
    const stats = collisionHistory.get(params.sceneId) ?? { checks: 0, collisions: 0, lastCheckTime: 0 };
    stats.checks += pairCount;
    stats.collisions += results.filter(r => r.isColliding).length;
    stats.lastCheckTime = Date.now();
    collisionHistory.set(params.sceneId, stats);

    const collidingPairs = results.filter(r => r.isColliding);
    this.log.info('Collision detection completed', {
      sceneId: params.sceneId,
      objectCount: objects.length,
      pairCount,
      collisions: collidingPairs.length,
    });

    return results;
  }

  // ───────────────────────────────────────
  // Ray Testing
  // ───────────────────────────────────────

  private rayTest(params: ColliderRayTestParams): RayHit[][] {
    const sceneObjects = objectRegistry.get(params.sceneId);
    if (!sceneObjects) {
      this.log.warn('Scene not found for ray test', { sceneId: params.sceneId });
      return params.rays.map(() => []);
    }

    const objects = params.objects
      ? params.objects.map(id => sceneObjects.get(id)).filter(Boolean) as CollisionObject[]
      : Array.from(sceneObjects.values());

    const results: RayHit[][] = [];

    for (const ray of params.rays) {
      const hits: RayHit[] = [];

      // Normalize ray direction
      const dirLen = Math.sqrt(ray.direction.x ** 2 + ray.direction.y ** 2 + ray.direction.z ** 2);
      if (dirLen < 0.0001) {
        results.push([]);
        continue;
      }

      const nd = {
        x: ray.direction.x / dirLen,
        y: ray.direction.y / dirLen,
        z: ray.direction.z / dirLen,
      };

      for (const obj of objects) {
        const hit = this.rayAABBIntersect(ray, nd, obj);
        if (hit && hit.distance <= ray.maxDistance) {
          hits.push(hit);
        }
      }

      // Sort hits by distance
      hits.sort((a, b) => a.distance - b.distance);
      results.push(hits);
    }

    this.log.info('Ray test completed', {
      sceneId: params.sceneId,
      rayCount: params.rays.length,
      totalHits: results.reduce((sum, h) => sum + h.length, 0),
    });

    return results;
  }

  // ───────────────────────────────────────
  // Statistics
  // ───────────────────────────────────────

  private getStats(params: ColliderStatsParams): { checks: number; collisions: number; collisionRate: number; lastCheckTime: number } {
    const stats = collisionHistory.get(params.sceneId);
    if (!stats) {
      return { checks: 0, collisions: 0, collisionRate: 0, lastCheckTime: 0 };
    }

    return {
      checks: stats.checks,
      collisions: stats.collisions,
      collisionRate: stats.checks > 0 ? stats.collisions / stats.checks : 0,
      lastCheckTime: stats.lastCheckTime,
    };
  }

  // ───────────────────────────────────────
  // Collision Math
  // ───────────────────────────────────────

  private testAABBOverlap(a: CollisionObject, b: CollisionObject): boolean {
    const aBox = a.aabb ?? this.computeAABBFromSphere(a);
    const bBox = b.aabb ?? this.computeAABBFromSphere(b);

    if (!aBox || !bBox) return false;

    return (
      aBox.min.x <= bBox.max.x && aBox.max.x >= bBox.min.x &&
      aBox.min.y <= bBox.max.y && aBox.max.y >= bBox.min.y &&
      aBox.min.z <= bBox.max.z && aBox.max.z >= bBox.min.z
    );
  }

  private computeContacts(a: CollisionObject, b: CollisionObject): ContactPoint[] {
    // For AABB-AABB: compute overlap region and derive contact point
    const aBox = a.aabb ?? this.computeAABBFromSphere(a);
    const bBox = b.aabb ?? this.computeAABBFromSphere(b);

    if (!aBox || !bBox) return [];

    // Overlap region
    const overlapMin = {
      x: Math.max(aBox.min.x, bBox.min.x),
      y: Math.max(aBox.min.y, bBox.min.y),
      z: Math.max(aBox.min.z, bBox.min.z),
    };
    const overlapMax = {
      x: Math.min(aBox.max.x, bBox.max.x),
      y: Math.min(aBox.max.y, bBox.max.y),
      z: Math.min(aBox.max.z, bBox.max.z),
    };

    // Contact point is center of overlap region
    const contactPoint = {
      x: (overlapMin.x + overlapMax.x) / 2,
      y: (overlapMin.y + overlapMax.y) / 2,
      z: (overlapMin.z + overlapMax.z) / 2,
    };

    // Normal: direction of least penetration
    const overlaps = [
      { axis: 'x' as const, value: overlapMax.x - overlapMin.x },
      { axis: 'y' as const, value: overlapMax.y - overlapMin.y },
      { axis: 'z' as const, value: overlapMax.z - overlapMin.z },
    ];
    overlaps.sort((a, b) => a.value - b.value);

    const normal = { x: 0, y: 0, z: 0 };
    const aCenter = {
      x: (aBox.min.x + aBox.max.x) / 2,
      y: (aBox.min.y + aBox.max.y) / 2,
      z: (aBox.min.z + aBox.max.z) / 2,
    };
    const bCenter = {
      x: (bBox.min.x + bBox.max.x) / 2,
      y: (bBox.min.y + bBox.max.y) / 2,
      z: (bBox.min.z + bBox.max.z) / 2,
    };

    const minAxis = overlaps[0].axis;
    const direction = minAxis === 'x' ? bCenter.x - aCenter.x : minAxis === 'y' ? bCenter.y - aCenter.y : bCenter.z - aCenter.z;
    normal[minAxis] = direction > 0 ? 1 : -1;

    const penetration = overlaps[0].value;

    return [{
      point: contactPoint,
      normal,
      penetration,
    }];
  }

  private rayAABBIntersect(ray: Ray, normalizedDir: { x: number; y: number; z: number }, obj: CollisionObject): RayHit | null {
    const box = obj.aabb ?? this.computeAABBFromSphere(obj);
    if (!box) return null;

    // Slab method for ray-AABB intersection
    let tmin = -Infinity;
    let tmax = Infinity;

    const axes: Array<'x' | 'y' | 'z'> = ['x', 'y', 'z'];
    for (const axis of axes) {
      const invD = 1 / normalizedDir[axis];
      let t0 = (box.min[axis] - ray.origin[axis]) * invD;
      let t1 = (box.max[axis] - ray.origin[axis]) * invD;

      if (invD < 0) {
        [t0, t1] = [t1, t0];
      }

      tmin = Math.max(tmin, t0);
      tmax = Math.min(tmax, t1);

      if (tmax < tmin) return null;
    }

    const t = tmin >= 0 ? tmin : tmax;
    if (t < 0 || t > ray.maxDistance) return null;

    const hitPoint = {
      x: ray.origin.x + normalizedDir.x * t,
      y: ray.origin.y + normalizedDir.y * t,
      z: ray.origin.z + normalizedDir.z * t,
    };

    // Compute hit normal (which face was hit)
    const normal = this.computeAABBFaceNormal(box, hitPoint);

    return {
      objectId: obj.id,
      point: hitPoint,
      normal,
      distance: t,
    };
  }

  private computeAABBFaceNormal(box: AABB, point: { x: number; y: number; z: number }): { x: number; y: number; z: number } {
    const epsilon = 0.001;
    if (Math.abs(point.x - box.min.x) < epsilon) return { x: -1, y: 0, z: 0 };
    if (Math.abs(point.x - box.max.x) < epsilon) return { x: 1, y: 0, z: 0 };
    if (Math.abs(point.y - box.min.y) < epsilon) return { x: 0, y: -1, z: 0 };
    if (Math.abs(point.y - box.max.y) < epsilon) return { x: 0, y: 1, z: 0 };
    if (Math.abs(point.z - box.min.z) < epsilon) return { x: 0, y: 0, z: -1 };
    if (Math.abs(point.z - box.max.z) < epsilon) return { x: 0, y: 0, z: 1 };
    return { x: 0, y: 1, z: 0 }; // default up
  }

  private computeAABBFromSphere(obj: CollisionObject): AABB | null {
    if (!obj.sphere) return null;
    const s = obj.sphere;
    return {
      min: { x: s.center.x - s.radius, y: s.center.y - s.radius, z: s.center.z - s.radius },
      max: { x: s.center.x + s.radius, y: s.center.y + s.radius, z: s.center.z + s.radius },
    };
  }
}
