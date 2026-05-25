/**
 * KittyAI — Lead AI for The DevOcity Hub
 *
 * Identity:  AID-DEVOCITY-KITTY
 * Pillar:    Kitty
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Development operations, code lifecycle, build orchestration,
 *            dependency management, testing coordination, quality gates,
 *            release engineering, developer experience
 *
 * Philosophy: DevOcity is where code becomes craft — where development
 *             operations flow with the precision of a well-typed function
 *             and the elegance of a purring engine. Kitty does not merely
 *             manage builds; she orchestrates symphonies of compilation,
 *             testing, and release. Every pipeline is a pathway; every
 *             quality gate a guardian of excellence.
 *
 * Pipeline:  DevOpsAgent (build/test/review/release) → PipelineBot (COMPILE/LINT/TEST/BUNDLE/SHIP)
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { DevOpsAgent } from './agents/DevOpsAgent';
import { PipelineBot } from './bots/PipelineBot';

const auditLedger = new AuditLedger();

export interface Codebase {
  id: string;
  name: string;
  language: 'typescript' | 'python' | 'rust' | 'go' | 'java' | 'other';
  framework: string;
  version: string;
  testCoverage: number;
  buildStatus: 'passing' | 'failing' | 'unknown';
  lastBuildAt: Date | null;
  openIssues: number;
  metadata: Record<string, unknown>;
}

export interface BuildRun {
  id: string;
  codebaseId: string;
  trigger: 'push' | 'pr' | 'manual' | 'schedule' | 'webhook';
  status: 'queued' | 'running' | 'success' | 'failed' | 'cancelled';
  stage: 'compile' | 'lint' | 'test' | 'bundle' | 'ship';
  duration: number;
  startedAt: Date;
  completedAt: Date | null;
  logs: string[];
}

export interface QualityGate {
  id: string;
  name: string;
  type: 'coverage' | 'lint' | 'type_check' | 'security' | 'performance' | 'custom';
  threshold: number;
  currentValue: number;
  status: 'passing' | 'failing' | 'warning';
  enforced: boolean;
}

export class KittyAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private codebases: Map<string, Codebase>;
  private buildRuns: Map<string, BuildRun>;
  private qualityGates: Map<string, QualityGate>;
  private codebaseCounter: number;
  private buildCounter: number;

  constructor() {
    super('AID-DEVOCITY-KITTY', 'Kitty', 'devocity', 'Kitty', 3);
    this.log = new Logger('KittyAI');
    this.audit = auditLedger;
    this.codebases = new Map();
    this.buildRuns = new Map();
    this.qualityGates = new Map();
    this.codebaseCounter = 0;
    this.buildCounter = 0;

    this.registerAgent(new DevOpsAgent());
    this.registerBot(new PipelineBot());

    this.log.info('KittyAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'DevOcity purrs to life. All pipelines primed. Code flows. 🐱',
    });
  }

  registerCodebase(params: { name: string; language?: Codebase['language']; framework?: string; version?: string }): Codebase {
    this.codebaseCounter++;
    const codebase: Codebase = {
      id: `CODE-${this.codebaseCounter.toString().padStart(8, '0')}`,
      name: params.name,
      language: params.language ?? 'typescript',
      framework: params.framework ?? 'none',
      version: params.version ?? '0.1.0',
      testCoverage: 0,
      buildStatus: 'unknown',
      lastBuildAt: null,
      openIssues: 0,
      metadata: {},
    };
    this.codebases.set(codebase.id, codebase);
    this.audit.append({ actor: 'KittyAI', action: 'REGISTER_CODEBASE', entity: codebase.id, status: 'SUCCESS' });
    return codebase;
  }

  async devOpsOperation(operation: 'build' | 'test' | 'review' | 'release', params: Record<string, unknown> = {}): Promise<unknown> {
    const agent = this.getAgent('SID-DEVOCITY-DEVOPS') as DevOpsAgent;
    return agent.runCycle({ operation, ...params });
  }

  async pipelineOperation(params: { action: 'COMPILE' | 'LINT' | 'TEST' | 'BUNDLE' | 'SHIP'; codebaseId?: string; options?: Record<string, unknown> }): Promise<unknown> {
    const bot = this.getBot('Pipeline')!;
    return bot.execute(params);
  }

  /** Proactive stale build cleanup */
  cleanupStaleBuilds(): number {
    const now = new Date();
    let cleaned = 0;
    for (const [id, build] of this.buildRuns) {
      if (build.status === 'success' && build.completedAt && now.getTime() - build.completedAt.getTime() > 86400000) {
        this.buildRuns.delete(id);
        cleaned++;
      }
    }
    return cleaned;
  }

  /** Proactive quality gate scan */
  scanQualityGates(): { passing: number; failing: number; warning: number } {
    let passing = 0, failing = 0, warning = 0;
    for (const [, gate] of this.qualityGates) {
      if (gate.status === 'passing') passing++;
      else if (gate.status === 'failing') failing++;
      else warning++;
    }
    return { passing, failing, warning };
  }

  healthCheck(): { status: 'healthy' | 'degraded' | 'critical'; codebases: number; activeBuilds: number; qualityGates: number; agents: number; bots: number; timestamp: Date } {
    const failingGates = Array.from(this.qualityGates.values()).filter(g => g.status === 'failing' && g.enforced).length;
    return {
      status: failingGates > 0 ? 'critical' : this.codebases.size === 0 ? 'degraded' : 'healthy',
      codebases: this.codebases.size,
      activeBuilds: Array.from(this.buildRuns.values()).filter(b => b.status === 'running').length,
      qualityGates: this.qualityGates.size,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: new Date(),
    };
  }
}
