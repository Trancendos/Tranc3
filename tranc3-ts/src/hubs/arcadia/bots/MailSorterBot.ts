/**
 * MailSorter Bot — Arcadia Tier 5 Bot (NID-ARCADIA-MAIL-SORTER)
 *
 * Classifies incoming mail into categories for routing.
 * Uses keyword analysis and priority detection to determine
 * the appropriate category and urgency level.
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('MailSorterBot');

/** Mail classification categories */
export type MailCategory = 'INBOX' | 'PROMOTION' | 'SOCIAL' | 'ALERT' | 'SPAM' | 'SYSTEM';

/** Mail priority levels */
export type MailPriority = 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT';

/** Incoming mail structure */
export interface IncomingMail {
  from: string;
  subject: string;
  body: string;
  priority?: string;
  timestamp?: Date;
}

/** Sorted mail result */
export interface SortedMail {
  category: MailCategory;
  priority: MailPriority;
  tags: string[];
  routingTarget: string;
  confidence: number;
}

export class MailSorterBot extends Bot {
  constructor() {
    super(
      'MailSorter',
      async (mail: IncomingMail): Promise<SortedMail> => {
        const category = classifyMail(mail);
        const priority = detectPriority(mail);
        const tags = extractTags(mail);
        const routingTarget = getRoutingTarget(category);
        const confidence = calculateConfidence(mail, category);

        logger.debug('Mail sorted', {
          from: mail.from,
          category,
          priority,
          confidence,
        });

        return { category, priority, tags, routingTarget, confidence };
      },
      'Classifies incoming mail into categories and priority levels for routing',
    );
  }
}

/** Classify mail based on content analysis */
function classifyMail(mail: IncomingMail): MailCategory {
  const subjectLower = mail.subject.toLowerCase();
  const bodyLower = mail.body.toLowerCase();
  const combined = `${subjectLower} ${bodyLower}`;

  // System notifications
  if (combined.includes('system') || combined.includes('alert') || combined.includes('critical')) {
    return 'ALERT';
  }

  // Social / community
  if (combined.includes('reply') || combined.includes('comment') || combined.includes('mention') || combined.includes('follow')) {
    return 'SOCIAL';
  }

  // Promotions
  if (combined.includes('offer') || combined.includes('discount') || combined.includes('sale') || combined.includes('deal')) {
    return 'PROMOTION';
  }

  // Spam detection
  if (combined.includes('viagra') || combined.includes('lottery') || combined.includes('winner') || combined.includes('prince')) {
    return 'SPAM';
  }

  // System-generated
  if (mail.from.includes('noreply') || mail.from.includes('no-reply') || mail.from.includes('daemon')) {
    return 'SYSTEM';
  }

  return 'INBOX';
}

/** Detect priority from mail content */
function detectPriority(mail: IncomingMail): MailPriority {
  const subjectLower = mail.subject.toLowerCase();

  if (subjectLower.includes('urgent') || subjectLower.includes('critical') || subjectLower.includes('emergency')) {
    return 'URGENT';
  }
  if (subjectLower.includes('important') || subjectLower.includes('action required') || subjectLower.includes('attention')) {
    return 'HIGH';
  }
  if (mail.priority === 'high') return 'HIGH';
  if (mail.priority === 'low') return 'LOW';

  return 'NORMAL';
}

/** Extract tags from mail content */
function extractTags(mail: IncomingMail): string[] {
  const tags: string[] = [];
  const combined = `${mail.subject} ${mail.body}`.toLowerCase();

  const tagPatterns: Record<string, string[]> = {
    'bug': ['bug', 'error', 'crash', 'fail'],
    'feature': ['feature', 'request', 'enhancement', 'suggestion'],
    'security': ['security', 'vulnerability', 'breach', 'exploit'],
    'billing': ['billing', 'payment', 'invoice', 'charge'],
    'support': ['help', 'support', 'question', 'how-to'],
  };

  for (const [tag, patterns] of Object.entries(tagPatterns)) {
    if (patterns.some(p => combined.includes(p))) {
      tags.push(tag);
    }
  }

  return tags;
}

/** Determine routing target based on category */
function getRoutingTarget(category: MailCategory): string {
  const routingMap: Record<MailCategory, string> = {
    INBOX: 'user-inbox',
    PROMOTION: 'promo-folder',
    SOCIAL: 'social-feed',
    ALERT: 'alert-queue',
    SPAM: 'spam-quarantine',
    SYSTEM: 'system-log',
  };
  return routingMap[category];
}

/** Calculate classification confidence */
function calculateConfidence(mail: IncomingMail, category: MailCategory): number {
  // Simple heuristic: more specific categories get higher confidence
  const baseConfidence: Record<MailCategory, number> = {
    SPAM: 0.85,
    ALERT: 0.80,
    SYSTEM: 0.75,
    SOCIAL: 0.70,
    PROMOTION: 0.65,
    INBOX: 0.40, // Default/catch-all has lower confidence
  };
  return baseConfidence[category];
}
