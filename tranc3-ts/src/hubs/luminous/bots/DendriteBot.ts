/**
 * Dendrite Bot — Luminous Tier 5 Bot (NID-LUMINOUS-DENDRITE)
 *
 * Input aggregation and signal combining bot.
 * Receives multiple input signals, combines them with weighted
 * summation, and produces a unified aggregated output.
 * Analogous to dendrites in biological neurons.
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('DendriteBot');

/** Aggregation request */
export interface AggregationRequest {
  inputs: string[];
  weights?: number[];
  metadata?: Record<string, any>;
}

/** Aggregation result */
export interface AggregationResult {
  combined: string;
  inputCount: number;
  totalWeight: number;
  signalStrength: number;
}

export class DendriteBot extends Bot {
  constructor() {
    super(
      'Dendrite',
      async (request: AggregationRequest): Promise<AggregationResult> => {
        const inputs = request.inputs || [];
        const weights = request.weights || inputs.map(() => 1.0 / inputs.length);

        // Combine inputs with weights
        const totalWeight = weights.reduce((a, b) => a + b, 0);
        const combined = inputs.join('\n');

        // Calculate signal strength (heuristic: weighted average of input lengths)
        let signalStrength = 0;
        for (let i = 0; i < inputs.length; i++) {
          const w = weights[i] || 0;
          signalStrength += inputs[i].length * w;
        }
        signalStrength = totalWeight > 0 ? signalStrength / totalWeight : 0;

        logger.debug('Inputs aggregated', {
          inputCount: inputs.length,
          combinedLength: combined.length,
          signalStrength: signalStrength.toFixed(1),
        });

        return {
          combined,
          inputCount: inputs.length,
          totalWeight,
          signalStrength,
        };
      },
      'Aggregates multiple input signals with weighted summation into unified output',
    );
  }
}
