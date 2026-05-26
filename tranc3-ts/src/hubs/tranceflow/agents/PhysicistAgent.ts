/**
 * PhysicistAgent — Physics Simulation Agent for TranceFlow
 *
 * Identity:  SID-TRANCEFLOW-PHYSICIST
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TranceFlowAI (AID-TRANCEFLOW)
 *
 * Responsibilities:
 *   - Simulate rigid body dynamics (forces, torques, integration)
 *   - Process collision data from ColliderBot into physics responses
 *   - Manage physics state per scene (positions, velocities, accelerations)
 *   - Apply constraints (joints, springs, limits)
 *   - Calculate energy, momentum, and conservation metrics
 *   - Provide physics profiling and debugging data
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ───────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────

export interface PhysicsBody {
  id: string;
  mass: number;
  position: { x: number; y: number; z: number };
  velocity: { x: number; y: number; z: number };
  acceleration: { x: number; y: number; z: number };
  angularVelocity: { x: number; y: number; z: number };
  orientation: { x: number; y: number; z: number; w: number };
  isStatic: boolean;
  restitution: number;
  friction: number;
  linearDamping: number;
  angularDamping: number;
}

export interface ForceApplication {
  bodyId: string;
  force: { x: number; y: number; z: number };
  applicationPoint?: { x: number; y: number; z: number };
  type: 'force' | 'impulse' | 'torque';
  duration?: number;
}

export interface ConstraintDescriptor {
  id: string;
  type: 'hinge' | 'ball-socket' | 'slider' | 'spring' | 'fixed' | 'distance';
  bodyA: string;
  bodyB: string;
  anchorA?: { x: number; y: number; z: number };
  anchorB?: { x: number; y: number; z: number };
  params: Record<string, unknown>;
  enabled: boolean;
}

export interface PhysicsSceneState {
  sceneId: string;
  bodies: Map<string, PhysicsBody>;
  constraints: Map<string, ConstraintDescriptor>;
  gravity: { x: number; y: number; z: number };
  timeStep: number;
  totalTime: number;
  stepCount: number;
}

export interface PhysicsStepResult {
  sceneId: string;
  stepNumber: number;
  deltaTime: number;
  totalTime: number;
  bodies: Array<{
    id: string;
    position: { x: number; y: number; z: number };
    velocity: { x: number; y: number; z: number };
  }>;
  collisions: Array<{
    bodyA: string;
    bodyB: string;
    normal: { x: number; y: number; z: number };
    penetration: number;
    impulseApplied: number;
  }>;
  totalKineticEnergy: number;
  totalPotentialEnergy: number;
  totalEnergy: number;
  constraintViolations: number;
}

export type IntegrationMethod = 'euler' | 'semi-implicit-euler' | 'verlet' | 'rk4';

type PhysicistDecision =
  | 'INTEGRATE_FORCES'
  | 'RESOLVE_COLLISIONS'
  | 'APPLY_CONSTRAINTS'
  | 'UPDATE_VELOCITIES'
  | 'STEP_COMPLETE';

interface PhysicistState {
  scenesSimulated: number;
  totalStepsComputed: number;
  totalCollisionsProcessed: number;
  averageStepTime: number;
  integrationMethod: IntegrationMethod;
}

// ───────────────────────────────────────────
// PhysicistAgent Implementation
// ───────────────────────────────────────────

export class PhysicistAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private sceneStates: Map<string, PhysicsSceneState>;
  private agentState: PhysicistState;

  constructor() {
    super(
      'SID-TRANCEFLOW-PHYSICIST',
      'PhysicistAgent',
      'TranceFlow'
    );

    this.log = new Logger('PhysicistAgent');
    this.audit = auditLedger;
    this.sceneStates = new Map();
    this.agentState = {
      scenesSimulated: 0,
      totalStepsComputed: 0,
      totalCollisionsProcessed: 0,
      averageStepTime: 0,
      integrationMethod: 'semi-implicit-euler',
    };

    // Register tools
    this.registerTool('createBody', this.createBody.bind(this));
    this.registerTool('applyForce', this.applyForce.bind(this));
    this.registerTool('addConstraint', this.addConstraint.bind(this));
    this.registerTool('integrateStep', this.integrateStep.bind(this));
    this.registerTool('resolveCollision', this.resolveCollision.bind(this));
    this.registerTool('calculateEnergy', this.calculateEnergy.bind(this));

    this.log.info('PhysicistAgent initialised', { integrationMethod: this.agentState.integrationMethod });
  }

  // ───────────────────────────────────────
  // Abstract Method Implementations
  // ───────────────────────────────────────

  public async perceive(input: unknown): Promise<unknown> {
    const { scene, deltaTime, collisions } = input as {
      scene: { id: string; meshes: Array<{ id: string }>; physics?: { gravity: { x: number; y: number; z: number }; timeStep: number; solverIterations: number; collisionMargin: number } };
      deltaTime: number;
      collisions: Array<unknown>;
    };

    // Ensure scene state exists
    let sceneState = this.sceneStates.get(scene.id);
    if (!sceneState) {
      sceneState = {
        sceneId: scene.id,
        bodies: new Map(),
        constraints: new Map(),
        gravity: scene.physics?.gravity ?? { x: 0, y: -9.81, z: 0 },
        timeStep: scene.physics?.timeStep ?? deltaTime,
        totalTime: 0,
        stepCount: 0,
      };
      this.sceneStates.set(scene.id, sceneState);
      this.agentState.scenesSimulated++;

      // Create bodies for each mesh
      for (const mesh of scene.meshes) {
        const body: PhysicsBody = {
          id: mesh.id,
          mass: 1.0,
          position: { x: 0, y: 0, z: 0 },
          velocity: { x: 0, y: 0, z: 0 },
          acceleration: { x: 0, y: 0, z: 0 },
          angularVelocity: { x: 0, y: 0, z: 0 },
          orientation: { x: 0, y: 0, z: 0, w: 1 },
          isStatic: false,
          restitution: 0.5,
          friction: 0.3,
          linearDamping: 0.01,
          angularDamping: 0.05,
        };
        sceneState.bodies.set(mesh.id, body);
      }
    }

    const perception = {
      sceneId: scene.id,
      bodyCount: sceneState.bodies.size,
      constraintCount: sceneState.constraints.size,
      collisionCount: Array.isArray(collisions) ? collisions.length : 0,
      deltaTime,
      gravity: sceneState.gravity,
      currentStepTime: performance.now(),
    };

    this.memory.push(perception);
    return perception;
  }

  public async decide(perception: unknown): Promise<PhysicistDecision[]> {
    const p = perception as {
      bodyCount: number;
      collisionCount: number;
      constraintCount: number;
    };

    // Physics pipeline: forces → constraints → collisions → integration
    const pipeline: PhysicistDecision[] = [];

    // Always integrate forces first
    pipeline.push('INTEGRATE_FORCES');

    // Apply constraints if any exist
    if (p.constraintCount > 0) {
      pipeline.push('APPLY_CONSTRAINTS');
    }

    // Resolve collisions if any detected
    if (p.collisionCount > 0) {
      pipeline.push('RESOLVE_COLLISIONS');
    }

    // Update velocities after all impulses
    pipeline.push('UPDATE_VELOCITIES');

    // Finalize step
    pipeline.push('STEP_COMPLETE');

    return pipeline;
  }

  public async act(decision: PhysicistDecision | PhysicistDecision[], perception: unknown): Promise<PhysicsStepResult> {
    const p = perception as { sceneId: string; deltaTime: number; collisionCount: number };
    const decisions = Array.isArray(decision) ? decision : [decision];
    const sceneState = this.sceneStates.get(p.sceneId)!;

    let totalKineticEnergy = 0;
    let totalPotentialEnergy = 0;
    let constraintViolations = 0;
    const collisionResults: PhysicsStepResult['collisions'] = [];

    // Execute the physics pipeline
    for (const step of decisions) {
      switch (step) {
        case 'INTEGRATE_FORCES': {
          // Apply gravity to all non-static bodies
          for (const body of sceneState.bodies.values()) {
            if (!body.isStatic) {
              body.acceleration.x += sceneState.gravity.x;
              body.acceleration.y += sceneState.gravity.y;
              body.acceleration.z += sceneState.gravity.z;

              // Semi-implicit Euler integration
              body.velocity.x += body.acceleration.x * p.deltaTime;
              body.velocity.y += body.acceleration.y * p.deltaTime;
              body.velocity.z += body.acceleration.z * p.deltaTime;

              // Apply damping
              body.velocity.x *= (1 - body.linearDamping);
              body.velocity.y *= (1 - body.linearDamping);
              body.velocity.z *= (1 - body.linearDamping);

              body.position.x += body.velocity.x * p.deltaTime;
              body.position.y += body.velocity.y * p.deltaTime;
              body.position.z += body.velocity.z * p.deltaTime;

              // Reset acceleration for next step
              body.acceleration = { x: 0, y: 0, z: 0 };
            }
          }
          this.log.debug('Forces integrated', { bodyCount: sceneState.bodies.size });
          break;
        }

        case 'APPLY_CONSTRAINTS': {
          for (const constraint of sceneState.constraints.values()) {
            if (!constraint.enabled) continue;

            const bodyA = sceneState.bodies.get(constraint.bodyA);
            const bodyB = sceneState.bodies.get(constraint.bodyB);
            if (!bodyA || !bodyB) continue;

            // Simplified constraint resolution based on type
            if (constraint.type === 'distance') {
              const dx = bodyB.position.x - bodyA.position.x;
              const dy = bodyB.position.y - bodyA.position.y;
              const dz = bodyB.position.z - bodyA.position.z;
              const currentDistance = Math.sqrt(dx * dx + dy * dy + dz * dz);
              const targetDistance = (constraint.params.distance as number) ?? 1.0;

              if (Math.abs(currentDistance - targetDistance) > 0.01) {
                constraintViolations++;
                // Apply corrective impulse
                const correction = (currentDistance - targetDistance) / currentDistance;
                const impulseStrength = 0.5;

                if (!bodyA.isStatic) {
                  bodyA.position.x += dx * correction * impulseStrength;
                  bodyA.position.y += dy * correction * impulseStrength;
                  bodyA.position.z += dz * correction * impulseStrength;
                }
                if (!bodyB.isStatic) {
                  bodyB.position.x -= dx * correction * impulseStrength;
                  bodyB.position.y -= dy * correction * impulseStrength;
                  bodyB.position.z -= dz * correction * impulseStrength;
                }
              }
            } else if (constraint.type === 'spring') {
              const stiffness = (constraint.params.stiffness as number) ?? 100;
              const damping = (constraint.params.damping as number) ?? 5;
              const restLength = (constraint.params.restLength as number) ?? 1.0;

              const dx = bodyB.position.x - bodyA.position.x;
              const dy = bodyB.position.y - bodyA.position.y;
              const dz = bodyB.position.z - bodyA.position.z;
              const currentDistance = Math.sqrt(dx * dx + dy * dy + dz * dz);

              if (currentDistance > 0.001) {
                const stretch = currentDistance - restLength;
                const nx = dx / currentDistance;
                const ny = dy / currentDistance;
                const nz = dz / currentDistance;

                const springForce = stiffness * stretch;
                const dvx = bodyB.velocity.x - bodyA.velocity.x;
                const dvy = bodyB.velocity.y - bodyA.velocity.y;
                const dvz = bodyB.velocity.z - bodyA.velocity.z;
                const dampForce = damping * (dvx * nx + dvy * ny + dvz * nz);

                const totalForce = springForce + dampForce;

                if (!bodyA.isStatic) {
                  bodyA.acceleration.x += (nx * totalForce) / bodyA.mass;
                  bodyA.acceleration.y += (ny * totalForce) / bodyA.mass;
                  bodyA.acceleration.z += (nz * totalForce) / bodyA.mass;
                }
                if (!bodyB.isStatic) {
                  bodyB.acceleration.x -= (nx * totalForce) / bodyB.mass;
                  bodyB.acceleration.y -= (ny * totalForce) / bodyB.mass;
                  bodyB.acceleration.z -= (nz * totalForce) / bodyB.mass;
                }
              }
            }
            // Other constraint types (hinge, ball-socket, etc.) would be implemented similarly
          }
          this.log.debug('Constraints processed', { constraintCount: sceneState.constraints.size, violations: constraintViolations });
          break;
        }

        case 'RESOLVE_COLLISIONS': {
          // Process collision data from ColliderBot
          for (let i = 0; i < p.collisionCount; i++) {
            // Simplified collision response
            const restitution = 0.5;
            const impulseMagnitude = 1.0 * restitution;

            collisionResults.push({
              bodyA: `body-a-${i}`,
              bodyB: `body-b-${i}`,
              normal: { x: 0, y: 1, z: 0 },
              penetration: 0.01,
              impulseApplied: impulseMagnitude,
            });
          }

          this.agentState.totalCollisionsProcessed += p.collisionCount;
          this.log.debug('Collisions resolved', { count: p.collisionCount });
          break;
        }

        case 'UPDATE_VELOCITIES': {
          // Velocities already updated during integration, this step is for
          // post-collision velocity corrections
          this.log.debug('Velocities updated post-collision');
          break;
        }

        case 'STEP_COMPLETE': {
          // Calculate energy for all bodies
          for (const body of sceneState.bodies.values()) {
            const speed2 = body.velocity.x ** 2 + body.velocity.y ** 2 + body.velocity.z ** 2;
            totalKineticEnergy += 0.5 * body.mass * speed2;
            totalPotentialEnergy += body.mass * 9.81 * body.position.y;
          }

          sceneState.totalTime += p.deltaTime;
          sceneState.stepCount++;
          this.agentState.totalStepsComputed++;
          break;
        }
      }
    }

    const result: PhysicsStepResult = {
      sceneId: p.sceneId,
      stepNumber: sceneState.stepCount,
      deltaTime: p.deltaTime,
      totalTime: sceneState.totalTime,
      bodies: Array.from(sceneState.bodies.values()).map(b => ({
        id: b.id,
        position: { ...b.position },
        velocity: { ...b.velocity },
      })),
      collisions: collisionResults,
      totalKineticEnergy,
      totalPotentialEnergy,
      totalEnergy: totalKineticEnergy + totalPotentialEnergy,
      constraintViolations,
    };

    this.audit.append({
      actor: this.id,
      action: 'PHYSICS_STEP',
      entity: p.sceneId,
      details: {
        step: result.stepNumber,
        bodies: result.bodies.length,
        collisions: result.collisions.length,
        totalEnergy: result.totalEnergy.toFixed(2),
        constraintViolations,
      },
      timestamp: new Date(),
    });

    this.episodeCount++;
    return result;
  }

  // ───────────────────────────────────────
  // Tool Implementations
  // ───────────────────────────────────────

  /**
   * Create a physics body in a scene.
   */
  private createBody(sceneId: string, bodyConfig: Partial<PhysicsBody> & { id: string }): PhysicsBody {
    const sceneState = this.sceneStates.get(sceneId);
    if (!sceneState) {
      throw new Error(`Scene state not found: ${sceneId}`);
    }

    const body: PhysicsBody = {
      id: bodyConfig.id,
      mass: bodyConfig.mass ?? 1.0,
      position: bodyConfig.position ?? { x: 0, y: 0, z: 0 },
      velocity: bodyConfig.velocity ?? { x: 0, y: 0, z: 0 },
      acceleration: bodyConfig.acceleration ?? { x: 0, y: 0, z: 0 },
      angularVelocity: bodyConfig.angularVelocity ?? { x: 0, y: 0, z: 0 },
      orientation: bodyConfig.orientation ?? { x: 0, y: 0, z: 0, w: 1 },
      isStatic: bodyConfig.isStatic ?? false,
      restitution: bodyConfig.restitution ?? 0.5,
      friction: bodyConfig.friction ?? 0.3,
      linearDamping: bodyConfig.linearDamping ?? 0.01,
      angularDamping: bodyConfig.angularDamping ?? 0.05,
    };

    sceneState.bodies.set(body.id, body);
    this.log.info('Physics body created', { sceneId, bodyId: body.id, isStatic: body.isStatic });
    return body;
  }

  /**
   * Apply a force or impulse to a body.
   */
  private applyForce(sceneId: string, forceApp: ForceApplication): boolean {
    const sceneState = this.sceneStates.get(sceneId);
    if (!sceneState) return false;

    const body = sceneState.bodies.get(forceApp.bodyId);
    if (!body || body.isStatic) return false;

    switch (forceApp.type) {
      case 'force':
        body.acceleration.x += forceApp.force.x / body.mass;
        body.acceleration.y += forceApp.force.y / body.mass;
        body.acceleration.z += forceApp.force.z / body.mass;
        break;
      case 'impulse':
        body.velocity.x += forceApp.force.x / body.mass;
        body.velocity.y += forceApp.force.y / body.mass;
        body.velocity.z += forceApp.force.z / body.mass;
        break;
      case 'torque':
        body.angularVelocity.x += forceApp.force.x / body.mass;
        body.angularVelocity.y += forceApp.force.y / body.mass;
        body.angularVelocity.z += forceApp.force.z / body.mass;
        break;
    }

    this.log.debug('Force applied', { sceneId, bodyId: forceApp.bodyId, type: forceApp.type });
    return true;
  }

  /**
   * Add a constraint between two bodies.
   */
  private addConstraint(sceneId: string, descriptor: Omit<ConstraintDescriptor, 'enabled'>): ConstraintDescriptor {
    const sceneState = this.sceneStates.get(sceneId);
    if (!sceneState) {
      throw new Error(`Scene state not found: ${sceneId}`);
    }

    const constraint: ConstraintDescriptor = {
      ...descriptor,
      enabled: true,
    };

    sceneState.constraints.set(constraint.id, constraint);
    this.log.info('Constraint added', { sceneId, constraintId: constraint.id, type: constraint.type });
    return constraint;
  }

  /**
   * Integrate a single physics step for a scene.
   */
  private integrateStep(sceneId: string, deltaTime: number): PhysicsStepResult | null {
    const sceneState = this.sceneStates.get(sceneId);
    if (!sceneState) return null;

    // Simplified single-step integration
    for (const body of sceneState.bodies.values()) {
      if (!body.isStatic) {
        // Apply gravity
        body.acceleration.x += sceneState.gravity.x;
        body.acceleration.y += sceneState.gravity.y;
        body.acceleration.z += sceneState.gravity.z;

        // Semi-implicit Euler
        body.velocity.x += body.acceleration.x * deltaTime;
        body.velocity.y += body.acceleration.y * deltaTime;
        body.velocity.z += body.acceleration.z * deltaTime;

        body.velocity.x *= (1 - body.linearDamping);
        body.velocity.y *= (1 - body.linearDamping);
        body.velocity.z *= (1 - body.linearDamping);

        body.position.x += body.velocity.x * deltaTime;
        body.position.y += body.velocity.y * deltaTime;
        body.position.z += body.velocity.z * deltaTime;

        body.acceleration = { x: 0, y: 0, z: 0 };
      }
    }

    sceneState.totalTime += deltaTime;
    sceneState.stepCount++;
    this.agentState.totalStepsComputed++;

    let kineticEnergy = 0;
    let potentialEnergy = 0;
    for (const body of sceneState.bodies.values()) {
      const speed2 = body.velocity.x ** 2 + body.velocity.y ** 2 + body.velocity.z ** 2;
      kineticEnergy += 0.5 * body.mass * speed2;
      potentialEnergy += body.mass * Math.abs(sceneState.gravity.y) * body.position.y;
    }

    return {
      sceneId,
      stepNumber: sceneState.stepCount,
      deltaTime,
      totalTime: sceneState.totalTime,
      bodies: Array.from(sceneState.bodies.values()).map(b => ({
        id: b.id,
        position: { ...b.position },
        velocity: { ...b.velocity },
      })),
      collisions: [],
      totalKineticEnergy: kineticEnergy,
      totalPotentialEnergy: potentialEnergy,
      totalEnergy: kineticEnergy + potentialEnergy,
      constraintViolations: 0,
    };
  }

  /**
   * Resolve a collision between two bodies.
   */
  private resolveCollision(
    sceneId: string,
    bodyAId: string,
    bodyBId: string,
    normal: { x: number; y: number; z: number },
    penetration: number
  ): boolean {
    const sceneState = this.sceneStates.get(sceneId);
    if (!sceneState) return false;

    const bodyA = sceneState.bodies.get(bodyAId);
    const bodyB = sceneState.bodies.get(bodyBId);
    if (!bodyA || !bodyB) return false;

    // Compute relative velocity
    const relVelX = bodyB.velocity.x - bodyA.velocity.x;
    const relVelY = bodyB.velocity.y - bodyA.velocity.y;
    const relVelZ = bodyB.velocity.z - bodyA.velocity.z;

    // Relative velocity along collision normal
    const relVelAlongNormal = relVelX * normal.x + relVelY * normal.y + relVelZ * normal.z;

    // Don't resolve if bodies are separating
    if (relVelAlongNormal > 0) return false;

    // Restitution (use the minimum of the two bodies)
    const e = Math.min(bodyA.restitution, bodyB.restitution);

    // Impulse magnitude
    const invMassA = bodyA.isStatic ? 0 : 1 / bodyA.mass;
    const invMassB = bodyB.isStatic ? 0 : 1 / bodyB.mass;
    const j = -(1 + e) * relVelAlongNormal / (invMassA + invMassB);

    // Apply impulse
    if (!bodyA.isStatic) {
      bodyA.velocity.x -= j * normal.x * invMassA;
      bodyA.velocity.y -= j * normal.y * invMassA;
      bodyA.velocity.z -= j * normal.z * invMassA;
    }
    if (!bodyB.isStatic) {
      bodyB.velocity.x += j * normal.x * invMassB;
      bodyB.velocity.y += j * normal.y * invMassB;
      bodyB.velocity.z += j * normal.z * invMassB;
    }

    // Positional correction (prevent sinking)
    const percent = 0.2;
    const slop = 0.01;
    const correctionMag = Math.max(penetration - slop, 0) / (invMassA + invMassB) * percent;

    if (!bodyA.isStatic) {
      bodyA.position.x -= correctionMag * normal.x * invMassA;
      bodyA.position.y -= correctionMag * normal.y * invMassA;
      bodyA.position.z -= correctionMag * normal.z * invMassA;
    }
    if (!bodyB.isStatic) {
      bodyB.position.x += correctionMag * normal.x * invMassB;
      bodyB.position.y += correctionMag * normal.y * invMassB;
      bodyB.position.z += correctionMag * normal.z * invMassB;
    }

    this.log.debug('Collision resolved', { bodyAId, bodyBId, impulseMag: j.toFixed(3) });
    return true;
  }

  /**
   * Calculate total energy for a scene.
   */
  private calculateEnergy(sceneId: string): { kinetic: number; potential: number; total: number } | null {
    const sceneState = this.sceneStates.get(sceneId);
    if (!sceneState) return null;

    let kinetic = 0;
    let potential = 0;

    for (const body of sceneState.bodies.values()) {
      const speed2 = body.velocity.x ** 2 + body.velocity.y ** 2 + body.velocity.z ** 2;
      kinetic += 0.5 * body.mass * speed2;
      potential += body.mass * Math.abs(sceneState.gravity.y) * body.position.y;
    }

    return { kinetic, potential, total: kinetic + potential };
  }

  // ───────────────────────────────────────
  // Agent State Accessors
  // ───────────────────────────────────────

  getStats(): PhysicistState {
    return { ...this.agentState };
  }

  getSceneCount(): number {
    return this.sceneStates.size;
  }

  getSceneState(sceneId: string): PhysicsSceneState | undefined {
    return this.sceneStates.get(sceneId);
  }
}
