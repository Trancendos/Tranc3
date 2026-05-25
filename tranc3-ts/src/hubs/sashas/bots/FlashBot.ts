/**
 * Flash Bot — Sasha's Photo Studio Tier 5 Bot (NID-SASHAS-FLASH)
 *
 * Lighting correction and brightness adjustment.
 * Applies flash/lighting effects to images, correcting exposure
 * and adding dramatic lighting.
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('FlashBot');

export interface FlashRequest {
  imageId: string;
  intensity: number; // 0.0 - 2.0
  direction?: 'front' | 'side' | 'top' | 'back';
  colorTemperature?: number; // Kelvin: 2700 (warm) - 6500 (cool)
}

export interface FlashResult {
  imageId: string;
  intensity: number;
  direction: string;
  colorTemperature: number;
  exposureAdjustment: number;
  shadowRecovery: number;
  highlightProtection: number;
}

export class FlashBot extends Bot {
  constructor() {
    super(
      'Flash',
      async (request: FlashRequest): Promise<FlashResult> => {
        const intensity = Math.max(0, Math.min(2, request.intensity || 1.0));
        const direction = request.direction || 'front';
        const colorTemperature = request.colorTemperature || 5500;

        const exposureAdjustment = intensity > 1 ? (intensity - 1) * 0.5 : 0;
        const shadowRecovery = intensity < 1 ? (1 - intensity) * 0.3 : 0;
        const highlightProtection = intensity > 1.2 ? (intensity - 1.2) * 0.2 : 0;

        logger.debug('Flash applied', { imageId: request.imageId, intensity, direction });

        return {
          imageId: request.imageId,
          intensity,
          direction,
          colorTemperature,
          exposureAdjustment,
          shadowRecovery,
          highlightProtection,
        };
      },
      'Applies flash lighting effects and exposure correction to images',
    );
  }
}
