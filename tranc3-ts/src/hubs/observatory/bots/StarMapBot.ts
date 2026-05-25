/**
 * StarMapBot — Celestial Pattern Plotting Bot for The Observatory
 *
 * Identity:  NID-OBSERVATORY-STARMAP
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheObservatoryAI (AID-OBSERVATORY)
 *
 * Responsibilities:
 *   - PLOT: Map celestial patterns and entity relationships onto a star chart
 *   - Calculate positional data, gravitational influences, and trajectories
 *   - Identify pattern formations: convergence, divergence, alignment, etc.
 *   - Generate star chart coordinates for visualisation
 *   - Track pattern evolution and entity movement over time
 *
 * "Every entity is a star. The StarMap reveals the constellation they form."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface StarMapInput {
  operation: 'PLOT';
  patternType: 'convergence' | 'divergence' | 'eclipse' | 'alignment' | 'nova' | 'void';
  entities: string[];
  timeframe?: 'current' | 'historical' | 'projected';
  resolution?: 'coarse' | 'standard' | 'fine' | 'ultra';
  coordinateSystem?: 'cartesian' | 'polar' | 'celestial';
}

export interface CelestialCoordinate {
  entity: string;
  x: number;
  y: number;
  z: number;
  rightAscension?: number;
  declination?: number;
  magnitude: number;
  spectralClass: string;
  velocity: { dx: number; dy: number; dz: number };
  distance: number;
  influence: number;
}

export interface ConstellationLink {
  from: string;
  to: string;
  strength: number;
  type: 'gravitational' | 'electromagnetic' | 'temporal' | 'informational';
  distance: number;
  latency: number;
}

export interface PatternFormation {
  type: StarMapInput['patternType'];
  entities: string[];
  centreOfMass: { x: number; y: number; z: number };
  radius: number;
  intensity: number;
  stability: number;
  projectedEvolution: 'forming' | 'stable' | 'dissipating' | 'intensifying';
  timeToPeak: number;
  confidence: number;
}

export interface StarChart {
  id: string;
  name: string;
  epoch: string;
  coordinates: CelestialCoordinate[];
  links: ConstellationLink[];
  patterns: PatternFormation[];
  bounds: { minX: number; maxX: number; minY: number; maxY: number; minZ: number; maxZ: number };
  totalEntities: number;
  totalLinks: number;
  density: number;
  timestamp: number;
}

export interface PlotResult {
  success: boolean;
  chart: StarChart;
  dominantPattern: PatternFormation | null;
  entityPositions: Record<string, CelestialCoordinate>;
  patternAnalysis: {
    strongestPattern: string;
    patternCount: number;
    entityCoverage: number;
    gravitationalCentre: { x: number; y: number; z: number };
    averageInfluence: number;
    networkDensity: number;
  };
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Simulated Entity Registry
// ─────────────────────────────────────────────────────────────────────────────

const ENTITY_REGISTRY: Record<string, {
  basePosition: { x: number; y: number; z: number };
  magnitude: number;
  spectralClass: string;
  baseInfluence: number;
}> = {
  'arcadia-hub':     { basePosition: { x: 0, y: 0, z: 0 }, magnitude: 1.0, spectralClass: 'G2V', baseInfluence: 95 },
  'luminous-hub':    { basePosition: { x: 50, y: 30, z: 10 }, magnitude: 0.8, spectralClass: 'F5V', baseInfluence: 80 },
  'townhall-hub':    { basePosition: { x: -30, y: 50, z: -5 }, magnitude: 0.6, spectralClass: 'K3V', baseInfluence: 65 },
  'studio-hub':      { basePosition: { x: 40, y: -20, z: 15 }, magnitude: 0.5, spectralClass: 'M2V', baseInfluence: 50 },
  'sashas-hub':      { basePosition: { x: 60, y: 10, z: -10 }, magnitude: 0.4, spectralClass: 'A1V', baseInfluence: 45 },
  'tranceflow-hub':  { basePosition: { x: -50, y: -30, z: 20 }, magnitude: 0.7, spectralClass: 'B8V', baseInfluence: 60 },
  'tateking-hub':    { basePosition: { x: 20, y: -50, z: -15 }, magnitude: 0.5, spectralClass: 'G8V', baseInfluence: 55 },
  'fabulousa-hub':   { basePosition: { x: -40, y: 20, z: 5 }, magnitude: 0.4, spectralClass: 'F2V', baseInfluence: 40 },
  'docutari-hub':    { basePosition: { x: 30, y: 40, z: -20 }, magnitude: 0.6, spectralClass: 'K7V', baseInfluence: 55 },
  'basement-hub':    { basePosition: { x: -60, y: -40, z: 25 }, magnitude: 0.3, spectralClass: 'M5V', baseInfluence: 30 },
  'imaginarium-hub': { basePosition: { x: 70, y: -10, z: 30 }, magnitude: 0.7, spectralClass: 'O9V', baseInfluence: 70 },
  'digitalgrid-hub': { basePosition: { x: -20, y: 60, z: -30 }, magnitude: 0.5, spectralClass: 'A5V', baseInfluence: 55 },
  'lab-hub':         { basePosition: { x: 10, y: -60, z: 10 }, magnitude: 0.6, spectralClass: 'G5V', baseInfluence: 60 },
  'workshop-hub':    { basePosition: { x: -45, y: -15, z: -25 }, magnitude: 0.5, spectralClass: 'K1V', baseInfluence: 50 },
  'chaosparty-hub':  { basePosition: { x: 55, y: 45, z: 15 }, magnitude: 0.4, spectralClass: 'B3V', baseInfluence: 40 },
  'artifactory-hub': { basePosition: { x: -10, y: -45, z: 20 }, magnitude: 0.5, spectralClass: 'F8V', baseInfluence: 50 },
  'apimarketplace-hub': { basePosition: { x: 25, y: 15, z: -5 }, magnitude: 0.6, spectralClass: 'A3V', baseInfluence: 55 },
  'royalbank-hub':   { basePosition: { x: -35, y: 35, z: -10 }, magnitude: 0.8, spectralClass: 'G0V', baseInfluence: 75 },
  'arcadianexchange-hub': { basePosition: { x: 15, y: 25, z: 10 }, magnitude: 0.9, spectralClass: 'F0V', baseInfluence: 85 },
  'observatory-hub': { basePosition: { x: 0, y: 70, z: 0 }, magnitude: 1.0, spectralClass: 'B0V', baseInfluence: 90 },
};

let chartCounter = 0;

// ─────────────────────────────────────────────────────────────────────────────
// StarMapBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class StarMapBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-OBSERVATORY-STARMAP',
      'StarMap',
      async (input: StarMapInput) => this.handle(input),
      'Celestial pattern plotting with coordinate mapping and constellation analysis'
    );

    this.log = new Logger('StarMapBot');
    this.audit = AuditLedger.getInstance();
  }

  private async handle(input: StarMapInput): Promise<PlotResult> {
    if (input.operation !== 'PLOT') {
      return this.fail(`Unknown operation: ${input.operation}. StarMapBot only accepts PLOT.`);
    }
    return this.plot(input);
  }

  // ───────────────────────────────────────────────────────────────────────
  // PLOT — Generate star chart
  // ───────────────────────────────────────────────────────────────────────

  private plot(input: StarMapInput): PlotResult {
    const { patternType, entities, timeframe, resolution, coordinateSystem } = input;

    if (!entities || entities.length === 0) {
      return this.fail('At least one entity is required for plotting');
    }

    // Resolve entities — if 'all' is specified, use all registered entities
    const resolvedEntities = entities.includes('all-hubs')
      ? Object.keys(ENTITY_REGISTRY)
      : entities;

    const timeFactor = timeframe === 'historical' ? -1 : timeframe === 'projected' ? 1 : 0;
    const resMultiplier = resolution === 'ultra' ? 0.01 : resolution === 'fine' ? 0.05 : resolution === 'standard' ? 0.1 : 0.25;

    // Calculate celestial coordinates for each entity
    const coordinates: CelestialCoordinate[] = [];
    const entityPositions: Record<string, CelestialCoordinate> = {};

    for (const entity of resolvedEntities) {
      const reg = ENTITY_REGISTRY[entity] ?? {
        basePosition: { x: Math.random() * 100 - 50, y: Math.random() * 100 - 50, z: Math.random() * 50 - 25 },
        magnitude: 0.5,
        spectralClass: 'G2V',
        baseInfluence: 50,
      };

      // Apply temporal drift
      const drift = timeFactor * 5 * resMultiplier;
      const x = Math.round((reg.basePosition.x + drift + (Math.random() - 0.5) * 2 * resMultiplier) * 100) / 100;
      const y = Math.round((reg.basePosition.y + drift * 0.7 + (Math.random() - 0.5) * 2 * resMultiplier) * 100) / 100;
      const z = Math.round((reg.basePosition.z + drift * 0.3 + (Math.random() - 0.5) * 1 * resMultiplier) * 100) / 100;

      const distance = Math.round(Math.sqrt(x * x + y * y + z * z) * 100) / 100;
      const rightAscension = Math.round((Math.atan2(y, x) * 180 / Math.PI + 360) % 360 * 100) / 100;
      const declination = Math.round((Math.asin(z / Math.max(distance, 0.01)) * 180 / Math.PI) * 100) / 100;

      const coord: CelestialCoordinate = {
        entity,
        x, y, z,
        rightAscension,
        declination,
        magnitude: reg.magnitude,
        spectralClass: reg.spectralClass,
        velocity: {
          dx: Math.round((Math.random() - 0.5) * 5 * 100) / 100,
          dy: Math.round((Math.random() - 0.5) * 5 * 100) / 100,
          dz: Math.round((Math.random() - 0.5) * 2 * 100) / 100,
        },
        distance,
        influence: Math.round((reg.baseInfluence * (0.9 + Math.random() * 0.2)) * 100) / 100,
      };

      coordinates.push(coord);
      entityPositions[entity] = coord;
    }

    // Generate constellation links between entities
    const links: ConstellationLink[] = [];
    for (let i = 0; i < coordinates.length; i++) {
      for (let j = i + 1; j < coordinates.length; j++) {
        const a = coordinates[i];
        const b = coordinates[j];
        const dist = Math.sqrt(
          Math.pow(a.x - b.x, 2) +
          Math.pow(a.y - b.y, 2) +
          Math.pow(a.z - b.z, 2)
        );

        // Only link entities within reasonable proximity
        if (dist < 100) {
          const strength = Math.round((1 - dist / 100) * 100) / 100;
          const linkTypes: ConstellationLink['type'][] = ['gravitational', 'electromagnetic', 'temporal', 'informational'];

          links.push({
            from: a.entity,
            to: b.entity,
            strength,
            type: linkTypes[Math.floor(Math.random() * linkTypes.length)],
            distance: Math.round(dist * 100) / 100,
            latency: Math.round(dist * 2.5 * 100) / 100, // Simulated latency based on distance
          });
        }
      }
    }

    // Generate pattern formations
    const patterns: PatternFormation[] = [];
    if (resolvedEntities.length >= 2) {
      const formation = this.calculatePatternFormation(patternType, coordinates);
      patterns.push(formation);
    }

    // Calculate chart bounds
    const bounds = {
      minX: Math.min(...coordinates.map(c => c.x)),
      maxX: Math.max(...coordinates.map(c => c.x)),
      minY: Math.min(...coordinates.map(c => c.y)),
      maxY: Math.max(...coordinates.map(c => c.y)),
      minZ: Math.min(...coordinates.map(c => c.z)),
      maxZ: Math.max(...coordinates.map(c => c.z)),
    };

    const totalVolume = (bounds.maxX - bounds.minX) * (bounds.maxY - bounds.minY) * (bounds.maxZ - bounds.minZ);
    const density = totalVolume > 0 ? Math.round((coordinates.length / totalVolume) * 10000) / 10000 : 0;

    chartCounter++;
    const chart: StarChart = {
      id: `CHART-${chartCounter.toString().padStart(6, '0')}`,
      name: `${patternType.charAt(0).toUpperCase() + patternType.slice(1)} Chart — ${resolvedEntities.join(', ')}`,
      epoch: timeframe === 'historical' ? 'PAST' : timeframe === 'projected' ? 'FUTURE' : 'CURRENT',
      coordinates,
      links,
      patterns,
      bounds,
      totalEntities: coordinates.length,
      totalLinks: links.length,
      density,
      timestamp: Date.now(),
    };

    // Pattern analysis
    const gravitationalCentre = {
      x: Math.round(coordinates.reduce((s, c) => s + c.x * c.influence, 0) / coordinates.reduce((s, c) => s + c.influence, 0) * 100) / 100,
      y: Math.round(coordinates.reduce((s, c) => s + c.y * c.influence, 0) / coordinates.reduce((s, c) => s + c.influence, 0) * 100) / 100,
      z: Math.round(coordinates.reduce((s, c) => s + c.z * c.influence, 0) / coordinates.reduce((s, c) => s + c.influence, 0) * 100) / 100,
    };

    const averageInfluence = Math.round((coordinates.reduce((s, c) => s + c.influence, 0) / coordinates.length) * 100) / 100;
    const maxLinks = coordinates.length * (coordinates.length - 1) / 2;
    const networkDensity = maxLinks > 0 ? Math.round((links.length / maxLinks) * 10000) / 100 : 0;

    const dominantPattern = patterns.length > 0 ? patterns[0] : null;

    this.audit.append({
      actor: 'NID-OBSERVATORY-STARMAP',
      action: 'CHART_PLOTTED',
      entity: patternType,
      status: 'SUCCESS',
      meta: {
        chartId: chart.id,
        entities: resolvedEntities.length,
        links: links.length,
        patterns: patterns.length,
        density,
      },
    });

    this.log.info('Star chart plotted', {
      chartId: chart.id,
      patternType,
      entities: resolvedEntities.length,
      links: links.length,
      patterns: patterns.length,
    });

    return {
      success: true,
      chart,
      dominantPattern,
      entityPositions,
      patternAnalysis: {
        strongestPattern: dominantPattern?.type ?? 'none',
        patternCount: patterns.length,
        entityCoverage: resolvedEntities.length / Object.keys(ENTITY_REGISTRY).length * 100,
        gravitationalCentre,
        averageInfluence,
        networkDensity,
      },
      message: `Star chart plotted: ${resolvedEntities.length} entities, ${links.length} links, ${patterns.length} patterns | ${patternType} at (${gravitationalCentre.x}, ${gravitationalCentre.y}, ${gravitationalCentre.z}) | Density: ${density}`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // Pattern Formation Calculation
  // ───────────────────────────────────────────────────────────────────────

  private calculatePatternFormation(
    patternType: StarMapInput['patternType'],
    coordinates: CelestialCoordinate[]
  ): PatternFormation {
    // Calculate centre of mass
    const totalInfluence = coordinates.reduce((s, c) => s + c.influence, 0);
    const centreOfMass = {
      x: Math.round((coordinates.reduce((s, c) => s + c.x * c.influence, 0) / totalInfluence) * 100) / 100,
      y: Math.round((coordinates.reduce((s, c) => s + c.y * c.influence, 0) / totalInfluence) * 100) / 100,
      z: Math.round((coordinates.reduce((s, c) => s + c.z * c.influence, 0) / totalInfluence) * 100) / 100,
    };

    // Calculate radius (max distance from centre)
    const radius = Math.max(...coordinates.map(c =>
      Math.sqrt(Math.pow(c.x - centreOfMass.x, 2) + Math.pow(c.y - centreOfMass.y, 2) + Math.pow(c.z - centreOfMass.z, 2))
    ));

    // Pattern-specific intensity and stability
    const intensityByPattern: Record<string, number> = {
      convergence: 80 + Math.random() * 15,
      divergence: 40 + Math.random() * 25,
      eclipse: 70 + Math.random() * 20,
      alignment: 60 + Math.random() * 30,
      nova: 90 + Math.random() * 10,
      void: 10 + Math.random() * 20,
    };

    const stabilityByPattern: Record<string, number> = {
      convergence: 50 + Math.random() * 30,
      divergence: 30 + Math.random() * 25,
      eclipse: 40 + Math.random() * 30,
      alignment: 70 + Math.random() * 25,
      nova: 10 + Math.random() * 30,
      void: 60 + Math.random() * 25,
    };

    const evolutionByPattern: Record<string, PatternFormation['projectedEvolution']> = {
      convergence: 'intensifying',
      divergence: 'dissipating',
      eclipse: 'forming',
      alignment: 'stable',
      nova: 'intensifying',
      void: 'stable',
    };

    const timeToPeakByPattern: Record<string, number> = {
      convergence: 1800000 + Math.random() * 3600000,  // 30-90 min
      divergence: 3600000 + Math.random() * 7200000,   // 1-3 hours
      eclipse: 900000 + Math.random() * 1800000,       // 15-45 min
      alignment: 7200000 + Math.random() * 14400000,   // 2-6 hours
      nova: 300000 + Math.random() * 600000,           // 5-15 min
      void: 0,                                           // Already at peak (absence)
    };

    return {
      type: patternType,
      entities: coordinates.map(c => c.entity),
      centreOfMass,
      radius: Math.round(radius * 100) / 100,
      intensity: Math.round((intensityByPattern[patternType] ?? 50) * 100) / 100,
      stability: Math.round((stabilityByPattern[patternType] ?? 50) * 100) / 100,
      projectedEvolution: evolutionByPattern[patternType] ?? 'stable',
      timeToPeak: Math.round(timeToPeakByPattern[patternType] ?? 0),
      confidence: Math.round((65 + Math.random() * 30) * 100) / 100,
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // Helpers
  // ───────────────────────────────────────────────────────────────────────

  private fail(message: string): PlotResult {
    this.log.error('Plot failed', { message });
    const emptyChart: StarChart = {
      id: 'CHART-000000',
      name: '',
      epoch: 'CURRENT',
      coordinates: [],
      links: [],
      patterns: [],
      bounds: { minX: 0, maxX: 0, minY: 0, maxY: 0, minZ: 0, maxZ: 0 },
      totalEntities: 0,
      totalLinks: 0,
      density: 0,
      timestamp: 0,
    };

    return {
      success: false,
      chart: emptyChart,
      dominantPattern: null,
      entityPositions: {},
      patternAnalysis: {
        strongestPattern: 'none',
        patternCount: 0,
        entityCoverage: 0,
        gravitationalCentre: { x: 0, y: 0, z: 0 },
        averageInfluence: 0,
        networkDensity: 0,
      },
      message,
      timestamp: Date.now(),
    };
  }
}
