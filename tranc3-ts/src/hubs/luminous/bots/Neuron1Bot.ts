/**
 * Neuron1 Bot — Luminous Tier 5 Bot (NID-LUMINOUS-NEURON-1)
 *
 * Signal processing and pattern recognition bot.
 * Applies activation functions to input signals and detects
 * patterns that exceed the configurable threshold.
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('Neuron1Bot');

/** Signal processing request */
export interface SignalRequest {
  signals: number[];
  activationFn?: 'relu' | 'sigmoid' | 'tanh' | 'leaky_relu';
}

/** Signal processing result */
export interface SignalResult {
  input: number[];
  output: number[];
  activationFn: string;
  peakSignal: number;
  patternDetected: boolean;
  threshold: number;
}

export class Neuron1Bot extends Bot {
  private readonly threshold: number;

  constructor(threshold: number = 0.5) {
    super(
      'Neuron1',
      async (request: SignalRequest): Promise<SignalResult> => {
        const fn = request.activationFn || 'relu';
        const output = applyActivation(request.signals, fn);
        const peakSignal = Math.max(...output.map(Math.abs));
        const patternDetected = peakSignal >= this.threshold;

        logger.debug('Signals processed', {
          inputCount: request.signals.length,
          activationFn: fn,
          peak: peakSignal.toFixed(3),
          patternDetected,
        });

        return {
          input: request.signals,
          output,
          activationFn: fn,
          peakSignal,
          patternDetected,
          threshold: this.threshold,
        };
      },
      'Applies activation functions to signals and detects patterns above threshold',
    );
    this.threshold = threshold;
  }
}

/** Apply activation function to signal array */
function applyActivation(signals: number[], fn: string): number[] {
  switch (fn) {
    case 'sigmoid':
      return signals.map(s => 1 / (1 + Math.exp(-s)));
    case 'tanh':
      return signals.map(s => Math.tanh(s));
    case 'leaky_relu':
      return signals.map(s => s > 0 ? s : 0.01 * s);
    case 'relu':
    default:
      return signals.map(s => Math.max(0, s));
  }
}
