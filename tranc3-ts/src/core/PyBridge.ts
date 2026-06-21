/**
 * PyBridge — HTTP bridge from tranc3-ts TypeScript hubs to Python backend.
 *
 * Usage:
 *   const bridge = PyBridge.getInstance();
 *   const result = await bridge.infer({ id: 'req-1', prompt: 'Hello', type: 'CHAT', priority: 'NORMAL' });
 *
 * The bridge targets TRANC3_BACKEND_URL (default http://localhost:8000).
 * All inference is routed through the Python AI Gateway zero-cost rotation chain.
 */

export interface PyInferenceRequest {
  id: string;
  type: 'CHAT' | 'COMPLETION' | 'EMBEDDING' | 'CLASSIFICATION' | 'SUMMARIZATION';
  model?: string;
  prompt: string;
  parameters?: Record<string, unknown>;
  priority: 'LOW' | 'NORMAL' | 'HIGH';
  hub_id?: string;
  entity_id?: string;
}

export interface PyInferenceResponse {
  request_id: string;
  result: unknown;
  model: string;
  latency_ms: number;
  tokens_used: number;
  status: 'SUCCESS' | 'FAILURE' | 'TIMEOUT';
  tier: number;
}

export interface PyHealthSignal {
  entity_id: string;
  hub_id?: string;
  latency_ms?: number;
  error_rate?: number;
  request_rate?: number;
}

export class PyBridge {
  private static _instance: PyBridge | null = null;
  private readonly _baseUrl: string;
  private _healthy: boolean = true;

  private constructor(baseUrl?: string) {
    this._baseUrl = (baseUrl ?? process.env['TRANC3_BACKEND_URL'] ?? 'http://localhost:8000').replace(/\/$/, '');
  }

  static getInstance(baseUrl?: string): PyBridge {
    if (!PyBridge._instance) {
      PyBridge._instance = new PyBridge(baseUrl);
    }
    return PyBridge._instance;
  }

  /** Route an inference request through the Python AI Gateway. */
  async infer(req: PyInferenceRequest): Promise<PyInferenceResponse> {
    const t0 = Date.now();
    try {
      const res = await fetch(`${this._baseUrl}/tranc3ts/infer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }
      this._healthy = true;
      return (await res.json()) as PyInferenceResponse;
    } catch (err) {
      this._healthy = false;
      // Return stub on failure so TS hubs degrade gracefully
      return {
        request_id: req.id,
        result: { error: String(err) },
        model: 'stub',
        latency_ms: Date.now() - t0,
        tokens_used: 0,
        status: 'FAILURE',
        tier: 3,
      };
    }
  }

  /** Report hub health to t2ance Prime Intelligence layer. */
  async reportHealth(signal: PyHealthSignal): Promise<void> {
    try {
      await fetch(`${this._baseUrl}/tranc3ts/health/signal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(signal),
      });
    } catch {
      // non-critical — don't throw
    }
  }

  /** Check bridge availability. */
  async ping(): Promise<boolean> {
    try {
      const res = await fetch(`${this._baseUrl}/tranc3ts/status`);
      this._healthy = res.ok;
      return res.ok;
    } catch {
      this._healthy = false;
      return false;
    }
  }

  get isHealthy(): boolean {
    return this._healthy;
  }

  get baseUrl(): string {
    return this._baseUrl;
  }
}
