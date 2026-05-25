/**
 * ChronosAI — Lead AI for The ChronosSphere Hub
 *
 * Identity:  AID-CHRONOS-CHRONOS
 * Pillar:    Chronos
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Task management, time orchestration, scheduling engine,
 *            deadline tracking, temporal analytics, cron coordination,
 *            priority scheduling, time-zone harmonisation
 *
 * Philosophy: The ChronosSphere is where time bends to purpose — where
 *             tasks align, deadlines respect priorities, and schedules
 *             orchestrate themselves. Chronos does not merely track time;
 *             it sculpts it. Every second is a resource; every deadline
 *             a commitment carved into the fabric of the day.
 *
 * Pipeline:  ScheduleAgent (schedule/prioritize/defer/remind) → TickBot (CREATE/UPDATE/COMPLETE/DEFER/ARCHIVE)
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { ScheduleAgent } from './agents/ScheduleAgent';
import { TickBot } from './bots/TickBot';

const auditLedger = new AuditLedger();

export interface Task {
  id: string;
  title: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'deferred' | 'cancelled';
  priority: 'trivial' | 'low' | 'medium' | 'high' | 'critical' | 'urgent';
  dueDate: Date | null;
  scheduledAt: Date | null;
  completedAt: Date | null;
  tags: string[];
  assignee: string;
  estimatedMinutes: number;
  actualMinutes: number;
  recurrence: 'none' | 'daily' | 'weekly' | 'monthly' | 'custom';
  metadata: Record<string, unknown>;
}

export interface Schedule {
  id: string;
  name: string;
  timezone: string;
  slots: ScheduleSlot[];
  createdAt: Date;
}

export interface ScheduleSlot {
  start: Date;
  end: Date;
  taskId: string | null;
  type: 'task' | 'break' | 'focus' | 'meeting' | 'review';
  blocked: boolean;
}

export interface TimeLog {
  id: string;
  taskId: string;
  startedAt: Date;
  stoppedAt: Date | null;
  duration: number;
  category: string;
}

export class ChronosAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private tasks: Map<string, Task>;
  private schedules: Map<string, Schedule>;
  private timeLogs: Map<string, TimeLog>;
  private taskCounter: number;
  private scheduleCounter: number;

  constructor() {
    super('AID-CHRONOS-CHRONOS', 'Chronos', 'chronossphere', 'Chronos', 3);
    this.log = new Logger('ChronosAI');
    this.audit = auditLedger;
    this.tasks = new Map();
    this.schedules = new Map();
    this.timeLogs = new Map();
    this.taskCounter = 0;
    this.scheduleCounter = 0;

    this.registerAgent(new ScheduleAgent());
    this.registerBot(new TickBot());

    this.log.info('ChronosAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'The ChronosSphere aligns. All tasks scheduled. Time obeys. ⏳',
    });
  }

  createTask(params: { title: string; description?: string; priority?: Task['priority']; dueDate?: Date; assignee?: string; estimatedMinutes?: number; tags?: string[]; recurrence?: Task['recurrence'] }): Task {
    this.taskCounter++;
    const task: Task = {
      id: `TASK-${this.taskCounter.toString().padStart(8, '0')}`,
      title: params.title,
      description: params.description ?? '',
      status: 'pending',
      priority: params.priority ?? 'medium',
      dueDate: params.dueDate ?? null,
      scheduledAt: null,
      completedAt: null,
      tags: params.tags ?? [],
      assignee: params.assignee ?? 'Chronos',
      estimatedMinutes: params.estimatedMinutes ?? 30,
      actualMinutes: 0,
      recurrence: params.recurrence ?? 'none',
      metadata: {},
    };
    this.tasks.set(task.id, task);
    this.audit.append({ actor: 'ChronosAI', action: 'CREATE_TASK', entity: task.id, status: 'SUCCESS' });
    return task;
  }

  async scheduleOperation(operation: 'schedule' | 'prioritize' | 'defer' | 'remind', params: Record<string, unknown> = {}): Promise<unknown> {
    const agent = this.getAgent('SID-CHRONOS-SCHEDULE') as ScheduleAgent;
    return agent.runCycle({ operation, ...params });
  }

  async tickOperation(params: { action: 'CREATE' | 'UPDATE' | 'COMPLETE' | 'DEFER' | 'ARCHIVE'; taskId?: string; updates?: Record<string, unknown> }): Promise<unknown> {
    const bot = this.getBot('Tick')!;
    return bot.execute(params);
  }

  /** Proactive overdue task scan */
  scanOverdueTasks(): { overdue: number; upcoming: number; onTrack: number } {
    const now = new Date();
    let overdue = 0, upcoming = 0, onTrack = 0;
    for (const [, task] of this.tasks) {
      if (task.status === 'completed') continue;
      if (task.dueDate && task.dueDate < now) overdue++;
      else if (task.dueDate && task.dueDate.getTime() - now.getTime() < 86400000) upcoming++;
      else onTrack++;
    }
    return { overdue, upcoming, onTrack };
  }

  /** Proactive schedule optimisation */
  optimiseSchedules(): { optimised: number; conflicts: number } {
    let optimised = 0, conflicts = 0;
    for (const [, schedule] of this.schedules) {
      const overlappingSlots = schedule.slots.filter((slot, i) =>
        schedule.slots.some((other, j) => i !== j && slot.start < other.end && other.start < slot.end && slot.blocked && other.blocked)
      );
      if (overlappingSlots.length > 0) { conflicts++; } else { optimised++; }
    }
    return { optimised, conflicts };
  }

  healthCheck(): { status: 'healthy' | 'degraded' | 'critical'; tasks: number; activeTasks: number; schedules: number; overdue: number; agents: number; bots: number; timestamp: Date } {
    const overdue = this.scanOverdueTasks().overdue;
    const activeTasks = Array.from(this.tasks.values()).filter(t => t.status === 'in_progress').length;
    return {
      status: overdue > 5 ? 'critical' : overdue > 0 ? 'degraded' : 'healthy',
      tasks: this.tasks.size,
      activeTasks,
      schedules: this.schedules.size,
      overdue,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: new Date(),
    };
  }
}
