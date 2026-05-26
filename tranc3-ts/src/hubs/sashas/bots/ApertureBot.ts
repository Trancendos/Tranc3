/**
 * Aperture Bot — Sasha's Photo Studio Tier 5 Bot (NID-SASHAS-APERTURE)
 *
 * Camera/exposure settings and generation parameter configuration.
 * Translates creative intent into technical generation parameters.
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('ApertureBot');

export interface ApertureRequest {
  width: number;
  height: number;
  steps?: number;
  guidanceScale?: number;
  seed?: number;
  sampler?: string;
}

export interface ApertureResult {
  settings: {
    width: number;
    height: number;
    steps: number;
    guidanceScale: number;
    seed: number;
    sampler: string;
    clipSkip: number;
    vae: string;
  };
  estimatedVramMb: number;
  estimatedTimeSeconds: number;
}

export class ApertureBot extends Bot {
  constructor() {
    super(
      'Aperture',
      async (request: ApertureRequest): Promise<ApertureResult> => {
        const settings = {
          width: request.width || 512,
          height: request.height || 512,
          steps: request.steps || 30,
          guidanceScale: request.guidanceScale || 7.5,
          seed: request.seed ?? Math.floor(Math.random() * 2147483647),
          sampler: request.sampler || 'DPM++ 2M Karras',
          clipSkip: 1,
          vae: 'auto',
        };

        const pixels = settings.width * settings.height;
        const estimatedVramMb = Math.ceil(pixels * settings.steps * 0.0005 + 2048);
        const estimatedTimeSeconds = Math.ceil(settings.steps * pixels / 1000000 + 5);

        logger.debug('Generation params configured', { width: settings.width, height: settings.height, steps: settings.steps });

        return { settings, estimatedVramMb, estimatedTimeSeconds };
      },
      'Configures AI image generation parameters from creative intent',
    );
  }
}
