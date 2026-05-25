/**
 * CampaignMgr Agent — Arcadia Tier 4 Agent (SID-ARCADIA-CAMPAIGN)
 *
 * Autonomous microservice for campaign management.
 * Handles campaign scheduling, audience targeting, A/B testing,
 * performance tracking, and automated campaign lifecycle management.
 *
 * Perceive: Analyze campaign request, audience data, and timing
 * Decide: Determine targeting, scheduling, and variant allocation
 * Act: Launch campaign, track performance, and adjust parameters
 */

import { AuditLedger, Agent, Bot } from '../../../core/definitions'
import { Logger } from '../../../core/logger';

const logger = new Logger('CampaignMgrAgent');

/** Campaign status lifecycle */
export type CampaignStatus = 'DRAFT' | 'SCHEDULED' | 'ACTIVE' | 'PAUSED' | 'COMPLETED' | 'CANCELLED';

/** Campaign priority level */
export type CampaignPriority = 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT';

/** Audience segment definition */
export interface AudienceSegment {
  name: string;
  criteria: Record<string, any>;
  estimatedSize: number;
  priority: CampaignPriority;
}

/** Campaign definition */
export interface Campaign {
  id: string;
  name: string;
  description: string;
  status: CampaignStatus;
  priority: CampaignPriority;
  segments: AudienceSegment[];
  startDate: Date;
  endDate: Date;
  budget: number;
  variants: CampaignVariant[];
  metrics: CampaignMetrics;
  createdAt: Date;
  updatedAt: Date;
}

/** A/B test variant */
export interface CampaignVariant {
  id: string;
  name: string;
  content: Record<string, any>;
  allocationPercent: number;
  metrics: VariantMetrics;
}

/** Variant performance metrics */
export interface VariantMetrics {
  impressions: number;
  clicks: number;
  conversions: number;
  revenue: number;
  ctr: number;
  conversionRate: number;
}

/** Overall campaign metrics */
export interface CampaignMetrics {
  totalImpressions: number;
  totalClicks: number;
  totalConversions: number;
  totalRevenue: number;
  overallCtr: number;
  overallConversionRate: number;
  costPerConversion: number;
}

/** Campaign decision outcome */
export interface CampaignDecision {
  action: 'LAUNCH' | 'PAUSE' | 'RESUME' | 'ADJUST_BUDGET' | 'SWAP_VARIANT' | 'COMPLETE' | 'CANCEL';
  reason: string;
  variantId?: string;
  budgetAdjustment?: number;
  confidence: number;
}

/** Campaign execution result */
export interface CampaignResult {
  decision: CampaignDecision;
  campaignId: string;
  auditId: string;
  timestamp: Date;
}

export class CampaignMgrAgent extends Agent {
  private readonly audit: AuditLedger;
  private readonly campaigns: Map<string, Campaign> = new Map();
  private readonly scheduledActions: Map<string, NodeJS.Timeout> = new Map();

  constructor(id: string, audit: AuditLedger) {
    super(id);
    this.audit = audit;
    logger.info('CampaignMgrAgent initialized', { id });
  }

