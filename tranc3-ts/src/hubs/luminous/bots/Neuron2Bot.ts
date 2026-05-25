/**
 * Neuron2 Bot — Luminous Tier 5 Bot (NID-LUMINOUS-NEURON-2)
 *
 * Data transformation and feature extraction bot.
 * Normalizes, encodes, and extracts statistical features
 * from processed signal data.
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('Neuron2Bot');

/** Transform request */
export interface TransformRequest {
  data: number[];
  normalize?: boolean;
  extractFeatures?: boolean;
}

/** Transform result */
export interface TransformResult {
  original: number[];
  transformed: number[];
  normalized: boolean;
  features: StatisticalFeatures;
}

/** Statistical features extracted from data */
export interface StatisticalFeatures {
  mean: number;
  median: number;
  stddev: number;
  min: number;
  max: number;
  range: number;
  skewness: number;
  entropy: number;
}

export class Neuron2Bot extends Bot {
  constructor() {
    super(
      'Neuron2',
      async (request: TransformRequest): Promise<TransformResult> => {
        const data = request.data || [];
        const shouldNormalize = request.normalize !== false;
        const shouldExtract = request.extractFeatures !== false;

        const transformed = shouldNormalize ? normalize(data) : [...data];
        const features = shouldExtract ? extractFeatures(data) : emptyFeatures();

        logger.debug('Data transformed', {
          inputSize: data.length,
          normalized: shouldNormalize,
          featureCount: Object.keys(features).length,
        });

        return {
          original: data,
          transformed,
          normalized: shouldNormalize,
          features,
        };
      },
      'Normalizes data and extracts statistical features from signal arrays',
    );
  }
}

/** Normalize data to [0, 1] range */
function normalize(data: number[]): number[] {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min;

  if (range === 0) return data.map(() => 0.5);

  return data.map(v => (v - min) / range);
}

/** Extract statistical features */
function extractFeatures(data: number[]): StatisticalFeatures {
  if (data.length === 0) return emptyFeatures();

  const sorted = [...data].sort((a, b) => a - b);
  const n = data.length;
  const sum = data.reduce((a, b) => a + b, 0);
  const mean = sum / n;

  const median = n % 2 === 0
    ? (sorted[n / 2 - 1] + sorted[n / 2]) / 2
    : sorted[Math.floor(n / 2)];

  const variance = data.reduce((acc, v) => acc + (v - mean) ** 2, 0) / n;
  const stddev = Math.sqrt(variance);

  const min = sorted[0];
  const max = sorted[n - 1];

  const skewness = stddev > 0
    ? data.reduce((acc, v) => acc + ((v - mean) / stddev) ** 3, 0) / n
    : 0;

  // Shannon entropy (binned approximation)
  const bins = 10;
  const binWidth = (max - min) / bins || 1;
  const counts = new Array(bins).fill(0);
  for (const v of data) {
    const bin = Math.min(Math.floor((v - min) / binWidth), bins - 1);
    counts[bin]++;
  }
  let entropy = 0;
  for (const count of counts) {
    if (count > 0) {
      const p = count / n;
      entropy -= p * Math.log2(p);
    }
  }

  return {
    mean,
    median,
    stddev,
    min,
    max,
    range: max - min,
    skewness,
    entropy,
  };
}

/** Empty features placeholder */
function emptyFeatures(): StatisticalFeatures {
  return {
    mean: 0,
    median: 0,
    stddev: 0,
    min: 0,
    max: 0,
    range: 0,
    skewness: 0,
    entropy: 0,
  };
}
