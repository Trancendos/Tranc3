/**
 * SpriteBot — 2D Sprite Management Bot for TranceFlow
 *
 * Identity:  NID-TRANCEFLOW-SPRITE
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TranceFlowAI (AID-TRANCEFLOW)
 *
 * Responsibilities:
 *   - Manage 2D sprite creation, update, and deletion
 *   - Handle sprite animation state (frame progression, playback)
 *   - Apply sprite transforms (position, rotation, scale, flip)
 *   - Composite sprites onto layers with blend modes
 *   - Generate sprite sheets from individual frames
 *   - Provide sprite atlas packing and UV coordinate computation
 */

import { Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────

export interface SpriteData {
  id: string;
  texture: string;
  position: { x: number; y: number };
  size: { width: number; height: number };
  rotation: number;
  flipX: boolean;
  flipY: boolean;
  frame: number;
  animation: string | null;
  animationSpeed: number;
  animationFrame: number;
  totalFrames: number;
  opacity: number;
  tint: string;
  zIndex: number;
}

export interface SpriteAddParams {
  operation: 'ADD';
  layerId: string;
  sprite: Omit<SpriteData, 'id' | 'animationFrame' | 'totalFrames' | 'opacity' | 'tint' | 'zIndex'>;
}

export interface SpriteUpdateParams {
  operation: 'UPDATE';
  spriteId: string;
  updates: Partial<Pick<SpriteData, 'position' | 'rotation' | 'flipX' | 'flipY' | 'opacity' | 'tint' | 'frame' | 'zIndex'>>;
}

export interface SpriteAnimateParams {
  operation: 'ANIMATE';
  spriteId: string;
  deltaTime: number;
}

export interface SpriteRemoveParams {
  operation: 'REMOVE';
  spriteId: string;
  layerId: string;
}

export interface SpriteSheetParams {
  operation: 'SHEET';
  sprites: Array<{ texture: string; frameWidth: number; frameHeight: number; frameCount: number }>;
  sheetWidth: number;
  sheetHeight: number;
}

export type SpriteOperation =
  | SpriteAddParams
  | SpriteUpdateParams
  | SpriteAnimateParams
  | SpriteRemoveParams
  | SpriteSheetParams;

export interface SpriteSheetResult {
  sheetId: string;
  dimensions: { width: number; height: number };
  spriteCount: number;
  totalFrames: number;
  uvCoordinates: Array<{ u0: number; v0: number; u1: number; v1: number }>;
  packedEfficiency: number;
}

// ───────────────────────────────────────────
// In-memory Sprite Storage
// ───────────────────────────────────────────

const spriteStore = new Map<string, SpriteData>();

// ───────────────────────────────────────────
// SpriteBot Implementation
// ───────────────────────────────────────────

export class SpriteBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: SpriteOperation): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-TRANCEFLOW-SPRITE',
      'Sprite',
      handler,
      '2D sprite management, animation, compositing, sprite sheet packing'
    );

    this.log = new Logger('SpriteBot');
  }

  private async process(input: SpriteOperation): Promise<unknown> {
    switch (input.operation) {
      case 'ADD':
        return this.addSprite(input);
      case 'UPDATE':
        return this.updateSprite(input);
      case 'ANIMATE':
        return this.animateSprite(input);
      case 'REMOVE':
        return this.removeSprite(input);
      case 'SHEET':
        return this.generateSpriteSheet(input);
      default:
        throw new Error(`Unknown sprite operation: ${(input as SpriteOperation).operation}`);
    }
  }

  // ───────────────────────────────────────
  // Sprite CRUD
  // ───────────────────────────────────────

  private addSprite(params: SpriteAddParams): SpriteData {
    const spriteId = `SPRITE-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();

    const sprite: SpriteData = {
      id: spriteId,
      texture: params.sprite.texture,
      position: params.sprite.position ?? { x: 0, y: 0 },
      size: params.sprite.size ?? { width: 64, height: 64 },
      rotation: params.sprite.rotation ?? 0,
      flipX: params.sprite.flipX ?? false,
      flipY: params.sprite.flipY ?? false,
      frame: params.sprite.frame ?? 0,
      animation: params.sprite.animation ?? null,
      animationSpeed: params.sprite.animationSpeed ?? 1.0,
      animationFrame: 0,
      totalFrames: 1,
      opacity: 1.0,
      tint: '#FFFFFF',
      zIndex: 0,
    };

    spriteStore.set(spriteId, sprite);

    this.log.info('Sprite added', { spriteId, texture: sprite.texture, layerId: params.layerId });
    return sprite;
  }

  private updateSprite(params: SpriteUpdateParams): SpriteData | null {
    const sprite = spriteStore.get(params.spriteId);
    if (!sprite) {
      this.log.warn('Sprite not found for update', { spriteId: params.spriteId });
      return null;
    }

    const updates = params.updates;

    if (updates.position) sprite.position = updates.position;
    if (updates.rotation !== undefined) sprite.rotation = updates.rotation;
    if (updates.flipX !== undefined) sprite.flipX = updates.flipX;
    if (updates.flipY !== undefined) sprite.flipY = updates.flipY;
    if (updates.opacity !== undefined) sprite.opacity = Math.max(0, Math.min(1, updates.opacity));
    if (updates.tint) sprite.tint = updates.tint;
    if (updates.frame !== undefined) sprite.frame = updates.frame;
    if (updates.zIndex !== undefined) sprite.zIndex = updates.zIndex;

    this.log.debug('Sprite updated', { spriteId: params.spriteId, fields: Object.keys(updates) });
    return sprite;
  }

  private animateSprite(params: SpriteAnimateParams): SpriteData | null {
    const sprite = spriteStore.get(params.spriteId);
    if (!sprite) {
      this.log.warn('Sprite not found for animation', { spriteId: params.spriteId });
      return null;
    }

    if (!sprite.animation || sprite.totalFrames <= 1) {
      return sprite; // Not animated
    }

    // Advance animation frame based on delta time and speed
    sprite.animationFrame += sprite.animationSpeed * params.deltaTime * 10; // 10 fps base

    // Wrap around
    if (sprite.animationFrame >= sprite.totalFrames) {
      sprite.animationFrame = sprite.animationFrame % sprite.totalFrames;
    }

    sprite.frame = Math.floor(sprite.animationFrame);

    this.log.debug('Sprite animated', { spriteId: params.spriteId, frame: sprite.frame, totalFrames: sprite.totalFrames });
    return sprite;
  }

  private removeSprite(params: SpriteRemoveParams): boolean {
    const removed = spriteStore.delete(params.spriteId);
    if (removed) {
      this.log.info('Sprite removed', { spriteId: params.spriteId, layerId: params.layerId });
    } else {
      this.log.warn('Sprite not found for removal', { spriteId: params.spriteId });
    }
    return removed;
  }

  // ───────────────────────────────────────
  // Sprite Sheet Generation
  // ───────────────────────────────────────

  private generateSpriteSheet(params: SpriteSheetParams): SpriteSheetResult {
    const { sprites, sheetWidth, sheetHeight } = params;

    const sheetId = `SHEET-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();
    const uvCoordinates: Array<{ u0: number; v0: number; u1: number; v1: number }> = [];

    let currentX = 0;
    let currentY = 0;
    let rowHeight = 0;
    let totalFrames = 0;

    for (const sprite of sprites) {
      const frameWidth = sprite.frameWidth;
      const frameHeight = sprite.frameHeight;

      // Check if sprite fits on current row
      if (currentX + frameWidth > sheetWidth) {
        // Move to next row
        currentX = 0;
        currentY += rowHeight;
        rowHeight = 0;
      }

      // Check if sheet is full
      if (currentY + frameHeight > sheetHeight) {
        this.log.warn('Sprite sheet overflow — some sprites may not fit', {
          sheetId,
          currentY,
          frameHeight,
          sheetHeight,
        });
        break;
      }

      // Compute UV coordinates for each frame
      for (let f = 0; f < sprite.frameCount; f++) {
        const frameX = currentX + (f * frameWidth) % sheetWidth;
        const frameY = currentY + Math.floor((currentX + f * frameWidth) / sheetWidth) * frameHeight;

        uvCoordinates.push({
          u0: frameX / sheetWidth,
          v0: frameY / sheetHeight,
          u1: (frameX + frameWidth) / sheetWidth,
          v1: (frameY + frameHeight) / sheetHeight,
        });
      }

      totalFrames += sprite.frameCount;
      currentX += frameWidth * sprite.frameCount;
      rowHeight = Math.max(rowHeight, frameHeight);
    }

    // Calculate packing efficiency
    const usedArea = uvCoordinates.length > 0
      ? uvCoordinates.reduce((sum, uv) => {
          const frameW = (uv.u1 - uv.u0) * sheetWidth;
          const frameH = (uv.v1 - uv.v0) * sheetHeight;
          return sum + frameW * frameH;
        }, 0)
      : 0;
    const totalArea = sheetWidth * sheetHeight;
    const packedEfficiency = totalArea > 0 ? usedArea / totalArea : 0;

    this.log.info('Sprite sheet generated', {
      sheetId,
      spriteCount: sprites.length,
      totalFrames,
      dimensions: `${sheetWidth}x${sheetHeight}`,
      efficiency: `${(packedEfficiency * 100).toFixed(1)}%`,
    });

    return {
      sheetId,
      dimensions: { width: sheetWidth, height: sheetHeight },
      spriteCount: sprites.length,
      totalFrames,
      uvCoordinates,
      packedEfficiency,
    };
  }
}
