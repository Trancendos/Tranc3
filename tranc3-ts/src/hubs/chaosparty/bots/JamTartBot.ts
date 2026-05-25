/**
 * JamTartBot — Chaos Result Analysis & Flavour Assessment Bot for The Chaos Party
 *
 * Identity:  NID-CHAOSPARTY-JAMTART
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheChaosPartyAI (AID-CHAOSPARTY)
 *
 * Responsibilities:
 *   - Taste (analyse) chaos results from completed scenarios
 *   - Assess flavour profiles of chaos campaigns
 *   - Generate detailed impact and resilience reports
 *   - Score chaos effectiveness and system response quality
 *   - Provide recommendations for future chaos improvements
 *
 * "Taste this — no, not that one — the other one. Or was it this one?"
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface JamTartInput {
  operation: 'TASTE';
  scenarioId: string;
  flavour?: 'sweet' | 'sour' | 'bitter' | 'umami' | 'mixed' | 'spicy';
  detailedReport?: boolean;
  compareWithBaseline?: boolean;
}

export interface FlavourNote {
  characteristic: string;
  intensity: number; // 0..100
  description: string;
  category: 'positive' | 'negative' | 'neutral';
}

export interface ImpactMetric {
  metric: string;
  before: number;
  after: number;
  delta: number;
  unit: string;
  severity: 'none' | 'low' | 'medium' | 'high' | 'critical';
}

export interface ResilienceAssessment {
  overallScore: number; // 0..100
  categories: Array<{
    name: string;
    score: number;
    grade: 'A' | 'B' | 'C' | 'D' | 'F';
    notes: string;
  }>;
  strengths: string[];
  weaknesses: string[];
  recoveryTimeEstimate: string;
}

export interface TasteResult {
  success: boolean;
  scenarioId: string;
  flavour: NonNullable<JamTartInput['flavour']>;
  flavourProfile: {
    dominant: string;
    notes: FlavourNote[];
    complexity: number; // 0..100
    balance: number;    // 0..100
    aftertaste: string;
  };
  impactAssessment: {
    overallImpact: 'negligible' | 'minor' | 'moderate' | 'significant' | 'severe';
    metrics: ImpactMetric[];
    affectedComponents: number;
    cascadingEffects: number;
  };
  resilience: ResilienceAssessment;
  chaosEffectivenessScore: number; // 0..100 — how effective the chaos was
  recommendations: Array<{
    area: string;
    suggestion: string;
    priority: 'low' | 'medium' | 'high';
  }>;
  verdict: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// JamTartBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class JamTartBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly tasteHistory: Map<string, Array<{
    flavour: string;
    effectivenessScore: number;
    timestamp: number;
  }>>;

  constructor() {
    const handler = async (input: JamTartInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-CHAOSPARTY-JAMTART',
      'JamTart',
      handler,
      'Chaos result tasting with flavour profiling, impact assessment, and resilience scoring'
    );

    this.log = new Logger('JamTartBot');
    this.audit = AuditLedger.getInstance();
    this.tasteHistory = new Map();
  }

  private async process(input: JamTartInput): Promise<TasteResult> {
    switch (input.operation) {
      case 'TASTE':
        return this.taste(input);
      default:
        throw new Error(`JamTartBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // TASTE
  // ─────────────────────────────────────────────────────────────────────────

  private taste(input: JamTartInput): TasteResult {
    const { scenarioId, flavour, detailedReport, compareWithBaseline } = input;
    const selectedFlavour = flavour ?? 'mixed';

    // Generate flavour profile based on selected flavour
    const flavourProfile = this.generateFlavourProfile(selectedFlavour);

    // Generate impact assessment
    const impactAssessment = this.generateImpactAssessment(selectedFlavour, detailedReport ?? false);

    // Generate resilience assessment
    const resilience = this.generateResilienceAssessment(selectedFlavour);

    // Calculate chaos effectiveness score
    const chaosEffectivenessScore = this.calculateEffectiveness(
      impactAssessment,
      resilience,
      selectedFlavour
    );

    // Generate recommendations
    const recommendations = this.generateRecommendations(
      impactAssessment,
      resilience,
      chaosEffectivenessScore
    );

    // Generate verdict
    const verdict = this.generateVerdict(chaosEffectivenessScore, selectedFlavour);

    // Store in taste history
    const history = this.tasteHistory.get(scenarioId) ?? [];
    history.push({
      flavour: selectedFlavour,
      effectivenessScore: chaosEffectivenessScore,
      timestamp: Date.now(),
    });
    this.tasteHistory.set(scenarioId, history);

    const result: TasteResult = {
      success: true,
      scenarioId,
      flavour: selectedFlavour,
      flavourProfile,
      impactAssessment,
      resilience,
      chaosEffectivenessScore,
      recommendations,
      verdict,
      timestamp: Date.now(),
    };

    this.audit.append({
      actor: 'NID-CHAOSPARTY-JAMTART',
      action: 'CHAOS_TASTED',
      entity: scenarioId,
      status: 'SUCCESS',
      meta: {
        flavour: selectedFlavour,
        effectivenessScore: chaosEffectivenessScore,
        overallImpact: impactAssessment.overallImpact,
        resilienceScore: resilience.overallScore,
      },
    });

    this.log.info('Chaos tasted', {
      scenarioId,
      flavour: selectedFlavour,
      effectivenessScore: chaosEffectivenessScore,
      overallImpact: impactAssessment.overallImpact,
    });

    return result;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Flavour Profile Generation
  // ─────────────────────────────────────────────────────────────────────────

  private generateFlavourProfile(flavour: NonNullable<JamTartInput['flavour']>): TasteResult['flavourProfile'] {
    const profiles: Record<string, {
      dominant: string;
      notes: FlavourNote[];
      complexity: number;
      balance: number;
      aftertaste: string;
    }> = {
      sweet: {
        dominant: 'Gentle Disruption',
        notes: [
          { characteristic: 'Predictability', intensity: 30, description: 'Chaos was well-contained and predictable', category: 'positive' },
          { characteristic: 'Smooth Transitions', intensity: 60, description: 'System transitions were graceful under chaos', category: 'positive' },
          { characteristic: 'Recovery Speed', intensity: 75, description: 'System recovered quickly from disruptions', category: 'positive' },
          { characteristic: 'Visibility', intensity: 45, description: 'Chaos effects were clearly observable', category: 'neutral' },
        ],
        complexity: 25,
        balance: 80,
        aftertaste: 'Pleasant — the chaos was productive without being destructive',
      },
      sour: {
        dominant: 'Unpleasant Surprises',
        notes: [
          { characteristic: 'Unexpected Failures', intensity: 65, description: 'Some failures were not anticipated', category: 'negative' },
          { characteristic: 'Error Handling', intensity: 40, description: 'Error handling showed gaps under stress', category: 'negative' },
          { characteristic: 'Edge Cases', intensity: 70, description: 'Edge cases surfaced that were not covered', category: 'neutral' },
          { characteristic: 'Recovery', intensity: 55, description: 'Recovery was possible but messy', category: 'neutral' },
        ],
        complexity: 55,
        balance: 35,
        aftertaste: 'Tart — the chaos revealed weaknesses that need addressing',
      },
      bitter: {
        dominant: 'Harsh Impact',
        notes: [
          { characteristic: 'Data Loss Risk', intensity: 80, description: 'Near data loss scenarios encountered', category: 'negative' },
          { characteristic: 'Cascading Failures', intensity: 75, description: 'Failures cascaded beyond expected boundaries', category: 'negative' },
          { characteristic: 'Timeout Storms', intensity: 60, description: 'Timeout propagation created storms', category: 'negative' },
          { characteristic: 'Recovery Difficulty', intensity: 85, description: 'Recovery required significant manual intervention', category: 'negative' },
        ],
        complexity: 70,
        balance: 15,
        aftertaste: 'Harsh — the chaos caused real damage that was difficult to undo',
      },
      umami: {
        dominant: 'Deep Insight',
        notes: [
          { characteristic: 'Architecture Understanding', intensity: 85, description: 'Chaos revealed deep architectural insights', category: 'positive' },
          { characteristic: 'Hidden Dependencies', intensity: 90, description: 'Previously unknown dependencies surfaced', category: 'positive' },
          { characteristic: 'Performance Characteristics', intensity: 70, description: 'True performance limits discovered', category: 'positive' },
          { characteristic: 'Resilience Patterns', intensity: 65, description: 'Existing resilience patterns proved effective', category: 'positive' },
        ],
        complexity: 85,
        balance: 65,
        aftertaste: 'Rich and revealing — the chaos was deeply informative',
      },
      mixed: {
        dominant: 'Balanced Results',
        notes: [
          { characteristic: 'Partial Success', intensity: 60, description: 'Some chaos objectives met, others missed', category: 'neutral' },
          { characteristic: 'Inconsistent Impact', intensity: 55, description: 'Impact varied across different system components', category: 'neutral' },
          { characteristic: 'Recovery Inconsistency', intensity: 50, description: 'Some components recovered well, others struggled', category: 'neutral' },
          { characteristic: 'Mixed Signals', intensity: 70, description: 'Results are ambiguous — further testing recommended', category: 'neutral' },
        ],
        complexity: 65,
        balance: 45,
        aftertaste: 'Ambiguous — results are a mixed bag requiring further analysis',
      },
      spicy: {
        dominant: 'Intense Disruption',
        notes: [
          { characteristic: 'Performance Impact', intensity: 90, description: 'Significant performance degradation observed', category: 'negative' },
          { characteristic: 'Hot Spots', intensity: 85, description: 'Specific components became critical bottlenecks', category: 'negative' },
          { characteristic: 'Resource Exhaustion', intensity: 80, description: 'Resource limits were reached and tested', category: 'neutral' },
          { characteristic: 'Breakthrough', intensity: 70, description: 'Chaos pushed through resilience barriers', category: 'neutral' },
        ],
        complexity: 75,
        balance: 25,
        aftertaste: 'Burning — the chaos was intense and pushed systems to their limits',
      },
    };

    return profiles[flavour] ?? profiles.mixed;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Impact Assessment Generation
  // ─────────────────────────────────────────────────────────────────────────

  private generateImpactAssessment(
    flavour: NonNullable<JamTartInput['flavour']>,
    detailed: boolean
  ): TasteResult['impactAssessment'] {
    // Impact severity by flavour
    const impactByFlavour: Record<string, TasteResult['impactAssessment']['overallImpact']> = {
      sweet: 'negligible',
      sour: 'minor',
      bitter: 'severe',
      umami: 'moderate',
      mixed: 'moderate',
      spicy: 'significant',
    };

    const overallImpact = impactByFlavour[flavour] ?? 'moderate';

    // Generate metrics
    const metrics: ImpactMetric[] = [
      {
        metric: 'Response Time',
        before: 50,
        after: flavour === 'spicy' ? 2500 : flavour === 'bitter' ? 1500 : 200,
        delta: flavour === 'spicy' ? 2450 : flavour === 'bitter' ? 1450 : 150,
        unit: 'ms',
        severity: flavour === 'spicy' ? 'critical' : flavour === 'bitter' ? 'high' : 'low',
      },
      {
        metric: 'Error Rate',
        before: 0.1,
        after: flavour === 'bitter' ? 15 : flavour === 'spicy' ? 8 : 2,
        delta: flavour === 'bitter' ? 14.9 : flavour === 'spicy' ? 7.9 : 1.9,
        unit: '%',
        severity: flavour === 'bitter' ? 'critical' : flavour === 'spicy' ? 'high' : 'medium',
      },
      {
        metric: 'Availability',
        before: 99.9,
        after: flavour === 'bitter' ? 85.0 : flavour === 'spicy' ? 92.0 : 98.5,
        delta: -(flavour === 'bitter' ? 14.9 : flavour === 'spicy' ? 7.9 : 1.4),
        unit: '%',
        severity: flavour === 'bitter' ? 'critical' : flavour === 'spicy' ? 'high' : 'low',
      },
      {
        metric: 'Throughput',
        before: 1000,
        after: flavour === 'bitter' ? 100 : flavour === 'spicy' ? 300 : 750,
        delta: -(flavour === 'bitter' ? 900 : flavour === 'spicy' ? 700 : 250),
        unit: 'req/s',
        severity: flavour === 'bitter' ? 'critical' : flavour === 'spicy' ? 'high' : 'medium',
      },
    ];

    if (detailed) {
      metrics.push(
        {
          metric: 'Memory Usage',
          before: 45,
          after: flavour === 'bitter' ? 95 : 65,
          delta: flavour === 'bitter' ? 50 : 20,
          unit: '%',
          severity: flavour === 'bitter' ? 'high' : 'medium',
        },
        {
          metric: 'CPU Usage',
          before: 30,
          after: flavour === 'spicy' ? 99 : flavour === 'bitter' ? 90 : 55,
          delta: flavour === 'spicy' ? 69 : flavour === 'bitter' ? 60 : 25,
          unit: '%',
          severity: flavour === 'spicy' ? 'critical' : flavour === 'bitter' ? 'high' : 'medium',
        },
        {
          metric: 'Disk I/O',
          before: 5000,
          after: flavour === 'bitter' ? 1000 : 3500,
          delta: -(flavour === 'bitter' ? 4000 : 1500),
          unit: 'IOPS',
          severity: flavour === 'bitter' ? 'high' : 'medium',
        }
      );
    }

    const affectedComponents = flavour === 'bitter' ? 8 : flavour === 'spicy' ? 6 : flavour === 'sweet' ? 2 : 4;
    const cascadingEffects = flavour === 'bitter' ? 5 : flavour === 'spicy' ? 3 : 1;

    return {
      overallImpact,
      metrics,
      affectedComponents,
      cascadingEffects,
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Resilience Assessment Generation
  // ─────────────────────────────────────────────────────────────────────────

  private generateResilienceAssessment(
    flavour: NonNullable<JamTartInput['flavour']>
  ): ResilienceAssessment {
    // Base scores by flavour
    const baseScoreByFlavour: Record<string, number> = {
      sweet: 90, sour: 65, bitter: 25, umami: 70, mixed: 55, spicy: 35,
    };

    const baseScore = baseScoreByFlavour[flavour] ?? 55;
    const jitter = Math.floor(Math.random() * 10) - 5;
    const overallScore = Math.max(0, Math.min(100, baseScore + jitter));

    const categories: ResilienceAssessment['categories'] = [
      {
        name: 'Fault Tolerance',
        score: Math.max(0, Math.min(100, overallScore + Math.floor(Math.random() * 20) - 10)),
        grade: 'B',
        notes: flavour === 'sweet' ? 'System handled faults gracefully' : 'Fault tolerance needs improvement',
      },
      {
        name: 'Recovery Speed',
        score: Math.max(0, Math.min(100, overallScore + Math.floor(Math.random() * 15) - 5)),
        grade: 'B',
        notes: flavour === 'bitter' ? 'Recovery was slow and manual' : 'Recovery was within acceptable bounds',
      },
      {
        name: 'Graceful Degradation',
        score: Math.max(0, Math.min(100, overallScore + Math.floor(Math.random() * 25) - 15)),
        grade: 'C',
        notes: flavour === 'spicy' ? 'Degradation was not graceful — hard failures observed' : 'System degraded acceptably under load',
      },
      {
        name: 'Observability',
        score: Math.max(0, Math.min(100, overallScore + Math.floor(Math.random() * 10))),
        grade: 'B',
        notes: 'Chaos effects were observable through existing monitoring',
      },
    ];

    // Assign grades
    for (const cat of categories) {
      if (cat.score >= 90) cat.grade = 'A';
      else if (cat.score >= 80) cat.grade = 'B';
      else if (cat.score >= 65) cat.grade = 'C';
      else if (cat.score >= 50) cat.grade = 'D';
      else cat.grade = 'F';
    }

    const strengths = categories
      .filter((c) => c.score >= 70)
      .map((c) => `${c.name}: ${c.grade} (${c.score}/100)`);
    const weaknesses = categories
      .filter((c) => c.score < 70)
      .map((c) => `${c.name}: ${c.grade} (${c.score}/100) — ${c.notes}`);

    const recoveryTimeEstimate = overallScore >= 80
      ? '< 1 minute (automated recovery)'
      : overallScore >= 60
        ? '1-5 minutes (mostly automated)'
        : overallScore >= 40
          ? '5-30 minutes (manual intervention required)'
          : '30+ minutes (significant manual effort)';

    return {
      overallScore,
      categories,
      strengths,
      weaknesses,
      recoveryTimeEstimate,
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Effectiveness Calculation
  // ─────────────────────────────────────────────────────────────────────────

  private calculateEffectiveness(
    impact: TasteResult['impactAssessment'],
    resilience: ResilienceAssessment,
    flavour: NonNullable<JamTartInput['flavour']>
  ): number {
    // Effectiveness = how well the chaos exposed weaknesses
    // High impact + low resilience = highly effective chaos
    // Low impact + high resilience = chaos was absorbed (less effective at finding issues)

    const impactWeights: Record<string, number> = {
      negligible: 10, minor: 25, moderate: 50, significant: 75, severe: 90,
    };
    const impactScore = impactWeights[impact.overallImpact] ?? 50;

    // Invert resilience — if system was very resilient, chaos was less effective at breaking it
    const disruptionScore = 100 - resilience.overallScore;

    // Combined: chaos is effective when it disrupts but the key metric is
    // whether it found real issues (umami is most effective)
    const flavourBonus: Record<string, number> = {
      umami: 20, bitter: 15, spicy: 10, mixed: 5, sour: 5, sweet: -10,
    };

    const effectiveness = Math.floor(
      (impactScore * 0.4 + disruptionScore * 0.4 + (flavourBonus[flavour] ?? 0)) * 1.0
    );

    return Math.max(0, Math.min(100, effectiveness));
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Recommendations Generation
  // ─────────────────────────────────────────────────────────────────────────

  private generateRecommendations(
    impact: TasteResult['impactAssessment'],
    resilience: ResilienceAssessment,
    effectiveness: number
  ): TasteResult['recommendations'] {
    const recommendations: TasteResult['recommendations'] = [];

    // Based on resilience weaknesses
    for (const weakness of resilience.weaknesses) {
      recommendations.push({
        area: weakness.split(':')[0].trim(),
        suggestion: `Improve ${weakness.split(':')[0].trim().toLowerCase()} — consider adding redundancy and automated recovery`,
        priority: effectiveness > 60 ? 'high' : 'medium',
      });
    }

    // Based on impact severity
    if (impact.cascadingEffects > 2) {
      recommendations.push({
        area: 'Cascading Failures',
        suggestion: 'Implement bulkheads and circuit breakers to prevent failure propagation',
        priority: 'high',
      });
    }

    if (impact.affectedComponents > 5) {
      recommendations.push({
        area: 'Blast Radius',
        suggestion: 'Reduce coupling between components to limit the blast radius of failures',
        priority: 'high',
      });
    }

    // General recommendation
    if (effectiveness < 40) {
      recommendations.push({
        area: 'Chaos Intensity',
        suggestion: 'Increase chaos intensity — current scenarios are not sufficiently challenging the system',
        priority: 'medium',
      });
    } else if (effectiveness > 80) {
      recommendations.push({
        area: 'Remediation',
        suggestion: 'Prioritise fixing the weaknesses exposed — chaos testing has been highly effective',
        priority: 'high',
      });
    }

    return recommendations;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Verdict Generation
  // ─────────────────────────────────────────────────────────────────────────

  private generateVerdict(
    effectiveness: number,
    flavour: NonNullable<JamTartInput['flavour']>
  ): string {
    if (effectiveness >= 80) {
      return `Highly effective chaos — the ${flavour} flavour revealed critical weaknesses that require immediate attention.`;
    } else if (effectiveness >= 60) {
      return `Productive chaos — the ${flavour} flavour exposed meaningful issues worth investigating and addressing.`;
    } else if (effectiveness >= 40) {
      return `Moderate chaos — the ${flavour} flavour showed some areas for improvement but the system largely held.`;
    } else if (effectiveness >= 20) {
      return `Mild chaos — the ${flavour} flavour barely disturbed the system. Consider escalating intensity.`;
    } else {
      return `Ineffective chaos — the ${flavour} flavour was completely absorbed. The system is either very resilient or the chaos was too mild.`;
    }
  }
}
