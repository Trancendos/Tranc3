/**
 * bullmq-queue-service — Port 8092
 * =================================
 * TypeScript job-queue service built on BullMQ, backed by the existing
 * Valkey instance (Redis-compatible, already running in the compose stack).
 *
 * Entity: The HIVE
 * Lead AI: The Queen
 */

import express, { Request, Response } from 'express';
import { Queue, Worker, JobsOptions } from 'bullmq';

const PORT = parseInt(process.env.PORT || '8092', 10);
const REDIS_HOST = process.env.VALKEY_HOST || process.env.REDIS_HOST || 'valkey';
const REDIS_PORT = parseInt(process.env.VALKEY_PORT || process.env.REDIS_PORT || '6379', 10);

const connection = { host: REDIS_HOST, port: REDIS_PORT };

// Declare which queues this service handles. Requests for unknown queues
// return 404 rather than silently enqueuing to an unprocessed queue.
const ALLOWED_QUEUES: string[] = (process.env.BULLMQ_QUEUES || 'default')
  .split(',')
  .map((q) => q.trim())
  .filter((q) => q.length > 0);

const queues = new Map<string, Queue>();

function getQueue(name: string): Queue | null {
  if (!ALLOWED_QUEUES.includes(name)) {
    return null;
  }
  if (!queues.has(name)) {
    queues.set(name, new Queue(name, { connection }));
  }
  return queues.get(name)!;
}

// Create a worker for every allowed queue so jobs are actually consumed.
ALLOWED_QUEUES.forEach((queueName) => {
  const w = new Worker(
    queueName,
    async (job) => ({ processed: true, jobId: job.id, name: job.name, queue: queueName }),
    { connection },
  );
  w.on('failed', (job, err: Error) => {
    console.error(`[${queueName}] job ${job?.id} failed:`, err?.message);
  });
  w.on('error', (err: Error) => {
    console.error(`[${queueName}] worker error:`, err?.message);
  });
});

const app = express();
app.use(express.json());

app.get('/health', async (_req: Request, res: Response) => {
  try {
    const q = getQueue('default');
    if (!q) throw new Error('"default" queue not in ALLOWED_QUEUES');
    await q.getJobCounts();
    res.json({
      status: 'ok',
      service: 'bullmq-queue-service',
      entity: 'The HIVE',
      redis: `${REDIS_HOST}:${REDIS_PORT}`,
    });
  } catch (err) {
    res.status(503).json({ status: 'error', error: (err as Error).message });
  }
});

app.get('/queues', (_req: Request, res: Response) => {
  res.json({ queues: ALLOWED_QUEUES });
});

interface EnqueueBody {
  jobName?: string;
  data?: Record<string, unknown>;
  opts?: JobsOptions;
}

app.post('/queues/:name/jobs', async (req: Request<{ name: string }, unknown, EnqueueBody>, res: Response) => {
  const queue = getQueue(req.params.name);
  if (!queue) {
    return res.status(404).json({ error: `Queue "${req.params.name}" is not handled by this service` });
  }
  try {
    const { jobName = 'job', data = {}, opts = {} } = req.body ?? {};
    const job = await queue.add(jobName, data, opts);
    res.status(201).json({ id: job.id, name: job.name, queue: req.params.name });
  } catch (err) {
    res.status(500).json({ error: (err as Error).message });
  }
});

app.get('/queues/:name/jobs/:id', async (req: Request<{ name: string; id: string }>, res: Response) => {
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
    res.status(500).json({ error: (err as Error).message });
  }
});

app.get('/queues/:name/counts', async (req: Request<{ name: string }>, res: Response) => {
  const queue = getQueue(req.params.name);
  if (!queue) {
    return res.status(404).json({ error: `Queue "${req.params.name}" is not handled by this service` });
  }
  try {
    const counts = await queue.getJobCounts();
    res.json({ queue: req.params.name, counts });
  } catch (err) {
    res.status(500).json({ error: (err as Error).message });
  }
});

app.listen(PORT, () => {
  console.log(
    `bullmq-queue-service listening on :${PORT} (redis ${REDIS_HOST}:${REDIS_PORT}, queues: ${ALLOWED_QUEUES.join(', ')})`,
  );
});