  /**
   * Perceive: Analyze campaign request or performance update.
   */
  async perceive(observation: any): Promise<Partial<Campaign>> {
    const campaignData: Partial<Campaign> = {
      id: observation?.id || `camp-${Date.now()}`,
      name: observation?.name || 'Untitled Campaign',
      description: observation?.description || '',
      status: observation?.status || 'DRAFT',
      priority: observation?.priority || 'NORMAL',
      segments: observation?.segments || [],
      startDate: observation?.startDate ? new Date(observation.startDate) : new Date(),
      endDate: observation?.endDate ? new Date(observation.endDate) : new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
      budget: observation?.budget || 0,
      variants: observation?.variants || [],
      metrics: observation?.metrics || {
        totalImpressions: 0,
        totalClicks: 0,
        totalConversions: 0,
        totalRevenue: 0,
        overallCtr: 0,
        overallConversionRate: 0,
        costPerConversion: 0,
      },
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    logger.debug('Perceived campaign data', { id: campaignData.id, name: campaignData.name });
    return campaignData;
  }

  /**
   * Decide: Determine the optimal campaign action.
   */
  async decide(perceived: Partial<Campaign>): Promise<CampaignDecision> {
    const existing = perceived.id ? this.campaigns.get(perceived.id) : null;
    const status = perceived.status || existing?.status || 'DRAFT';

    // Decision logic based on current state
    if (status === 'DRAFT') {
      // Validate campaign readiness
      const hasSegments = (perceived.segments?.length || 0) > 0;
      const hasVariants = (perceived.variants?.length || 0) > 0;
      const hasBudget = (perceived.budget || 0) > 0;

      if (hasSegments && hasVariants && hasBudget) {
        return {
          action: 'LAUNCH',
          reason: 'Campaign fully configured and ready to launch',
          confidence: 0.85,
        };
      } else {
        return {
          action: 'CANCEL',
          reason: `Campaign incomplete: segments=${hasSegments}, variants=${hasVariants}, budget=${hasBudget}`,
          confidence: 0.9,
        };
      }
    }

    if (status === 'ACTIVE' && existing) {
      const metrics = existing.metrics;

      // Check if campaign is underperforming
      if (metrics.overallCtr < 0.01 && metrics.totalImpressions > 1000) {
        return {
          action: 'PAUSE',
          reason: `CTR ${metrics.overallCtr} below threshold after ${metrics.totalImpressions} impressions`,
          confidence: 0.75,
        };
      }

      // Check if campaign has exceeded budget efficiently
      if (metrics.totalConversions > 0 && metrics.costPerConversion < existing.budget * 0.5) {
        return {
          action: 'ADJUST_BUDGET',
          reason: `Good performance: cost/conversion ${metrics.costPerConversion} under 50% budget`,
          budgetAdjustment: existing.budget * 0.3,
          confidence: 0.7,
        };
      }

      // Check if best variant should get more allocation
      if (perceived.variants && perceived.variants.length > 1) {
        const sorted = [...perceived.variants].sort((a, b) => b.metrics.conversionRate - a.metrics.conversionRate);
        if (sorted[0].metrics.conversionRate > sorted[1].metrics.conversionRate * 1.5) {
          return {
            action: 'SWAP_VARIANT',
            reason: `Variant ${sorted[0].id} significantly outperforming ${sorted[1].id}`,
            variantId: sorted[0].id,
            confidence: 0.8,
          };
        }
      }

      // Check if campaign should complete
      if (existing.endDate && new Date() > existing.endDate) {
        return {
          action: 'COMPLETE',
          reason: 'Campaign end date reached',
          confidence: 0.95,
        };
      }
    }

    // Default: maintain current state
    return {
      action: 'LAUNCH',
      reason: 'Default decision — proceed with current trajectory',
      confidence: 0.5,
    };
  }

  /**
   * Act: Execute the campaign decision.
   */
  async act(decision: CampaignDecision): Promise<CampaignResult> {
    const auditId = await this.audit.append({
      actor: this.id,
      action: `CAMPAIGN_${decision.action}`,
      entity: 'campaign',
      status: decision.confidence >= 0.7 ? 'SUCCESS' : 'PENDING',
      meta: {
        reason: decision.reason,
        confidence: decision.confidence,
        variantId: decision.variantId,
        budgetAdjustment: decision.budgetAdjustment,
      },
    });

    logger.info('Campaign action executed', {
      action: decision.action,
      reason: decision.reason,
      confidence: decision.confidence,
    });

    return {
      decision,
      campaignId: this.state.currentCampaignId || 'unknown',
      auditId,
      timestamp: new Date(),
    };
  }

  /** Store a campaign */
  storeCampaign(campaign: Campaign): void {
    this.campaigns.set(campaign.id, campaign);
    this.state.currentCampaignId = campaign.id;
    logger.info('Campaign stored', { id: campaign.id, name: campaign.name });
  }

  /** Get a campaign by ID */
  getCampaign(id: string): Campaign | undefined {
    return this.campaigns.get(id);
  }

  /** List all campaign IDs */
  listCampaigns(): string[] {
    return Array.from(this.campaigns.keys());
  }
}
