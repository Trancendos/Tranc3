/**
 * The Filer — DocUtari Tier 4 Agent (SID-DOCUTARI-FILER)
 *
 * Decides the folder path for a document based on tags,
 * user override, and configured folder rules.
 */

import { Agent, Logger, AuditLedger } from '../../core/definitions';
import type { FolderRule } from './DocUtariAI';

export interface FilerObservation {
  tags: string[];
  overrideFolder?: string;
  rules: FolderRule[];
}

export interface FilerDecision {
  folderPath: string;
  matchedRule?: string;
  reason: string;
}

export class FilerAgent extends Agent {
  public readonly id = 'SID-DOCUTARI-FILER';
  public readonly name = 'The Filer';

  constructor(
    private readonly audit: AuditLedger,
    private readonly logger: Logger,
  ) {
    super();
  }

  async perceive(observation: FilerObservation): Promise<FilerObservation> {
    return observation;
  }

  async decide(observation: FilerObservation): Promise<string> {
    const perceived = await this.perceive(observation);
    const result = await this.act(perceived);
    return result.folderPath;
  }

  async act(observation: FilerObservation): Promise<FilerDecision> {
    // 1. User override wins
    if (observation.overrideFolder) {
      await this.audit.append({
        actor: this.id,
        action: 'folder.override',
        entity: observation.overrideFolder,
        meta: { reason: 'user_override' },
      });
      return {
        folderPath: observation.overrideFolder,
        reason: 'User-specified override folder',
      };
    }

    // 2. Evaluate folder rules by priority (descending)
    const enabledRules = observation.rules
      .filter(r => r.enabled)
      .sort((a, b) => b.priority - a.priority);

    for (const rule of enabledRules) {
      const regex = new RegExp(rule.pattern, 'i');
      const matchesTag = observation.tags.some(t => regex.test(t));
      if (matchesTag) {
        this.logger.info(`Filer: rule "${rule.ruleId}" matched`, { pattern: rule.pattern, folder: rule.targetFolder });
        await this.audit.append({
          actor: this.id,
          action: 'folder.rule_match',
          entity: rule.targetFolder,
          meta: { ruleId: rule.ruleId, pattern: rule.pattern },
        });
        return {
          folderPath: rule.targetFolder,
          matchedRule: rule.ruleId,
          reason: `Matched rule ${rule.ruleId} with pattern ${rule.pattern}`,
        };
      }
    }

    // 3. Tag-based default mapping
    const tagFolder = this.inferFolderFromTags(observation.tags);
    if (tagFolder) {
      await this.audit.append({
        actor: this.id,
        action: 'folder.inferred',
        entity: tagFolder,
        meta: { tags: observation.tags },
      });
      return {
        folderPath: tagFolder,
        reason: 'Inferred from tag semantics',
      };
    }

    // 4. Fallback
    return {
      folderPath: '/unsorted',
      reason: 'No rule match or tag inference; defaulted to /unsorted',
    };
  }

  private inferFolderFromTags(tags: string[]): string | null {
    const tagLower = tags.map(t => t.toLowerCase());
    if (tagLower.some(t => ['invoice', 'receipt', 'billing'].includes(t))) return '/finance';
    if (tagLower.some(t => ['contract', 'agreement', 'legal'].includes(t))) return '/legal';
    if (tagLower.some(t => ['report', 'analysis', 'data'].includes(t))) return '/reports';
    if (tagLower.some(t => ['photo', 'image', 'media'].includes(t))) return '/media';
    if (tagLower.some(t => ['code', 'dev', 'engineering'].includes(t))) return '/engineering';
    return null;
  }
}
