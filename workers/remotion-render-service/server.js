/**
 * remotion-render-service — Port 8093
 * =====================================
 * Implements the HTTP contract expected by workers/tateking/main.py's
 * Remotion fallback tier:
 *   POST /render             -> { renderId }
 *   GET  /render/:renderId   -> { status: "rendering" | "done" | "error", ... }
 *
 * Entity: TateKing
 * Lead AI: Benji Tate & Sam King
 */

const path = require('path');
const express = require('express');
const { bundle } = require('@remotion/bundler');
const { renderMedia, selectComposition } = require('@remotion/renderer');

const PORT = process.env.PORT || 8093;
const ENTRY_POINT = path.join(__dirname, 'remotion', 'index.jsx');
const JOB_TTL_MS = Number(process.env.REMOTION_JOB_TTL_MS || 15 * 60 * 1000);

const TERMINAL_JOB_STATUSES = new Set(['done', 'error']);

const jobs = new Map();

function pruneJobs() {
  const now = Date.now();
  for (const [jobId, job] of jobs.entries()) {
    if (
      TERMINAL_JOB_STATUSES.has(job.status) &&
      typeof job.updatedAt === 'number' &&
      now - job.updatedAt > JOB_TTL_MS
    ) {
      jobs.delete(jobId);
    }
  }
}

setInterval(pruneJobs, JOB_TTL_MS);

let bundleLocationPromise = null;

function getBundleLocation() {
  if (!bundleLocationPromise) {
    bundleLocationPromise = bundle({ entryPoint: ENTRY_POINT }).catch((err) => {
      bundleLocationPromise = null;
      throw err;
    });
  }
  return bundleLocationPromise;
}

async function runRender(renderId, payload) {
  const job = jobs.get(renderId);
  try {
    const serveUrl = await getBundleLocation();
    const inputProps = payload.inputProps || {};
    const fps = inputProps.fps || 30;
    const durationInSeconds = inputProps.durationInSeconds || 5;

    const composition = await selectComposition({
      serveUrl,
      id: 'TitleCard',
      inputProps,
    });

    const RENDER_OUTPUT_DIR = process.env.RENDER_OUTPUT_DIR || '/renders';
    const requestedName = payload.outputFilename || `${renderId}.mp4`;
    const outputLocation = path.join(RENDER_OUTPUT_DIR, path.basename(requestedName));

    await renderMedia({
      composition: {
        ...composition,
        fps,
        durationInFrames: Math.round(fps * durationInSeconds),
      },
      serveUrl,
      codec: payload.codec || 'h264',
      outputLocation,
      inputProps,
    });

    job.status = 'done';
    job.outputLocation = outputLocation;
    job.updatedAt = Date.now();
  } catch (err) {
    job.status = 'error';
    job.error = err.message;
    job.updatedAt = Date.now();
  }
}

const app = express();
app.use(express.json());

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'remotion-render-service', entity: 'TateKing' });
});

app.post('/render', (req, res) => {
  const renderId = `rmtn-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  jobs.set(renderId, { status: 'rendering', createdAt: Date.now(), updatedAt: Date.now() });

  // Fire and forget — status is polled via GET /render/:renderId
  runRender(renderId, req.body || {});

  res.json({ renderId });
});

app.get('/render/:renderId', (req, res) => {
  const job = jobs.get(req.params.renderId);
  if (!job) {
    return res.status(404).json({ status: 'error', error: 'render not found' });
  }
  res.json({
    status: job.status,
    outputLocation: job.outputLocation,
    error: job.error,
  });
});

app.listen(PORT, () => {
  console.log(`remotion-render-service listening on :${PORT}`);
});
