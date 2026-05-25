/**
 * The Tagger — DocUtari Tier 4 Agent (SID-DOCUTARI-TAGGER)
 *
 * Produces auto-tag suggestions from document content.
 * Uses keyword extraction, rule-based matching, and
 * (placeholder) ML confidence scoring.
 */

import { Agent, Logger, AuditLedger } from '../../core/definitions';
import type { TagSuggestion } from './DocUtariAI';

export interface TaggerInput {
  extractedText: string;
  fileName: string;
  mimeType: string;
}

/* keyword → tag rule set (extensible) */
const KEYWORD_RULES: Array<{ keywords: string[]; tag: string; confidence: number }> = [
  { keywords: ['invoice', 'amount due', 'bill to'], tag: 'invoice', confidence: 0.85 },
  { keywords: ['contract', 'agreement', 'parties'], tag: 'contract', confidence: 0.8 },
  { keywords: ['report', 'summary', 'findings'], tag: 'report', confidence: 0.75 },
  { keywords: ['meeting', 'agenda', 'minutes'], tag: 'meeting-notes', confidence: 0.8 },
  { keywords: ['resume', 'curriculum vitae', 'work experience'], tag: 'resume', confidence: 0.85 },
  { keywords: ['budget', 'forecast', 'fiscal'], tag: 'finance', confidence: 0.75 },
  { keywords: ['policy', 'guideline', 'compliance'], tag: 'policy', confidence: 0.8 },
  { keywords: ['design', 'mockup', 'wireframe', 'prototype'], tag: 'design', confidence: 0.7 },
  { keywords: ['api', 'endpoint', 'request', 'response'], tag: 'technical', confidence: 0.7 },
  { keywords: ['image', 'photo', 'screenshot', 'png', 'jpg'], tag: 'media', confidence: 0.65 },
];

/* MIME-based tag fallback */
const MIME_TAG_MAP: Record<string, string> = {
  'application/pdf': 'pdf',
  'image/png': 'image',
  'image/jpeg': 'image',
  'image/gif': 'image',
  'text/csv': 'spreadsheet',
  'application/vnd.ms-excel': 'spreadsheet',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'spreadsheet',
  'application/msword': 'document',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'document',
  'text/plain': 'text',
  'text/markdown': 'markdown',
  'application/json': 'data',
  'text/html': 'web',
};

export class TaggerAgent extends Agent {
  public readonly id = 'SID-DOCUTARI-TAGGER';
  public readonly name = 'The Tagger';

  constructor(
    private readonly audit: AuditLedger,
    private readonly logger: Logger,
  ) {
    super();
  }

  async perceive(input: TaggerInput): Promise<TaggerInput> {
    return input;
  }

  async decide(input: TaggerInput): Promise<TagSuggestion[]> {
    const perceived = await this.perceive(input);
    const results = await this.act(perceived);
    return results;
  }

  async act(input: TaggerInput): Promise<TagSuggestion[]> {
    const suggestions: TagSuggestion[] = [];
    const textLower = input.extractedText.toLowerCase();
    const fileNameLower = input.fileName.toLowerCase();

    // 1. Keyword rules against extracted text
    for (const rule of KEYWORD_RULES) {
      const matched = rule.keywords.some(kw => textLower.includes(kw) || fileNameLower.includes(kw));
      if (matched) {
        suggestions.push({
          tag: rule.tag,
          confidence: rule.confidence,
          source: 'rule',
        });
      }
    }

    // 2. MIME-type tag
    const mimeTag = MIME_TAG_MAP[input.mimeType];
    if (mimeTag) {
      suggestions.push({ tag: mimeTag, confidence: 0.9, source: 'rule' });
    }

    // 3. File extension heuristic
    const ext = input.fileName.split('.').pop()?.toLowerCase();
    if (ext) {
      const extTag = this.extToTag(ext);
      if (extTag && !suggestions.some(s => s.tag === extTag)) {
        suggestions.push({ tag: extTag, confidence: 0.6, source: 'rule' });
      }
    }

    // 4. Placeholder: ML-based suggestions
    // In production, this would call an embedding/classification model.
    // For now we add a low-confidence generic tag if we have no suggestions.
    if (suggestions.length === 0 && textLower.length > 0) {
      suggestions.push({ tag: 'untagged-content', confidence: 0.3, source: 'keyword' });
    }

    // De-duplicate
    const unique = this.deduplicate(suggestions);

    await this.audit.append({
      actor: this.id,
      action: 'tag.suggest',
      entity: input.fileName,
      meta: { tagCount: unique.length, tags: unique.map(s => s.tag) },
    });

    return unique;
  }

  private extToTag(ext: string): string | null {
    const map: Record<string, string> = {
      pdf: 'pdf', doc: 'document', docx: 'document',
      xls: 'spreadsheet', xlsx: 'spreadsheet', csv: 'spreadsheet',
      png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', svg: 'vector',
      md: 'markdown', txt: 'text', json: 'data', xml: 'data',
      zip: 'archive', tar: 'archive', gz: 'archive',
      mp4: 'video', mp3: 'audio', wav: 'audio',
    };
    return map[ext] ?? null;
  }

  private deduplicate(suggestions: TagSuggestion[]): TagSuggestion[] {
    const seen = new Map<string, TagSuggestion>();
    for (const s of suggestions) {
      const existing = seen.get(s.tag);
      if (!existing || s.confidence > existing.confidence) {
        seen.set(s.tag, s);
      }
    }
    return Array.from(seen.values()).sort((a, b) => b.confidence - a.confidence);
  }
}
