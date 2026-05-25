/**
 * TeapotBot — Chaos Brewing Bot for The Chaos Party
 *
 * Identity:  NID-CHAOSPARTY-TEAPOT
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheChaosPartyAI (AID-CHAOSPARTY)
 *
 * Responsibilities:
 *   - Brew chaos recipes from ingredients and parameters
 *   - Calculate chaos contribution per ingredient
 *   - Simulate brewing with temperature and time control
 *   - Track tea recipe library with known effects
 *   - Generate side effects and aftertaste reports
 *
 * "Why is a raven like a writing desk? — Have some more tea."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface TeapotInput {
  operation: 'BREW';
  recipe: string;
  intensity?: 'mild' | 'medium' | 'hot' | 'unleashed';
  servings?: number;
  sugarLevel?: number;
  customIngredients?: Array<{
    name: string;
    amount: number;
    unit: string;
    chaosContribution: number;
  }>;
  brewTimeOverride?: number;
  temperatureOverride?: number;
}

export interface TeaIngredient {
  name: string;
  amount: number;
  unit: string;
  chaosContribution: number;
  rarity: 'common' | 'uncommon' | 'rare' | 'legendary';
}

export interface BrewResult {
  success: boolean;
  recipeName: string;
  teaColour: string;
  ingredients: TeaIngredient[];
  brewTime: number;
  temperature: number;
  totalChaosContribution: number;
  servings: number;
  sugarLevel: number;
  effect: string;
  sideEffects: string[];
  aftertaste: string;
  steepingRequired: boolean;
  potency: number; // 0..100
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Built-in Recipes
// ─────────────────────────────────────────────────────────────────────────────

const CHAOS_RECIPES: Record<string, {
  ingredients: TeaIngredient[];
  brewTime: number;
  temperature: number;
  effect: string;
  sideEffects: string[];
  colour: string;
  aftertaste: string;
}> = {
  'fuzz-medium-blend': {
    ingredients: [
      { name: 'Random Bytes', amount: 256, unit: 'bytes', chaosContribution: 15, rarity: 'common' },
      { name: 'Boundary Salt', amount: 50, unit: 'mg', chaosContribution: 10, rarity: 'common' },
      { name: 'Edge-Case Extract', amount: 3, unit: 'drops', chaosContribution: 25, rarity: 'uncommon' },
      { name: 'Null Pointer Root', amount: 1, unit: 'sprig', chaosContribution: 20, rarity: 'uncommon' },
    ],
    brewTime: 30000,
    temperature: 85,
    effect: 'Fuzzing disruption — random data injection into inputs',
    sideEffects: ['Unusual log entries', 'Unexpected error responses'],
    colour: 'amber',
    aftertaste: 'Slightly bitter with notes of undefined behaviour',
  },
  'stress-hot-blend': {
    ingredients: [
      { name: 'CPU Pepper', amount: 100, unit: 'grams', chaosContribution: 30, rarity: 'common' },
      { name: 'Memory Foam', amount: 2048, unit: 'MB', chaosContribution: 25, rarity: 'common' },
      { name: 'Thread Spools', amount: 500, unit: 'threads', chaosContribution: 20, rarity: 'uncommon' },
      { name: 'Heap Pressure', amount: 10, unit: 'atm', chaosContribution: 35, rarity: 'rare' },
    ],
    brewTime: 60000,
    temperature: 100,
    effect: 'Resource exhaustion — CPU, memory, and thread saturation',
    sideEffects: ['Slow response times', 'Connection timeouts', 'Service degradation'],
    colour: 'fiery red',
    aftertaste: 'Burning with a lingering sensation of resource scarcity',
  },
  'fault-injection-hot-blend': {
    ingredients: [
      { name: 'Network Latency Syrup', amount: 500, unit: 'ms', chaosContribution: 20, rarity: 'common' },
      { name: 'Packet Loss Powder', amount: 30, unit: '%', chaosContribution: 25, rarity: 'uncommon' },
      { name: 'DNS Poison Berry', amount: 5, unit: 'berries', chaosContribution: 35, rarity: 'rare' },
      { name: 'Timeout Extract', amount: 60, unit: 'seconds', chaosContribution: 20, rarity: 'common' },
    ],
    brewTime: 45000,
    temperature: 95,
    effect: 'Network fault injection — latency, packet loss, DNS failures',
    sideEffects: ['Intermittent connectivity', 'DNS resolution failures', 'Request timeouts'],
    colour: 'murky green',
    aftertaste: 'Acrid with notes of broken connections',
  },
  'randomisation-mild-blend': {
    ingredients: [
      { name: 'Shuffle Leaves', amount: 10, unit: 'leaves', chaosContribution: 10, rarity: 'common' },
      { name: 'Dice Roll Seeds', amount: 6, unit: 'seeds', chaosContribution: 8, rarity: 'common' },
      { name: 'Entropy Dew', amount: 128, unit: 'bits', chaosContribution: 15, rarity: 'uncommon' },
    ],
    brewTime: 15000,
    temperature: 70,
    effect: 'Gentle randomisation — shuffle orders, random delays, entropy injection',
    sideEffects: ['Non-deterministic test results'],
    colour: 'pale lavender',
    aftertaste: 'Light and unpredictable — like a coin flip on the tongue',
  },
  'entropy-burst-unleashed-blend': {
    ingredients: [
      { name: 'Pure Entropy Crystal', amount: 1, unit: 'crystal', chaosContribution: 50, rarity: 'legendary' },
      { name: 'Chaos Vortex Essence', amount: 5, unit: 'drops', chaosContribution: 40, rarity: 'legendary' },
      { name: 'Random Number Storm', amount: 10000, unit: 'values', chaosContribution: 30, rarity: 'rare' },
      { name: 'Bit Flip Dust', amount: 256, unit: 'bits', chaosContribution: 25, rarity: 'rare' },
      { name: 'Uncertainty Principle Tea', amount: 42, unit: 'ml', chaosContribution: 45, rarity: 'legendary' },
    ],
    brewTime: 120000,
    temperature: 120,
    effect: 'Maximum entropy burst — total chaos across all dimensions',
    sideEffects: [
      'Complete non-determinism',
      'Unpredictable system states',
      'Cascading uncertainty',
      'Butterfly effect amplification',
    ],
    colour: 'swirling void',
    aftertaste: 'Incomprehensible — your taste buds question their existence',
  },
  'circuit-break-medium-blend': {
    ingredients: [
      { name: 'Threshold Switch', amount: 5, unit: 'switches', chaosContribution: 20, rarity: 'uncommon' },
      { name: 'Failure Cascade Extract', amount: 3, unit: 'cascades', chaosContribution: 25, rarity: 'rare' },
      { name: 'Retry Storm Petals', amount: 50, unit: 'petals', chaosContribution: 15, rarity: 'common' },
    ],
    brewTime: 40000,
    temperature: 90,
    effect: 'Circuit breaker triggering — force open breakers and test fallbacks',
    sideEffects: ['Service fallback activation', 'Degraded functionality mode'],
    colour: 'electric blue',
    aftertaste: 'Sharp and intermittent — like a flickering connection',
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// TeapotBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class TeapotBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    const handler = async (input: TeapotInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-CHAOSPARTY-TEAPOT',
      'Teapot',
      handler,
      'Chaos recipe brewing with ingredient mixing, temperature control, and potency calculation'
    );

    this.log = new Logger('TeapotBot');
    this.audit = auditLedger;
  }

  private async process(input: TeapotInput): Promise<BrewResult> {
    switch (input.operation) {
      case 'BREW':
        return this.brew(input);
      default:
        throw new Error(`TeapotBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // BREW
  // ─────────────────────────────────────────────────────────────────────────

  private brew(input: TeapotInput): BrewResult {
    const { recipe, intensity, servings, sugarLevel, customIngredients, brewTimeOverride, temperatureOverride } = input;
    const intensityLevel = intensity ?? 'medium';
    const servingCount = servings ?? 1;
    const sugar = sugarLevel ?? 50;

    // Look up recipe or create a default one
    const knownRecipe = CHAOS_RECIPES[recipe];

    let ingredients: TeaIngredient[];
    let brewTime: number;
    let temperature: number;
    let effect: string;
    let sideEffects: string[];
    let teaColour: string;
    let aftertaste: string;

    if (knownRecipe) {
      ingredients = [...knownRecipe.ingredients];
      brewTime = brewTimeOverride ?? knownRecipe.brewTime;
      temperature = temperatureOverride ?? knownRecipe.temperature;
      effect = knownRecipe.effect;
      sideEffects = [...knownRecipe.sideEffects];
      teaColour = knownRecipe.colour;
      aftertaste = knownRecipe.aftertaste;
    } else {
      // Generate a default recipe based on the name
      ingredients = customIngredients?.map((ci) => ({
        ...ci,
        rarity: 'common' as const,
      })) ?? [
        { name: 'Chaos Essence', amount: 10, unit: 'ml', chaosContribution: 20, rarity: 'common' as const },
        { name: 'Disruption Powder', amount: 5, unit: 'grams', chaosContribution: 15, rarity: 'common' as const },
        { name: 'Entropy Sprinkle', amount: 128, unit: 'bits', chaosContribution: 10, rarity: 'uncommon' as const },
      ];
      brewTime = brewTimeOverride ?? 30000;
      temperature = temperatureOverride ?? 85;
      effect = `Custom brew: ${recipe}`;
      sideEffects = ['Unknown — custom recipe'];
      teaColour = 'mysterious swirl';
      aftertaste = 'Experimental — results may vary';
    }

    // Scale by intensity
    const intensityMultiplier: Record<string, number> = { mild: 0.5, medium: 1, hot: 1.5, unleashed: 2.5 };
    const multiplier = intensityMultiplier[intensityLevel] ?? 1;

    ingredients = ingredients.map((ing) => ({
      ...ing,
      chaosContribution: Math.floor(ing.chaosContribution * multiplier),
      amount: Math.floor(ing.amount * (intensityLevel === 'unleashed' ? 2 : 1)),
    }));

    // Calculate total chaos contribution
    const totalChaosContribution = ingredients.reduce((sum, ing) => sum + ing.chaosContribution, 0);

    // Calculate potency
    const maxPossibleChaos = ingredients.length * 50 * 2.5; // max per ingredient * unleashed multiplier
    const potency = Math.min(100, Math.floor((totalChaosContribution / Math.max(maxPossibleChaos, 1)) * 100));

    // Add intensity-specific side effects
    if (intensityLevel === 'hot' || intensityLevel === 'unleashed') {
      sideEffects.push('Potential system instability');
      if (intensityLevel === 'unleashed') {
        sideEffects.push('May exceed chaos containment boundaries');
      }
    }

    // Sugar level modifies the subtlety
    if (sugar < 20) {
      sideEffects.push('Bitter brew — effects may be more abrupt than expected');
    } else if (sugar > 80) {
      sideEffects.push('Over-sweetened — effects may be deceptively subtle');
    }

    // Steeping requirement based on brew time
    const steepingRequired = brewTime > 60000;

    const result: BrewResult = {
      success: true,
      recipeName: recipe,
      teaColour,
      ingredients,
      brewTime,
      temperature,
      totalChaosContribution,
      servings: servingCount,
      sugarLevel: sugar,
      effect,
      sideEffects,
      aftertaste,
      steepingRequired,
      potency,
      timestamp: Date.now(),
    };

    this.audit.append({
      actor: 'NID-CHAOSPARTY-TEAPOT',
      action: 'TEA_BREWED',
      entity: recipe,
      status: 'SUCCESS',
      meta: { intensity: intensityLevel, totalChaosContribution, potency, servings: servingCount },
    });

    this.log.info('Chaos tea brewed', {
      recipe,
      intensity: intensityLevel,
      chaosContribution: totalChaosContribution,
      potency,
    });

    return result;
  }
}
