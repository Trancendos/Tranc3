/**
 * DocUtari Hub — barrel export
 * PID-DOCUTARI
 */

export { DocUtariAI } from './DocUtariAI';
export type { DocumentMeta, TagSuggestion, FolderRule, UploadRequest, UploadResult } from './DocUtariAI';

export { FilerAgent } from './FilerAgent';
export type { FilerObservation, FilerDecision } from './FilerAgent';

export { TaggerAgent } from './TaggerAgent';
export type { TaggerInput } from './TaggerAgent';

export { ScannerBot } from './bots/ScannerBot';
export { StaplerBot } from './bots/StaplerBot';
export { FolderBot } from './bots/FolderBot';
export { ShredderBot } from './bots/ShredderBot';
