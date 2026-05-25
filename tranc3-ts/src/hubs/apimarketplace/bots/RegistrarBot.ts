/**
 * RegistrarBot — API Endpoint Registration Bot for The API Marketplace
 *
 * Identity:  NID-APIMARKETPLACE-REGISTRAR
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheAPIMarketplaceAI (AID-APIMARKETPLACE)
 *
 * Responsibilities:
 *   - Publish new API endpoints to the marketplace registry
 *   - Assign unique identifiers and API keys
 *   - Validate endpoint uniqueness (method + path combination)
 *   - Generate OpenAPI specification stubs
 *   - Track registration metadata and provenance
 *
 * "First impressions matter — register with precision."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface RegistrarInput {
  operation: 'PUBLISH';
  name: string;
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'OPTIONS' | 'HEAD';
  path: string;
  basePath: string;
  version: string;
  visibility?: 'public' | 'internal' | 'partner';
  authentication?: 'none' | 'apikey' | 'oauth2' | 'jwt' | 'mtls';
  description?: string;
  tags?: string[];
  rateLimit?: {
    requests: number;
    window: number;
  };
}

export interface OpenAPIStub {
  openapi: string;
  info: {
    title: string;
    version: string;
    description: string;
  };
  paths: Record<string, Record<string, {
    summary: string;
    operationId: string;
    tags: string[];
    responses: Record<string, { description: string }>;
  }>>;
}

export interface PublishResult {
  success: boolean;
  endpointId: string;
  name: string;
  method: string;
  fullPath: string;
  version: string;
  visibility: string;
  authentication: string;
  openApiStub: OpenAPIStub;
  registrationToken: string;
  registeredAt: number;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// RegistrarBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class RegistrarBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly registry: Map<string, { method: string; path: string; registeredAt: number }>;

  constructor() {
    const handler = async (input: RegistrarInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-APIMARKETPLACE-REGISTRAR',
      'Registrar',
      handler,
      'API endpoint registration with uniqueness validation and OpenAPI spec generation'
    );

    this.log = new Logger('RegistrarBot');
    this.audit = auditLedger;
    this.registry = new Map();
  }

  private async process(input: RegistrarInput): Promise<PublishResult> {
    switch (input.operation) {
      case 'PUBLISH':
        return this.publish(input);
      default:
        throw new Error(`RegistrarBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // PUBLISH
  // ─────────────────────────────────────────────────────────────────────────

  private publish(input: RegistrarInput): PublishResult {
    const {
      name,
      method,
      path,
      basePath,
      version,
      visibility,
      authentication,
      description,
      tags,
      rateLimit,
    } = input;

    const fullPath = `${basePath}${path}`;
    const endpointKey = `${method}:${fullPath}`;

    // Check uniqueness
    if (this.registry.has(endpointKey)) {
      throw new Error(
        `RegistrarBot: Endpoint ${method} ${fullPath} is already registered. Use versioning for variations.`
      );
    }

    // Generate endpoint ID
    const endpointId = `EP-${this.registry.size + 1}`;

    // Generate registration token
    const registrationToken = `rt_${Buffer.from(`${endpointId}:${Date.now()}`).toString('base64url').slice(0, 24)}`;

    // Register
    this.registry.set(endpointKey, {
      method,
      path: fullPath,
      registeredAt: Date.now(),
    });

    // Generate OpenAPI stub
    const openApiStub: OpenAPIStub = {
      openapi: '3.1.0',
      info: {
        title: name,
        version,
        description: description ?? `${method} ${fullPath}`,
      },
      paths: {
        [path]: {
          [method.toLowerCase()]: {
            summary: description ?? `${method} ${path}`,
            operationId: `${name.replace(/\s+/g, '_')}_${method.toLowerCase()}`,
            tags: tags ?? [basePath.replace(/\//g, '')],
            responses: {
              '200': { description: 'Successful response' },
              '400': { description: 'Bad request' },
              '401': { description: 'Unauthorized' },
              '404': { description: 'Not found' },
              '500': { description: 'Internal server error' },
            },
          },
        },
      },
    };

    this.audit.append({
      actor: 'NID-APIMARKETPLACE-REGISTRAR',
      action: 'ENDPOINT_PUBLISHED',
      entity: endpointId,
      status: 'SUCCESS',
      meta: {
        name,
        method,
        fullPath,
        version,
        visibility: visibility ?? 'public',
        authentication: authentication ?? 'apikey',
        rateLimit,
      },
    });

    this.log.info('Endpoint registered', {
      endpointId,
      name,
      method,
      fullPath,
      version,
    });

    return {
      success: true,
      endpointId,
      name,
      method,
      fullPath,
      version,
      visibility: visibility ?? 'public',
      authentication: authentication ?? 'apikey',
      openApiStub,
      registrationToken,
      registeredAt: Date.now(),
      timestamp: Date.now(),
    };
  }
}
