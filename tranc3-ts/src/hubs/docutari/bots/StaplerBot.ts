/**
 * Stapler Bot — DocUtari Tier 5 Bot (NID-DOCUTARI-STAPLER)
 *
 * Generates a unique document ID and "staples" metadata
 * together as the canonical record reference.
 */

import { Bot, Logger } from '../../../core/definitions';

export interface StapleRequest {
  title: string;
  tags: string[];
  folderPath: string;
}

async function staplerFunc(req: StapleRequest): Promise<string> {
  const logger = new Logger('StaplerBot');

  // Generate a short, collision-resistant doc ID
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 8);
  const docId = `DOC-${timestamp}-${random}`;

  logger.debug(`Stapled document`, { docId, title: req.title, tags: req.tags.length, folder: req.folderPath });

  return docId;
}

export const StaplerBot = new Bot(
  'Stapler',
  staplerFunc,
  'Generates unique document IDs and staples metadata as canonical record reference',
);
