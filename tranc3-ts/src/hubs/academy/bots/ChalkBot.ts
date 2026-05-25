/**
 * ChalkBot — Content Scribing Bot for The Academy
 *
 * Identity:  NID-ACADEMY-CHALK
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheAcademyAI (AID-ACADEMY)
 *
 * Responsibilities:
 *   - SCRIBE: Record, format, and manage academic content
 *   - Support lecture, exam, notes, feedback, and syllabus content types
 *   - Track scribed content with versioning and revision history
 *   - Format content according to Academy standards and templates
 *   - Manage chalk board state: draft → reviewed → published → archived
 *
 * "The chalk dust settles into permanence. What is spoken fades;
 *  what is scribed endures. ChalkBot is the memory of the lecture hall."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ────────────────────────────────────────────────────────────────────────────
// Input / Output Types
// ────────────────────────────────────────────────────────────────────────────

export interface ChalkInput {
  operation: 'SCRIBE';
  contentType: 'lecture' | 'exam' | 'notes' | 'feedback' | 'syllabus';
  content: string;
  metadata?: Record<string, unknown>;
  courseId?: string;
  instructorId?: string;
  targetAudience?: string;
  format?: 'plain' | 'markdown' | 'html' | 'latex';
  version?: number;
  previousVersionId?: string;
}

export interface ChalkDocument {
  id: string;
  contentType: ChalkInput['contentType'];
  content: string;
  formattedContent: string;
  format: ChalkInput['format'];
  courseId: string;
  instructorId: string;
  targetAudience: string;
  status: 'draft' | 'reviewed' | 'published' | 'archived' | 'retracted';
  version: number;
  previousVersionId: string;
  wordCount: number;
  characterCount: number;
  readingTimeMinutes: number;
  metadata: Record<string, unknown>;
  createdAt: number;
  updatedAt: number;
  revisedBy: string;
}

export interface ChalkRevision {
  documentId: string;
  fromVersion: number;
  toVersion: number;
  changeType: 'created' | 'edited' | 'formatted' | 'corrected' | 'augmented' | 'retracted';
  changeSummary: string;
  timestamp: number;
  revisedBy: string;
}

export interface ChalkStats {
  totalDocuments: number;
  byContentType: Record<NonNullable<ChalkInput['contentType']>, number>;
  byStatus: Record<NonNullable<ChalkDocument['status']>, number>;
  byFormat: Record<NonNullable<ChalkInput['format']>, number>;
  totalRevisions: number;
  averageWordCount: number;
  averageReadingTime: number;
  recentlyPublished: number;
  timestamp: number;
}

export interface ScribeResult {
  success: boolean;
  document: ChalkDocument;
  revision: ChalkRevision;
  stats: ChalkStats;
  message: string;
  timestamp: number;
}

// ────────────────────────────────────────────────────────────────────────────
// Content Templates
// ────────────────────────────────────────────────────────────────────────────

const CONTENT_TEMPLATES: Record<ChalkInput['contentType'], {
  header: string;
  sections: string[];
  footer: string;
  defaultFormat: ChalkInput['format'];
}> = {
  lecture: {
    header: '# LECTURE NOTES',
    sections: ['Objectives', 'Key Concepts', 'Detailed Content', 'Examples', 'Summary', 'Further Reading'],
    footer: '— End of Lecture —',
    defaultFormat: 'markdown',
  },
  exam: {
    header: '# EXAMINATION PAPER',
    sections: ['Instructions', 'Section A: Multiple Choice', 'Section B: Short Answer', 'Section C: Essay', 'Marking Scheme'],
    footer: '— End of Examination —',
    defaultFormat: 'markdown',
  },
  notes: {
    header: '# STUDY NOTES',
    sections: ['Topic Overview', 'Key Points', 'Definitions', 'Diagrams', 'Review Questions'],
    footer: '— End of Notes —',
    defaultFormat: 'markdown',
  },
  feedback: {
    header: '# ACADEMIC FEEDBACK',
    sections: ['Overall Assessment', 'Strengths', 'Areas for Improvement', 'Recommendations', 'Action Items'],
    footer: '— End of Feedback —',
    defaultFormat: 'markdown',
  },
  syllabus: {
    header: '# COURSE SYLLABUS',
    sections: ['Course Description', 'Learning Outcomes', 'Required Materials', 'Schedule', 'Grading Policy', 'Policies'],
    footer: '— End of Syllabus —',
    defaultFormat: 'markdown',
  },
};

const FORMAT_WRAPPERS: Record<NonNullable<ChalkInput['format']>, {
  bold: (t: string) => string;
  italic: (t: string) => string;
  heading: (t: string, level: number) => string;
  list: (items: string[]) => string;
}> = {
  plain: {
    bold: (t) => t.toUpperCase(),
    italic: (t) => `_${t}_`,
    heading: (t, level) => `${'='.repeat(level)} ${t} ${'='.repeat(level)}`,
    list: (items) => items.map((item, i) => `  ${i + 1}. ${item}`).join('\n'),
  },
  markdown: {
    bold: (t) => `**${t}**`,
    italic: (t) => `*${t}*`,
    heading: (t, level) => `${'#'.repeat(level)} ${t}`,
    list: (items) => items.map((item) => `- ${item}`).join('\n'),
  },
  html: {
    bold: (t) => `<strong>${t}</strong>`,
    italic: (t) => `<em>${t}</em>`,
    heading: (t, level) => `<h${level}>${t}</h${level}>`,
    list: (items) => `<ul>\n${items.map((item) => `  <li>${item}</li>`).join('\n')}\n</ul>`,
  },
  latex: {
    bold: (t) => `\\textbf{${t}}`,
    italic: (t) => `\\textit{${t}}`,
    heading: (t, level) => `\\${'sub'.repeat(Math.max(0, level - 1))}section{${t}}`,
    list: (items) => `\\begin{itemize}\n${items.map((item) => `  \\item ${item}`).join('\n')}\n\\end{itemize}`,
  },
};

// ────────────────────────────────────────────────────────────────────────────
// Document Storage
// ────────────────────────────────────────────────────────────────────────────

let documentCounter = 0;
const documentStore: Map<string, ChalkDocument> = new Map();
const revisionLog: ChalkRevision[] = [];

// ────────────────────────────────────────────────────────────────────────────
// ChalkBot Implementation
// ────────────────────────────────────────────────────────────────────────────

export class ChalkBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-ACADEMY-CHALK',
      'Chalk',
      async (input: ChalkInput) => this.handleScribe(input),
      'Records, formats, and manages academic content including lectures, exams, notes, feedback, and syllabi'
    );

    this.log = new Logger('ChalkBot');
    this.audit = auditLedger;
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Main Handler
  // ──────────────────────────────────────────────────────────────────────────

  private async handleScribe(input: ChalkInput): Promise<ScribeResult> {
    if (input.operation !== 'SCRIBE') {
      return this.fail(input, `Invalid operation: ${input.operation}. ChalkBot only accepts SCRIBE.`);
    }

    if (!input.content || input.content.trim().length === 0) {
      return this.fail(input, 'Content cannot be empty');
    }

    return this.scribe(input);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // SCRIBE — Create or update a chalk document
  // ──────────────────────────────────────────────────────────────────────────

  private scribe(input: ChalkInput): ScribeResult {
    const {
      contentType,
      content,
      metadata,
      courseId,
      instructorId,
      targetAudience,
      format,
      version,
      previousVersionId,
    } = input;

    const template = CONTENT_TEMPLATES[contentType];
    const resolvedFormat = format ?? template.defaultFormat;
    const resolvedCourseId = courseId ?? 'CRS-000000';
    const resolvedInstructorId = instructorId ?? 'INST-000000';
    const resolvedTargetAudience = targetAudience ?? 'general';

    // Check if updating an existing document
    let existingDoc: ChalkDocument | undefined;
    if (previousVersionId) {
      existingDoc = documentStore.get(previousVersionId);
    }

    const newVersion = existingDoc ? (version ?? existingDoc.version + 1) : 1;
    const changeType: ChalkRevision['changeType'] = existingDoc ? 'edited' : 'created';

    // Format the content according to the template and format
    const formattedContent = this.formatContent(content, contentType, resolvedFormat, template);

    // Calculate metrics
    const wordCount = content.split(/\s+/).filter(w => w.length > 0).length;
    const characterCount = content.length;
    const readingTimeMinutes = Math.max(1, Math.ceil(wordCount / 250)); // ~250 WPM average

    // Create the document
    documentCounter++;
    const document: ChalkDocument = {
      id: `CHALK-${documentCounter.toString().padStart(6, '0')}`,
      contentType,
      content,
      formattedContent,
      format: resolvedFormat,
      courseId: resolvedCourseId,
      instructorId: resolvedInstructorId,
      targetAudience: resolvedTargetAudience,
      status: 'draft',
      version: newVersion,
      previousVersionId: previousVersionId ?? '',
      wordCount,
      characterCount,
      readingTimeMinutes,
      metadata: metadata ?? {},
      createdAt: Date.now(),
      updatedAt: Date.now(),
      revisedBy: 'ChalkBot',
    };

    // Auto-advance status: version 1 = draft, version 2+ inherits parent status or advances
    if (existingDoc) {
      if (existingDoc.status === 'published') {
        document.status = 'reviewed';
      } else if (existingDoc.status === 'reviewed') {
        document.status = 'published';
      }
    }

    documentStore.set(document.id, document);

    // Create revision record
    const revision: ChalkRevision = {
      documentId: document.id,
      fromVersion: existingDoc ? existingDoc.version : 0,
      toVersion: newVersion,
      changeType,
      changeSummary: existingDoc
        ? `Updated ${contentType} from v${existingDoc.version} to v${newVersion}`
        : `Created new ${contentType} document`,
      timestamp: Date.now(),
      revisedBy: 'ChalkBot',
    };
    revisionLog.push(revision);

    const stats = this.buildStats();

    this.audit.append({
      actor: 'NID-ACADEMY-CHALK',
      action: 'SCRIBE',
      entity: document.id,
      status: 'SUCCESS',
      meta: {
        contentType,
        format: resolvedFormat,
        version: newVersion,
        wordCount,
        courseId: resolvedCourseId,
      },
    });

    this.log.info('Content scribed', {
      documentId: document.id,
      contentType,
      version: newVersion,
      wordCount,
      format: resolvedFormat,
    });

    return {
      success: true,
      document,
      revision,
      stats,
      message: `${contentType.charAt(0).toUpperCase() + contentType.slice(1)} scribed as ${document.id} (v${newVersion}, ${resolvedFormat}) — ${wordCount} words, ~${readingTimeMinutes}min read | Status: ${document.status}`,
      timestamp: Date.now(),
    };
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Content Formatting
  // ──────────────────────────────────────────────────────────────────────────

  private formatContent(
    rawContent: string,
    contentType: ChalkInput['contentType'],
    format: ChalkInput['format'],
    template: typeof CONTENT_TEMPLATES['lecture']
  ): string {
    const wrappers = FORMAT_WRAPPERS[format!];
    const lines: string[] = [];

    // Header
    lines.push(wrappers.heading(template.header.replace('# ', ''), 1));
    lines.push('');

    // Metadata line
    const now = new Date().toISOString();
    lines.push(wrappers.italic(`Scribed: ${now} | Type: ${contentType.toUpperCase()} | Format: ${format}`));
    lines.push('');

    // Sections — distribute content across template sections
    const contentParagraphs = rawContent.split(/\n\n+/).filter(p => p.trim().length > 0);
    const sectionDistribution = this.distributeContent(contentParagraphs, template.sections);

    for (const section of template.sections) {
      lines.push(wrappers.heading(section, 2));
      lines.push('');

      const sectionContent = sectionDistribution.get(section);
      if (sectionContent && sectionContent.length > 0) {
        for (const paragraph of sectionContent) {
          lines.push(paragraph);
          lines.push('');
        }
      } else {
        lines.push(wrappers.italic(`[${section} content pending]`));
        lines.push('');
      }
    }

    // Footer
    lines.push('---');
    lines.push(wrappers.italic(template.footer));

    return lines.join('\n');
  }

  private distributeContent(
    paragraphs: string[],
    sections: string[]
  ): Map<string, string[]> {
    const distribution = new Map<string, string[]>();

    if (paragraphs.length === 0 || sections.length === 0) return distribution;

    // Initialize all sections
    for (const section of sections) {
      distribution.set(section, []);
    }

    // Distribute paragraphs across sections
    // First paragraph goes to first section, last to last, rest spread evenly
    if (paragraphs.length === 1) {
      distribution.set(sections[0], [paragraphs[0]]);
    } else if (paragraphs.length <= sections.length) {
      // One paragraph per section, fill from the start
      for (let i = 0; i < paragraphs.length; i++) {
        const sectionIdx = Math.min(i, sections.length - 1);
        const current = distribution.get(sections[sectionIdx]) ?? [];
        current.push(paragraphs[i]);
        distribution.set(sections[sectionIdx], current);
      }
    } else {
      // More paragraphs than sections — distribute evenly
      const perSection = Math.floor(paragraphs.length / sections.length);
      let paragraphIdx = 0;

      for (let s = 0; s < sections.length; s++) {
        const count = s === sections.length - 1
          ? paragraphs.length - paragraphIdx  // Last section gets remainder
          : perSection;
        const sectionParagraphs: string[] = [];
        for (let p = 0; p < count && paragraphIdx < paragraphs.length; p++) {
          sectionParagraphs.push(paragraphs[paragraphIdx]);
          paragraphIdx++;
        }
        distribution.set(sections[s], sectionParagraphs);
      }
    }

    return distribution;
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Statistics
  // ──────────────────────────────────────────────────────────────────────────

  private buildStats(): ChalkStats {
    const all = Array.from(documentStore.values());

    const byContentType: Record<NonNullable<ChalkInput['contentType']>, number> = {
      lecture: 0, exam: 0, notes: 0, feedback: 0, syllabus: 0,
    };
    const byStatus: Record<NonNullable<ChalkDocument['status']>, number> = {
      draft: 0, reviewed: 0, published: 0, archived: 0, retracted: 0,
    };
    const byFormat: Record<NonNullable<ChalkInput['format']>, number> = {
      plain: 0, markdown: 0, html: 0, latex: 0,
    };

    for (const doc of all) {
      byContentType[doc.contentType]++;
      byStatus[doc.status!]++;
      byFormat[doc.format!]++;
    }

    const totalWords = all.reduce((sum, doc) => sum + doc.wordCount, 0);
    const totalReadingTime = all.reduce((sum, doc) => sum + doc.readingTimeMinutes, 0);
    const oneDayAgo = Date.now() - 86400000;
    const recentlyPublished = all.filter(
      d => d.status === 'published' && d.updatedAt >= oneDayAgo
    ).length;

    return {
      totalDocuments: all.length,
      byContentType,
      byStatus,
      byFormat,
      totalRevisions: revisionLog.length,
      averageWordCount: all.length > 0 ? Math.round(totalWords / all.length) : 0,
      averageReadingTime: all.length > 0 ? Math.round(totalReadingTime / all.length) : 0,
      recentlyPublished,
      timestamp: Date.now(),
    };
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Failure Helper
  // ──────────────────────────────────────────────────────────────────────────

  private fail(input: ChalkInput, message: string): ScribeResult {
    this.log.error('Scribe failed', { message, contentType: input.contentType });

    const emptyDoc: ChalkDocument = {
      id: '',
      contentType: input.contentType ?? 'notes',
      content: '',
      formattedContent: '',
      format: 'plain',
      courseId: '',
      instructorId: '',
      targetAudience: '',
      status: 'draft',
      version: 0,
      previousVersionId: '',
      wordCount: 0,
      characterCount: 0,
      readingTimeMinutes: 0,
      metadata: {},
      createdAt: 0,
      updatedAt: 0,
      revisedBy: 'ChalkBot',
    };

    const emptyRevision: ChalkRevision = {
      documentId: '',
      fromVersion: 0,
      toVersion: 0,
      changeType: 'created',
      changeSummary: '',
      timestamp: Date.now(),
      revisedBy: 'ChalkBot',
    };

    return {
      success: false,
      document: emptyDoc,
      revision: emptyRevision,
      stats: this.buildStats(),
      message,
      timestamp: Date.now(),
    };
  }
}
