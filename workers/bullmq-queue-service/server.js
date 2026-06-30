/**
 * bullmq-queue-service — Port 8092
 * =================================
 * Node.js job-queue scaffold built on BullMQ, backed by the existing
 * Valkey instance (Redis-compatible, already running in the compose stack).
 *
 * Entity: The HIVE
 * Lead AI: The Queen
 *
 * Complements the existing Python/SQLite queue-service (port 8027) and
 * hive-service (port 8060) with a Node.js queue option for workloads that
 * benefit from the BullMQ ecosystem (retries, rate limiting, repeatable jobs).
 */

const express = require('express');
const { Queue, Worker } = require('bullmq');

const PORT = process.env.PORT || 8092;
const REDIS_HOST = process.env.VALKEY_HOST || process.env.REDIS_HOST || 'valkey';
const REDIS_PORT = parseInt(process.env.VALKEY_PORT || process.env.REDIS_PORT || '6379', 10);

const connection = { host: REDIS_HOST, port: REDIS_PORT };

// Declare which queues this service handles. Requests for unknown queues
// return 404 rather than silently enqueuing to an unprocessed queue.
const ALLOWED_QUEUES = (process.env.BULLMQ_QUEUES || 'default')
  .split(',')
  .map((q) => q.trim())
  .filter((q) => q.length > 0);

const queues = new Map();

function getQueue(name) {
  if (!ALLOWED_QUEUES.includes(name)) {
    return null;
  }
  if (!queues.has(name)) {
    queues.set(name, new Queue(name, { connection }));
  }
  return queues.get(name);
}

// Default worker for the "default" queue.
// Add additional Workers here for each entry in ALLOWED_QUEUES as needed.
const defaultWorker = new Worker(
  'default',
  async (job) => {
    return { processed: true, jobId: job.id, name: job.name };
  },
  { connection },
);

defaultWorker.on('failed', (job, err) => {
  console.error(`Job ${job?.id} failed:`, err?.message);
});

const app = express();
app.use(express.json());

app.get('/health', async (_req, res) => {
  try {
    // Ping Valkey by attempting a queue connection check on the default queue.
    const q = getQueue('default');
    await q.getJobCounts();
    res.json({
      status: 'ok',
      service: 'bullmq-queue-service',
      entity: 'The HIVE',
      redis: `${REDIS_HOST}:${REDIS_PORT}`,
    });
  } catch (err) {
    res.status(503).json({ status: 'error', error: err.message });
  }
});

app.get('/queues', (_req, res) => {
  res.json({ queues: ALLOWED_QUEUES });
});

app.post('/queues/:name/jobs', async (req, res) => {
  const queue = getQueue(req.params.name);
  if (!queue) {
    return res.status(404).json({ error: `Queue "${req.params.name}" is not handled by this service` });
  }
  try {
    const { jobName = 'job', data = {}, opts = {} } = req.body || {};
    const job = await queue.add(jobName, data, opts);
    res.status(201).json({ id: job.id, name: job.name, queue: req.params.name });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/queues/:name/jobs/:id', async (req, res) => {
  const queue = getQueue(req.params.name);
  if (!queue) {
    return res.status(404).json({ error: `Queue "${req.params.name}" is not handled by this service` });
  }
  try {
    const job = await queue.getJob(req.params.id);
    if (!job) {
      return res.status(404).json({ error: 'job not found' });
    }
    const state = await job.getState();
    res.json({ id: job.id, name: job.name, state, returnvalue: job.returnvalue });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/queues/:name/counts', async (req, res) => {
  const queue = getQueue(req.params.name);
  if (!queue) {
    return res.status(404).json({ error: `Queue "${req.params.name}" is not handled by this service` });
  }
  try {
    const counts = await queue.getJobCounts();
    res.json({ queue: req.params.name, counts });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`bullmq-queue-service listening on :${PORT} (redis ${REDIS_HOST}:${REDIS_PORT}, queues: ${ALLOWED_QUEUES.join(', ')})`);
});
