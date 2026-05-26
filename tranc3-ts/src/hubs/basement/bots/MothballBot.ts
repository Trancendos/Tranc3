/**
 * Mothball Bot — The Basement Tier 5 Bot (NID-BASEMENT-MOTHBALL)
 *
 * Applies protective preservation metadata to restored archives:
 * sets access timestamps, marks retrieval complete, and
 * re-seals the archive if the restore is temporary.
 */

import { Bot, Logger } from '../../../core/definitions';

export interface MothballRequest {
  archiveId: string;
  coldPath: string;
}

export interface MothballResult {
  archiveId: string;
  sealed: boolean;
  restoredAt: Date;
  reSealScheduledAt: Date | null;
}

async function mothballFunc(archiveId: string, coldPath: string): Promise<MothballResult> {
  const logger = new Logger('MothballBot');

  const restoredAt = new Date();

  // For temporary restores, schedule a re-seal (move back to cold)
  // after a configurable window (e.g. 24 hours)
  const TEMPORARY_RESTORE_HOURS = 24;
  const reSealScheduledAt = new Date(restoredAt.getTime() + TEMPORARY_RESTORE_HOURS * 3600_000);

  logger.debug(`Mothball applied`, {
    archiveId,
    coldPath,
    restoredAt: restoredAt.toISOString(),
    reSealScheduledAt: reSealScheduledAt.toISOString(),
  });

  // In production: update the ArchiveEntry metadata,
  // schedule a job to re-compress and move back to cold storage.

  return {
    archiveId,
    sealed: true,
    restoredAt,
    reSealScheduledAt,
  };
}

export const MothballBot = new Bot(
  'Mothball',
  mothballFunc,
  'Applies preservation metadata to restored archives and schedules re-sealing',
);
