/**
 * ShelfBot — Volume Stacking & Shelving Bot for The Library
 *
 * Identity:  NID-LIBRARY-SHELF
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheLibraryAI (AID-LIBRARY)
 *
 * Responsibilities:
 *   - STACK: Manage the physical and logical placement of volumes on shelves
 *   - Support shelve, retrieve, transfer, and preserve actions
 *   - Track shelf occupancy, location codes, and volume placement
 *   - Manage Dewey-organized aisle/stack/shelf hierarchy
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────
// Input / Output Types
// ─────────────────────────────────────────────────────────────────────

export interface ShelfInput {
  operation: 'STACK';
  volumeId: string;
  action: 'shelve' | 'retrieve' | 'transfer' | 'preserve';
  location?: string;
  targetLocation?: string;
}

export interface ShelfLocation {
  stack: string;
  aisle: string;
  shelf: string;
  position: number;
  fullLocation: string;
}

export interface ShelfRecord {
  volumeId: string;
  location: ShelfLocation;
  action: 'shelved' | 'retrieved' | 'transferred' | 'preserved';
  previousLocation?: ShelfLocation;
  timestamp: number;
  handledBy: string;
}

export interface ShelfOccupancy {
  location: string;
  totalSlots: number;
  usedSlots: number;
  availableSlots: number;
  utilizationPercent: number;
  volumes: string[];
}

export interface StackResult {
  success: boolean;
  volumeId: string;
  action: ShelfInput['action'];
  location?: ShelfLocation;
  previousLocation?: ShelfLocation;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────
// Simulated Shelf Layout
// ─────────────────────────────────────────────────────────────────────

const SHELF_CONFIG = {
  stacks: ['A', 'B', 'C', 'D', 'E'],
  aislesPerStack: 6,
  shelvesPerAisle: 8,
  positionsPerShelf: 12,
};

// ─────────────────────────────────────────────────────────────────────
// ShelfBot Implementation
// ─────────────────────────────────────────────────────────────────────

export class ShelfBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private shelfMap: Map<string, ShelfLocation>;
  private history: ShelfRecord[];
  private occupancyMap: Map<string, string[]>;

  constructor() {
    super(
      'NID-LIBRARY-SHELF',
      'Shelf',
      async (input: ShelfInput) => this.handleStack(input),
      'Manages volume placement, retrieval, transfer, and preservation on library shelves'
    );

    this.log = new Logger('ShelfBot');
    this.audit = auditLedger;
    this.shelfMap = new Map();
    this.history = [];
    this.occupancyMap = new Map();

    // Initialise occupancy tracking for all shelf locations
    this.initialiseOccupancy();
  }

  private initialiseOccupancy(): void {
    for (const stack of SHELF_CONFIG.stacks) {
      for (let aisle = 1; aisle <= SHELF_CONFIG.aislesPerStack; aisle++) {
        for (let shelf = 1; shelf <= SHELF_CONFIG.shelvesPerAisle; shelf++) {
          const key = `${stack}-${aisle}-${shelf}`;
          this.occupancyMap.set(key, []);
        }
      }
    }
  }

  // ───────────────────────────────────────────────────────────────
  // Main Handler
  // ───────────────────────────────────────────────────────────────

  private async handleStack(input: ShelfInput): Promise<StackResult> {
    if (input.operation !== 'STACK') {
      return {
        success: false,
        volumeId: input.volumeId,
        action: input.action,
        message: `Invalid operation: ${input.operation}. Expected STACK.`,
        timestamp: Date.now(),
      };
    }

    switch (input.action) {
      case 'shelve':
        return this.shelve(input.volumeId, input.location);
      case 'retrieve':
        return this.retrieve(input.volumeId);
      case 'transfer':
        return this.transfer(input.volumeId, input.targetLocation);
      case 'preserve':
        return this.preserve(input.volumeId);
      default:
        return {
          success: false,
          volumeId: input.volumeId,
          action: input.action,
          message: `Unknown action: ${input.action}`,
          timestamp: Date.now(),
        };
    }
  }

  // ───────────────────────────────────────────────────────────────
  // Shelve — Place a volume on an appropriate shelf
  // ───────────────────────────────────────────────────────────────

  private shelve(volumeId: string, locationHint?: string): StackResult {
    // If a location is specified, try to use it; otherwise auto-assign
    const location = locationHint
      ? this.parseLocation(locationHint)
      : this.findAvailableSlot();

    if (!location) {
      return {
        success: false,
        volumeId,
        action: 'shelve',
        message: 'No available shelf location found',
        timestamp: Date.now(),
      };
    }

    // Check if position is occupied
    const occupancyKey = `${location.stack}-${location.aisle}-${location.shelf}`;
    const occupants = this.occupancyMap.get(occupancyKey) ?? [];

    if (occupants.length >= SHELF_CONFIG.positionsPerShelf) {
      // Find alternative slot
      const altLocation = this.findAvailableSlot();
      if (!altLocation) {
        return {
          success: false,
          volumeId,
          action: 'shelve',
          message: 'Shelf full, no alternative location available',
          timestamp: Date.now(),
        };
      }
      return this.shelve(volumeId, this.formatLocation(altLocation));
    }

    // Place the volume
    this.shelfMap.set(volumeId, location);
    occupants.push(volumeId);
    this.occupancyMap.set(occupancyKey, occupants);

    const record: ShelfRecord = {
      volumeId,
      location,
      action: 'shelved',
      timestamp: Date.now(),
      handledBy: 'ShelfBot',
    };
    this.history.push(record);

    this.audit.append({
      actor: 'ShelfBot',
      action: 'SHELVE',
      entity: volumeId,
      status: 'SUCCESS',
      meta: { location: location.fullLocation },
    });

    this.log.info('Volume shelved', { volumeId, location: location.fullLocation });

    return {
      success: true,
      volumeId,
      action: 'shelve',
      location,
      message: `Volume ${volumeId} shelved at ${location.fullLocation}`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────
  // Retrieve — Remove a volume from its shelf
  // ───────────────────────────────────────────────────────────────

  private retrieve(volumeId: string): StackResult {
    const location = this.shelfMap.get(volumeId);

    if (!location) {
      return {
        success: false,
        volumeId,
        action: 'retrieve',
        message: `Volume ${volumeId} not found on any shelf`,
        timestamp: Date.now(),
      };
    }

    // Remove from occupancy tracking
    const occupancyKey = `${location.stack}-${location.aisle}-${location.shelf}`;
    const occupants = this.occupancyMap.get(occupancyKey) ?? [];
    const updatedOccupants = occupants.filter(id => id !== volumeId);
    this.occupancyMap.set(occupancyKey, updatedOccupants);

    // Remove from shelf map
    this.shelfMap.delete(volumeId);

    const record: ShelfRecord = {
      volumeId,
      location,
      action: 'retrieved',
      timestamp: Date.now(),
      handledBy: 'ShelfBot',
    };
    this.history.push(record);

    this.log.info('Volume retrieved', { volumeId, from: location.fullLocation });

    return {
      success: true,
      volumeId,
      action: 'retrieve',
      previousLocation: location,
      message: `Volume ${volumeId} retrieved from ${location.fullLocation}`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────
  // Transfer — Move a volume to a new shelf location
  // ───────────────────────────────────────────────────────────────

  private transfer(volumeId: string, targetLocation?: string): StackResult {
    const currentLocation = this.shelfMap.get(volumeId);

    if (!currentLocation) {
      return {
        success: false,
        volumeId,
        action: 'transfer',
        message: `Volume ${volumeId} not found on any shelf`,
        timestamp: Date.now(),
      };
    }

    // Determine new location
    const newLocation = targetLocation
      ? this.parseLocation(targetLocation)
      : this.findAvailableSlot();

    if (!newLocation) {
      return {
        success: false,
        volumeId,
        action: 'transfer',
        message: 'No target location available for transfer',
        timestamp: Date.now(),
      };
    }

    // Remove from old location
    const oldKey = `${currentLocation.stack}-${currentLocation.aisle}-${currentLocation.shelf}`;
    const oldOccupants = this.occupancyMap.get(oldKey) ?? [];
    this.occupancyMap.set(oldKey, oldOccupants.filter(id => id !== volumeId));

    // Place at new location
    const newKey = `${newLocation.stack}-${newLocation.aisle}-${newLocation.shelf}`;
    const newOccupants = this.occupancyMap.get(newKey) ?? [];
    newOccupants.push(volumeId);
    this.occupancyMap.set(newKey, newOccupants);

    this.shelfMap.set(volumeId, newLocation);

    const record: ShelfRecord = {
      volumeId,
      location: newLocation,
      action: 'transferred',
      previousLocation: currentLocation,
      timestamp: Date.now(),
      handledBy: 'ShelfBot',
    };
    this.history.push(record);

    this.log.info('Volume transferred', {
      volumeId,
      from: currentLocation.fullLocation,
      to: newLocation.fullLocation,
    });

    return {
      success: true,
      volumeId,
      action: 'transfer',
      location: newLocation,
      previousLocation: currentLocation,
      message: `Volume ${volumeId} transferred from ${currentLocation.fullLocation} to ${newLocation.fullLocation}`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────
  // Preserve — Move a volume to archival/preservation storage
  // ───────────────────────────────────────────────────────────────

  private preserve(volumeId: string): StackResult {
    const currentLocation = this.shelfMap.get(volumeId);

    // Preservation location is always Stack E (the special collections stack)
    const preserveLocation: ShelfLocation = {
      stack: 'E',
      aisle: '1',
      shelf: '1',
      position: (this.occupancyMap.get('E-1-1') ?? []).length + 1,
      fullLocation: 'E-1-1-PRES',
    };

    // Remove from current location if exists
    if (currentLocation) {
      const oldKey = `${currentLocation.stack}-${currentLocation.aisle}-${currentLocation.shelf}`;
      const oldOccupants = this.occupancyMap.get(oldKey) ?? [];
      this.occupancyMap.set(oldKey, oldOccupants.filter(id => id !== volumeId));
    }

    // Place in preservation
    this.shelfMap.set(volumeId, preserveLocation);
    const presOccupants = this.occupancyMap.get('E-1-1') ?? [];
    presOccupants.push(volumeId);
    this.occupancyMap.set('E-1-1', presOccupants);

    const record: ShelfRecord = {
      volumeId,
      location: preserveLocation,
      action: 'preserved',
      previousLocation: currentLocation,
      timestamp: Date.now(),
      handledBy: 'ShelfBot',
    };
    this.history.push(record);

    this.audit.append({
      actor: 'ShelfBot',
      action: 'PRESERVE',
      entity: volumeId,
      status: 'SUCCESS',
      meta: { location: preserveLocation.fullLocation },
    });

    this.log.info('Volume preserved', { volumeId, location: preserveLocation.fullLocation });

    return {
      success: true,
      volumeId,
      action: 'preserve',
      location: preserveLocation,
      previousLocation: currentLocation,
      message: `Volume ${volumeId} moved to preservation storage at ${preserveLocation.fullLocation}`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────
  // Helper: Parse location string
  // ───────────────────────────────────────────────────────────────

  private parseLocation(locationStr: string): ShelfLocation {
    const parts = locationStr.split('-');
    return {
      stack: parts[0] ?? 'A',
      aisle: parts[1] ?? '1',
      shelf: parts[2] ?? '1',
      position: parseInt(parts[3] ?? '1', 10),
      fullLocation: locationStr,
    };
  }

  // ───────────────────────────────────────────────────────────────
  // Helper: Format location
  // ───────────────────────────────────────────────────────────────

  private formatLocation(loc: ShelfLocation): string {
    return `${loc.stack}-${loc.aisle}-${loc.shelf}-${loc.position}`;
  }

  // ───────────────────────────────────────────────────────────────
  // Helper: Find an available shelf slot
  // ───────────────────────────────────────────────────────────────

  private findAvailableSlot(): ShelfLocation | null {
    for (const stack of SHELF_CONFIG.stacks) {
      for (let aisle = 1; aisle <= SHELF_CONFIG.aislesPerStack; aisle++) {
        for (let shelf = 1; shelf <= SHELF_CONFIG.shelvesPerAisle; shelf++) {
          const key = `${stack}-${aisle}-${shelf}`;
          const occupants = this.occupancyMap.get(key) ?? [];
          if (occupants.length < SHELF_CONFIG.positionsPerShelf) {
            return {
              stack,
              aisle: aisle.toString(),
              shelf: shelf.toString(),
              position: occupants.length + 1,
              fullLocation: `${stack}-${aisle}-${shelf}-${occupants.length + 1}`,
            };
          }
        }
      }
    }
    return null;
  }
}
