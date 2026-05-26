/**
 * Arcadia Hub — barrel exports
 */

// AI
export { ArcadiaAI, ArcadiaConfig, ArcadiaState, ArcadiaHealth } from './ArcadiaAI';

// Agents
export { ForumModAgent, ForumActivity, ModerationDecision, ModerationResult, FilterRule, ActivityType, Severity } from './agents/ForumModAgent';
export { CampaignMgrAgent, Campaign, CampaignVariant, CampaignMetrics, CampaignDecision, CampaignResult, CampaignStatus, CampaignPriority, AudienceSegment, VariantMetrics } from './agents/CampaignMgrAgent';

// Bots
export { MailSorterBot, IncomingMail, SortedMail, MailCategory, MailPriority } from './bots/MailSorterBot';
export { ThreadPumperBot, ThreadBoostRequest, ThreadBoostResult } from './bots/ThreadPumperBot';
export { UIRendererBot, RenderRequest, RenderResult, UIComponent } from './bots/UIRendererBot';
export { CacheFetchBot, CacheRequest, CacheResult } from './bots/CacheFetchBot';
