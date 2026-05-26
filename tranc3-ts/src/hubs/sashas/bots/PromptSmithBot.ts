/**
 * PromptSmith Bot — Sasha's Photo Studio Tier 5 Bot (NID-SASHAS-PROMPTSMITH)
 *
 * Prompt engineering and optimization for AI image generation.
 * Enhances raw prompts with style modifiers, quality boosters,
 * and negative prompt suggestions.
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('PromptSmithBot');

export interface PromptSmithRequest {
  prompt: string;
  style?: string;
  negativePrompt?: string;
  language?: string;
}

export interface PromptSmithResult {
  originalPrompt: string;
  enhancedPrompt: string;
  negativePrompt: string;
  styleModifiers: string[];
  qualityBoosters: string[];
  estimatedTokenCount: number;
}

export class PromptSmithBot extends Bot {
  private readonly styleModifiers: Record<string, string[]> = {
    'photorealistic': ['8k uhd', 'dslr', 'high quality', 'detailed', 'sharp focus'],
    'anime': ['anime style', 'cel shading', 'vibrant colors', 'detailed eyes'],
    'oil-painting': ['oil on canvas', 'brush strokes', 'rich colors', 'impasto'],
    'watercolor': ['watercolor painting', 'soft edges', 'flowing', 'translucent'],
    'digital-art': ['digital art', 'trending on artstation', 'concept art'],
    'cinematic': ['cinematic lighting', 'dramatic', 'anamorphic', 'film grain'],
    '3d-render': ['3d render', 'octane render', 'unreal engine', 'volumetric lighting'],
  };

  private readonly qualityBoosters: string[] = [
    'masterpiece',
    'best quality',
    'highly detailed',
    'professional',
  ];

  constructor() {
    super(
      'PromptSmith',
      async (request: PromptSmithRequest): Promise<PromptSmithResult> => {
        let enhanced = request.prompt;
        const appliedModifiers: string[] = [];
        const appliedBoosters: string[] = [];

        // Apply style modifiers
        if (request.style && this.styleModifiers[request.style]) {
          const modifiers = this.styleModifiers[request.style];
          for (const mod of modifiers.slice(0, 3)) {
            if (!enhanced.toLowerCase().includes(mod.toLowerCase())) {
              enhanced += `, ${mod}`;
              appliedModifiers.push(mod);
            }
          }
        }

        // Apply quality boosters (first 2)
        for (const booster of this.qualityBoosters.slice(0, 2)) {
          if (!enhanced.toLowerCase().includes(booster.toLowerCase())) {
            enhanced += `, ${booster}`;
            appliedBoosters.push(booster);
          }
        }

        // Generate negative prompt if not provided
        const negativePrompt = request.negativePrompt || 'blurry, low quality, distorted, deformed, ugly, watermark, text';

        const estimatedTokenCount = Math.ceil(enhanced.length / 4);

        logger.debug('Prompt enhanced', { original: request.prompt.length, enhanced: enhanced.length });

        return {
          originalPrompt: request.prompt,
          enhancedPrompt: enhanced,
          negativePrompt,
          styleModifiers: appliedModifiers,
          qualityBoosters: appliedBoosters,
          estimatedTokenCount,
        };
      },
      'Enhances AI image generation prompts with style modifiers and quality boosters',
    );
  }
}
