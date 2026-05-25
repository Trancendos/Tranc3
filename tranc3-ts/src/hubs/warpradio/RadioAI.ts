/**
 * RadioAI — Lead AI for Warp Radio Hub
 *
 * Identity:  AID-WARPRADIO-RICKI
 * Pillar:    Rocking Ricki
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Music & audio streaming, broadcast scheduling, playlist curation,
 *            frequency management, audio processing, live stream coordination
 *
 * Philosophy: Warp Radio is where sound becomes signal — every frequency a
 *             channel of expression, every playlist a journey, every broadcast
 *             a pulse of the ecosystem's heartbeat. Ricki doesn't just play
 *             music; it orchestrates the soundtrack of the Trancendos.
 *
 * Pipeline:  BroadcastAgent (schedule/cue/mix/stream) → StreamBot (PLAY/PAUSE/SKIP/RECORD/ENCODE)
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { BroadcastAgent } from './agents/BroadcastAgent';
import { StreamBot } from './bots/StreamBot';

const auditLedger = new AuditLedger();

export interface RadioStation {
  id: string;
  name: string;
  frequency: number;
  genre: string[];
  status: 'offline' | 'booting' | 'live' | 'paused' | 'error';
  listeners: number;
  peakListeners: number;
  currentTrack: string | null;
  createdAt: Date;
  metadata: Record<string, unknown>;
}

export interface Playlist {
  id: string;
  name: string;
  stationId: string;
  tracks: PlaylistTrack[];
  shuffle: boolean;
  repeat: boolean;
  totalDuration: number;
  createdAt: Date;
}

export interface PlaylistTrack {
  id: string;
  title: string;
  artist: string;
  duration: number;
  genre: string;
  bpm: number;
  key: string;
}

export interface BroadcastSchedule {
  id: string;
  stationId: string;
  type: 'live' | 'automated' | 'mixed' | 'special';
  startsAt: Date;
  endsAt: Date;
  host: string | null;
  metadata: Record<string, unknown>;
}

export class RadioAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private stations: Map<string, RadioStation>;
  private playlists: Map<string, Playlist>;
  private schedules: Map<string, BroadcastSchedule>;
  private stationCounter: number;

  constructor() {
    super('AID-WARPRADIO-RICKI', 'Radio', 'warpradio', 'Rocking Ricki', 3);
    this.log = new Logger('RadioAI');
    this.audit = auditLedger;
    this.stations = new Map();
    this.playlists = new Map();
    this.schedules = new Map();
    this.stationCounter = 0;

    this.registerAgent(new BroadcastAgent());
    this.registerBot(new StreamBot());

    this.log.info('RadioAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'Warp Radio online. Tune in. Turn up. Rock out. 🎵',
    });
  }

  createStation(params: { name: string; frequency?: number; genre?: string[] }): RadioStation {
    this.stationCounter++;
    const station: RadioStation = {
      id: `STA-${this.stationCounter.toString().padStart(8, '0')}`,
      name: params.name,
      frequency: params.frequency ?? 88.0 + this.stationCounter * 0.2,
      genre: params.genre ?? ['electronic'],
      status: 'live',
      listeners: 0,
      peakListeners: 0,
      currentTrack: null,
      createdAt: new Date(),
      metadata: {},
    };
    this.stations.set(station.id, station);
    this.audit.append({ actor: 'RadioAI', action: 'CREATE_STATION', entity: station.id, status: 'SUCCESS' });
    return station;
  }

  getStation(stationId: string): RadioStation | undefined {
    return this.stations.get(stationId);
  }

  async broadcastOperation(operation: 'schedule' | 'cue' | 'mix' | 'stream', params: Record<string, unknown> = {}): Promise<unknown> {
    const agent = this.getAgent('SID-WARPRADIO-BROADCAST') as BroadcastAgent;
    return agent.runCycle({ operation, ...params });
  }

  async streamOperation(params: { action: 'PLAY' | 'PAUSE' | 'SKIP' | 'RECORD' | 'ENCODE'; stationId?: string; trackId?: string }): Promise<unknown> {
    const bot = this.getBot('Stream')!;
    return bot.execute(params);
  }

  /** Proactive idle station detection */
  scanIdleStations(): RadioStation[] {
    return Array.from(this.stations.values()).filter(s => s.status === 'live' && s.listeners === 0);
  }

  /** Proactive schedule rotation */
  rotateSchedules(): number {
    const now = new Date();
    let rotated = 0;
    for (const [, schedule] of this.schedules) {
      if (schedule.endsAt < now) { rotated++; }
    }
    return rotated;
  }

  healthCheck(): { status: 'healthy' | 'degraded' | 'critical'; stations: number; liveStations: number; totalListeners: number; playlists: number; agents: number; bots: number; timestamp: Date } {
    const liveStations = Array.from(this.stations.values()).filter(s => s.status === 'live').length;
    const totalListeners = Array.from(this.stations.values()).reduce((sum, s) => sum + s.listeners, 0);
    return {
      status: liveStations === 0 ? 'critical' : 'healthy',
      stations: this.stations.size,
      liveStations,
      totalListeners,
      playlists: this.playlists.size,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: new Date(),
    };
  }
}
