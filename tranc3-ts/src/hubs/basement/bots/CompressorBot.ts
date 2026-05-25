/**
 * Compressor Bot — The Basement Tier 5 Bot (NID-BASEMENT-COMPRESSOR)
 *
 * Compresses document content for cold storage.
 * Uses zlib/deflate in production; stub returns simulated result.
 */

import { Bot, Logger } from '../../../core/definitions';
import { deflateSync } from 'zlib';

export interface CompressResult {
  dataBase64: string;
  compressedSizeBytes: number;
  archiveChecksum: string;
}

async function compressorFunc(contentBase64: string, mimeType: string): Promise<CompressResult> {
  const logger = new Logger('CompressorBot');
  const rawBuffer = Buffer.from(contentBase64, 'base64');

  // Attempt real compression
  let compressedBuffer: Buffer;
  try {
    compressedBuffer = deflateSync(rawBuffer);
  } catch {
    // Fallback: store uncompressed
    compressedBuffer = rawBuffer;
    logger.warn(`Compression failed for mime ${mimeType}, storing uncompressed`);
  }

  const dataBase64 = compressedBuffer.toString('base64');
  const compressedSizeBytes = compressedBuffer.byteLength;

  // Checksum of compressed payload
  // Production: crypto.createHash('sha256').update(compressedBuffer).digest('hex')
  const archiveChecksum = `sha256-arch-${compressedSizeBytes}-${Date.now()}`;

  const ratio = ((1 - compressedSizeBytes / rawBuffer.byteLength) * 100).toFixed(1);
  logger.debug(`Compressed document`, {
    mimeType,
    originalBytes: rawBuffer.byteLength,
    compressedBytes: compressedSizeBytes,
    savingPct: `${ratio}%`,
  });

  return { dataBase64, compressedSizeBytes, archiveChecksum };
}

export const CompressorBot = new Bot(
  'Compressor',
  compressorFunc,
  'Compresses document content for cold storage using deflate/gzip',
);
