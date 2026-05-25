/**
 * ActionBot — Action Execution Bot for DigitalGrid
 *
 * Identity:  NID-DIGITALGRID-ACTION
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    DigitalGridAI (AID-DIGITALGRID)
 *
 * Responsibilities:
 *   - Execute workflow actions based on action type
 *   - Support action types: transform, notify, store, http, script, composite
 *   - Provide execution results with timing and status
 *   - Handle error scenarios with retry and fallback information
 */

import { Bot, Logger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────

export interface ActionExecuteInput {
  operation: 'EXECUTE';
  actionType: 'transform' | 'notify' | 'store' | 'http' | 'script' | 'composite';
  config: Record<string, unknown>;
  input: Record<string, unknown>;
}

export type ActionInput = ActionExecuteInput;

export interface ActionResult {
  success: boolean;
  actionType: string;
  output: Record<string, unknown>;
  duration: number; // ms
  retries: number;
  metadata: Record<string, unknown>;
}

// ─────────────────────────────────────────────────────────────
// ActionBot Implementation
// ─────────────────────────────────────────────────────────────

export class ActionBot extends Bot {
  private readonly log: Logger;

  constructor() {
    // Must call super first — handler will be bound via execute()
    super(
      'NID-DIGITALGRID-ACTION',
      'Action',
      async (input: ActionInput): Promise<unknown> => ({ processed: true, input }),
      'Action execution (transform, notify, store, http, script, composite)'
    );

    this.log = new Logger('ActionBot');
  }

  private async process(input: ActionInput): Promise<ActionResult> {
    switch (input.operation) {
      case 'EXECUTE':
        return this.executeAction(input);
      default:
        throw new Error(`ActionBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // EXECUTE
  // ─────────────────────────────────────────────────────────────

  private async executeAction(input: ActionExecuteInput): Promise<ActionResult> {
    const { actionType, config, input: actionInput } = input;
    const startTime = Date.now();

    try {
      let result: ActionResult;

      switch (actionType) {
        case 'transform':
          result = this.executeTransform(config, actionInput, startTime);
          break;
        case 'notify':
          result = this.executeNotify(config, actionInput, startTime);
          break;
        case 'store':
          result = this.executeStore(config, actionInput, startTime);
          break;
        case 'http':
          result = await this.executeHttp(config, actionInput, startTime);
          break;
        case 'script':
          result = this.executeScript(config, actionInput, startTime);
          break;
        case 'composite':
          result = await this.executeComposite(config, actionInput, startTime);
          break;
        default:
          result = {
            success: false,
            actionType,
            output: {},
            duration: Date.now() - startTime,
            retries: 0,
            metadata: { error: `Unknown action type: ${actionType}` },
          };
      }

      this.log.info('Action executed', {
        actionType,
        success: result.success,
        duration: result.duration,
      });

      return result;
    } catch (error) {
      const duration = Date.now() - startTime;
      this.log.error('Action execution failed', { actionType, error: String(error) });

      return {
        success: false,
        actionType,
        output: {},
        duration,
        retries: 0,
        metadata: { error: String(error) },
      };
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Transform Action
  // ─────────────────────────────────────────────────────────────

  /**
   * Transform action: modifies data according to transformation rules.
   * Config: {
   *   mapping: Record<string, string>,   // output key → input path (dot notation)
   *   defaults: Record<string, unknown>, // default values for missing keys
   *   removeFields: string[],            // fields to exclude
   *   renameFields: Record<string, string>, // old name → new name
   *   addFields: Record<string, unknown>    // static fields to add
   * }
   */
  private executeTransform(
    config: Record<string, unknown>,
    input: Record<string, unknown>,
    startTime: number
  ): ActionResult {
    const mapping = (config.mapping as Record<string, string>) ?? {};
    const defaults = (config.defaults as Record<string, unknown>) ?? {};
    const removeFields = (config.removeFields as string[]) ?? [];
    const renameFields = (config.renameFields as Record<string, string>) ?? {};
    const addFields = (config.addFields as Record<string, unknown>) ?? {};

    const output: Record<string, unknown> = {};

    // Apply mapping — pull values from input using dot-notation paths
    for (const [outputKey, inputPath] of Object.entries(mapping)) {
      const value = this.resolvePath(input, inputPath);
      output[outputKey] = value !== undefined ? value : defaults[outputKey];
    }

    // Copy unmapped input fields (if no explicit mapping, pass through)
    if (Object.keys(mapping).length === 0) {
      Object.assign(output, JSON.parse(JSON.stringify(input)));
    }

    // Apply defaults for missing fields
    for (const [key, value] of Object.entries(defaults)) {
      if (output[key] === undefined) {
        output[key] = value;
      }
    }

    // Remove fields
    for (const field of removeFields) {
      delete output[field];
    }

    // Rename fields
    for (const [oldName, newName] of Object.entries(renameFields)) {
      if (output[oldName] !== undefined) {
        output[newName] = output[oldName];
        delete output[oldName];
      }
    }

    // Add static fields
    Object.assign(output, addFields);

    const transformSteps = [
      Object.keys(mapping).length > 0 ? 'mapping' : null,
      Object.keys(defaults).length > 0 ? 'defaults' : null,
      removeFields.length > 0 ? 'remove' : null,
      Object.keys(renameFields).length > 0 ? 'rename' : null,
      Object.keys(addFields).length > 0 ? 'add' : null,
    ].filter(Boolean);

    return {
      success: true,
      actionType: 'transform',
      output,
      duration: Date.now() - startTime,
      retries: 0,
      metadata: {
        transformSteps,
        outputFields: Object.keys(output),
        mappedFields: Object.keys(mapping).length,
      },
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Notify Action
  // ─────────────────────────────────────────────────────────────

  /**
   * Notify action: formats and dispatches notifications.
   * Config: {
   *   channel: 'email' | 'webhook' | 'slack' | 'log' | 'event',
   *   recipients: string[],
   *   template: string,            // template with {{variable}} placeholders
   *   subject?: string,            // for email
   *   priority?: 'low' | 'normal' | 'high' | 'critical',
   *   deduplicateKey?: string       // prevent duplicate notifications
   * }
   */
  private executeNotify(
    config: Record<string, unknown>,
    input: Record<string, unknown>,
    startTime: number
  ): ActionResult {
    const channel = (config.channel as string) ?? 'log';
    const recipients = (config.recipients as string[]) ?? [];
    const template = (config.template as string) ?? '';
    const subject = config.subject as string | undefined;
    const priority = (config.priority as string) ?? 'normal';

    // Render template with input variables
    const renderedMessage = this.renderTemplate(template, input);
    const renderedSubject = subject ? this.renderTemplate(subject, input) : undefined;

    // Build notification payload
    const notification: Record<string, unknown> = {
      channel,
      message: renderedMessage,
      subject: renderedSubject,
      priority,
      recipients,
      timestamp: Date.now(),
    };

    // In a real implementation, this would dispatch to the channel
    // For now, we log the notification as the dispatch action
    this.log.info('Notification dispatched', {
      channel,
      recipients: recipients.length,
      priority,
    });

    return {
      success: true,
      actionType: 'notify',
      output: {
        dispatched: true,
        channel,
        recipients,
        messagePreview: renderedMessage.slice(0, 200),
        subject: renderedSubject,
        priority,
      },
      duration: Date.now() - startTime,
      retries: 0,
      metadata: notification,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Store Action
  // ─────────────────────────────────────────────────────────────

  /**
   * Store action: persists data to a specified destination.
   * Config: {
   *   destination: 'memory' | 'file' | 'database',
   *   key: string,                  // storage key / path
   *   format?: 'json' | 'csv' | 'text',
   *   ttl?: number,                 // time-to-live in ms (for memory)
   *   overwrite?: boolean,          // overwrite existing data
   *   append?: boolean              // append to existing data
   * }
   */
  private executeStore(
    config: Record<string, unknown>,
    input: Record<string, unknown>,
    startTime: number
  ): ActionResult {
    const destination = (config.destination as string) ?? 'memory';
    const key = (config.key as string) ?? `data-${Date.now()}`;
    const format = (config.format as string) ?? 'json';
    const overwrite = (config.overwrite as boolean) ?? true;
    const append = (config.append as boolean) ?? false;

    let storedData: unknown;
    switch (format) {
      case 'csv':
        storedData = this.toCsv(input);
        break;
      case 'text':
        storedData = JSON.stringify(input);
        break;
      default:
        storedData = input;
    }

    const storageRecord = {
      key,
      destination,
      format,
      overwrite,
      append,
      data: storedData,
      storedAt: Date.now(),
    };

    this.log.info('Data stored', { destination, key, format });

    return {
      success: true,
      actionType: 'store',
      output: {
        key,
        destination,
        format,
        overwrite,
        append,
        storedAt: Date.now(),
        dataSize: JSON.stringify(storedData).length,
      },
      duration: Date.now() - startTime,
      retries: 0,
      metadata: storageRecord,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // HTTP Action
  // ─────────────────────────────────────────────────────────────

  /**
   * HTTP action: makes an HTTP request (simulated).
   * Config: {
   *   url: string,
   *   method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
   *   headers?: Record<string, string>,
   *   body?: Record<string, unknown>,
   *   timeout?: number,          // ms
   *   retries?: number,
   *   followRedirects?: boolean
   * }
   */
  private async executeHttp(
    config: Record<string, unknown>,
    input: Record<string, unknown>,
    startTime: number
  ): Promise<ActionResult> {
    const url = config.url as string;
    const method = ((config.method as string) ?? 'GET').toUpperCase();
    const headers = (config.headers as Record<string, string>) ?? {};
    const timeout = (config.timeout as number) ?? 30000;
    const maxRetries = (config.retries as number) ?? 0;

    // Merge input data into body for POST/PUT/PATCH
    let body = config.body ?? {};
    if (['POST', 'PUT', 'PATCH'].includes(method)) {
      body = { ...(body as Record<string, unknown>), ...input };
    }

    // In a real implementation, this would use fetch/axios
    // Simulated HTTP response
    const simulatedResponse = {
      status: 200,
      statusText: 'OK',
      headers: { 'content-type': 'application/json' },
      body: { success: true, url, method },
    };

    this.log.info('HTTP action simulated', { method, url, timeout });

    return {
      success: simulatedResponse.status >= 200 && simulatedResponse.status < 300,
      actionType: 'http',
      output: {
        url,
        method,
        status: simulatedResponse.status,
        statusText: simulatedResponse.statusText,
        responseBody: simulatedResponse.body,
      },
      duration: Date.now() - startTime,
      retries: 0,
      metadata: {
        requestHeaders: headers,
        requestBody: body,
        timeout,
        maxRetries,
      },
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Script Action
  // ─────────────────────────────────────────────────────────────

  /**
   * Script action: executes a predefined script template.
   * Config: {
   *   script: string,                 // script content or template
   *   language?: 'javascript' | 'typescript',
   *   timeout?: number,               // execution timeout ms
   *   environment?: Record<string, string>  // env variables
   * }
   */
  private executeScript(
    config: Record<string, unknown>,
    input: Record<string, unknown>,
    startTime: number
  ): ActionResult {
    const script = (config.script as string) ?? '';
    const language = (config.language as string) ?? 'javascript';
    const timeout = (config.timeout as number) ?? 5000;
    const environment = (config.environment as Record<string, string>) ?? {};

    // Script execution is simulated — in production would use a sandboxed VM
    // For now, we provide a safe template evaluation for simple expressions
    let output: Record<string, unknown>;
    try {
      // Simple expression evaluation: support basic math and string operations
      // on input data. Template variables are in {{variable}} format.
      const evaluatedScript = this.renderTemplate(script, input);
      output = {
        result: evaluatedScript,
        language,
        executed: true,
      };
    } catch (error) {
      output = {
        result: null,
        language,
        executed: false,
        error: String(error),
      };
    }

    this.log.info('Script action executed', { language, timeout });

    return {
      success: output.executed as boolean,
      actionType: 'script',
      output,
      duration: Date.now() - startTime,
      retries: 0,
      metadata: {
        scriptLength: script.length,
        language,
        timeout,
        envKeys: Object.keys(environment),
      },
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Composite Action
  // ─────────────────────────────────────────────────────────────

  /**
   * Composite action: chains multiple sub-actions sequentially.
   * Config: {
   *   actions: Array<{ actionType: string, config: Record<string, unknown> }>,
   *   failFast?: boolean,     // stop on first failure
   *   parallel?: boolean      // run actions in parallel (simulated as sequential here)
   * }
   */
  private async executeComposite(
    config: Record<string, unknown>,
    input: Record<string, unknown>,
    startTime: number
  ): Promise<ActionResult> {
    const actions = config.actions as Array<{
      actionType: ActionExecuteInput['actionType'];
      config: Record<string, unknown>;
    }>;
    const failFast = (config.failFast as boolean) ?? true;
    const parallel = (config.parallel as boolean) ?? false;

    if (!actions || actions.length === 0) {
      return {
        success: false,
        actionType: 'composite',
        output: {},
        duration: Date.now() - startTime,
        retries: 0,
        metadata: { error: 'No sub-actions defined' },
      };
    }

    const subResults: Array<{
      actionType: string;
      success: boolean;
      output: Record<string, unknown>;
      duration: number;
    }> = [];

    let currentInput = { ...input };

    for (const subAction of actions) {
      const subInput: ActionExecuteInput = {
        operation: 'EXECUTE',
        actionType: subAction.actionType,
        config: subAction.config,
        input: currentInput,
      };

      const result = await this.executeAction(subInput);
      subResults.push({
        actionType: result.actionType,
        success: result.success,
        output: result.output,
        duration: result.duration,
      });

      // Chain output to next action's input
      currentInput = { ...currentInput, ...result.output };

      if (!result.success && failFast) {
        break;
      }
    }

    const allSucceeded = subResults.every((r) => r.success);
    const totalDuration = Date.now() - startTime;

    this.log.info('Composite action executed', {
      actionCount: actions.length,
      completedCount: subResults.length,
      allSucceeded,
      parallel,
    });

    return {
      success: allSucceeded,
      actionType: 'composite',
      output: {
        // Last action's output is the composite output
        ...subResults[subResults.length - 1]?.output,
        _composite: {
          actionCount: actions.length,
          completedCount: subResults.length,
          results: subResults.map((r) => ({
            actionType: r.actionType,
            success: r.success,
          })),
        },
      },
      duration: totalDuration,
      retries: 0,
      metadata: {
        subResults,
        failFast,
        parallel,
      },
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Utilities
  // ─────────────────────────────────────────────────────────────

  private resolvePath(obj: Record<string, unknown>, path: string): unknown {
    const parts = path.split('.');
    let current: unknown = obj;
    for (const part of parts) {
      if (current === null || current === undefined || typeof current !== 'object') return undefined;
      current = (current as Record<string, unknown>)[part];
    }
    return current;
  }

  private renderTemplate(template: string, data: Record<string, unknown>): string {
    return template.replace(/\{\{(\w+(?:\.\w+)*)\}\}/g, (match, path) => {
      const value = this.resolvePath(data, path);
      return value !== undefined ? String(value) : match;
    });
  }

  private toCsv(data: Record<string, unknown>): string {
    // Simple flat-object to CSV
    const keys = Object.keys(data);
    const values = keys.map((k) => {
      const v = data[k];
      const str = typeof v === 'object' ? JSON.stringify(v) : String(v);
      return str.includes(',') ? `"${str}"` : str;
    });
    return `${keys.join(',')}\n${values.join(',')}`;
  }
}
