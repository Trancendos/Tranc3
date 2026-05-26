/**
 * Lens Bot — Sasha's Photo Studio Tier 5 Bot (NID-SASHAS-LENS)
 *
 * Perspective distortion and focal length effects.
 * Simulates camera lens characteristics including focal length,
 * depth of field, and perspective distortion.
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('LensBot');

export interface LensRequest {
  imageId: string;
  focalLength: number; // mm: 14 (ultra-wide) - 200 (telephoto)
  aperture?: number; // f-stop: 1.4 - 22
  distortion?: 'barrel' | 'pincushion' | 'none';
}

export interface LensResult {
  imageId: string;
  focalLength: number;
  aperture: number;
  distortion: string;
  fieldOfView: number;
  depthOfField: 'shallow' | 'medium' | 'deep';
  perspectiveEffect: string;
}

export class LensBot extends Bot {
  constructor() {
    super(
      'Lens',
      async (request: LensRequest): Promise<LensResult> => {
        const focalLength = Math.max(14, Math.min(200, request.focalLength || 50));
        const aperture = request.aperture || 5.6;
        const distortion = request.distortion || 'none';

        // Calculate field of view from focal length (full-frame sensor)
        const fieldOfView = 2 * Math.atan(43.27 / (2 * focalLength)) * (180 / Math.PI);

        const depthOfField = aperture <= 2.8 ? 'shallow' : aperture <= 8 ? 'medium' : 'deep';

        const perspectiveEffect = focalLength < 24 ? 'exaggerated-perspective' :
          focalLength < 50 ? 'natural-perspective' :
          focalLength < 85 ? 'moderate-compression' : 'strong-compression';

        logger.debug('Lens effect applied', { imageId: request.imageId, focalLength, aperture });

        return {
          imageId: request.imageId,
          focalLength,
          aperture,
          distortion,
          fieldOfView: Math.round(fieldOfView * 10) / 10,
          depthOfField,
          perspectiveEffect,
        };
      },
      'Simulates camera lens effects including focal length and perspective distortion',
    );
  }
}
