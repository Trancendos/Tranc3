/**
 * Trancendos Logger — lightweight structured logger
 *
 * Production note: replace with Pino / Winston / structured JSON logger
 * for actual deployment. This scaffold provides the interface contract
 * used across all hubs, agents, and bots.
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

let globalLevel: LogLevel = (process.env.LOG_LEVEL as LogLevel) || 'info';

export function setGlobalLogLevel(level: LogLevel): void {
  globalLevel = level;
}

export class Logger {
  private readonly namespace: string;
  private readonly minLevel: LogLevel;

  constructor(namespace: string, minLevel?: LogLevel) {
    this.namespace = namespace;
    this.minLevel = minLevel ?? globalLevel;
  }

  private shouldLog(level: LogLevel): boolean {
    return LEVEL_PRIORITY[level] >= LEVEL_PRIORITY[this.minLevel];
  }

  private emit(level: LogLevel, message: string, data?: Record<string, any>): void {
    if (!this.shouldLog(level)) return;
    const ts = new Date().toISOString();
    const prefix = `[${ts}] [${level.toUpperCase()}] [${this.namespace}]`;
    if (data && Object.keys(data).length > 0) {
      console.log(`${prefix} ${message}`, JSON.stringify(data));
    } else {
      console.log(`${prefix} ${message}`);
    }
  }

  debug(message: string, data?: Record<string, any>): void {
    this.emit('debug', message, data);
  }

  info(message: string, data?: Record<string, any>): void {
    this.emit('info', message, data);
  }

  warn(message: string, data?: Record<string, any>): void {
    this.emit('warn', message, data);
  }

  error(message: string, data?: Record<string, any>): void {
    this.emit('error', message, data);
  }

  /** Create a child logger with a sub-namespace */
  child(subNamespace: string): Logger {
    return new Logger(`${this.namespace}:${subNamespace}`, this.minLevel);
  }
}
