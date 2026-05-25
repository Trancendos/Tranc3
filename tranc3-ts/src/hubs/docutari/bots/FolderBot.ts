/**
 * Folder Bot — DocUtari Tier 5 Bot (NID-DOCUTARI-FOLDER)
 *
 * Moves / links a document into its assigned folder path
 * within the storage provider.
 */

import { Bot, Logger } from '../../../core/definitions';
import type { DocumentMeta } from '../DocUtariAI';

async function folderFunc(doc: DocumentMeta): Promise<{ storedPath: string }> {
  const logger = new Logger('FolderBot');

  // In production, this calls the IStorageProvider to write/link the file
  // at the correct folder path. For now we log the intended path.
  const storedPath = `${doc.folderPath}/${doc.docId}--${doc.title}`;

  logger.debug(`Filed document`, {
    docId: doc.docId,
    folderPath: doc.folderPath,
    storedPath,
  });

  return { storedPath };
}

export const FolderBot = new Bot(
  'Folder',
  folderFunc,
  'Moves or links a document into its assigned storage folder path',
);
