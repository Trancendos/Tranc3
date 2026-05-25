/**
 * RouterBot — API Request Routing Bot for The API Marketplace
 *
 * Identity:  NID-APIMARKETPLACE-ROUTER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheAPIMarketplaceAI (AID-APIMARKETPLACE)
 *
 * Responsibilities:
 *   - Route incoming API requests to correct backend services
 *   - Match request paths against registered endpoint patterns
 *   - Apply authentication and rate limiting checks
 *   - Load balance across multiple backend instances
 *   - Track routing decisions and latency metrics
 *
 * "Every request finds its destination — or a meaningful 404."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface RouterInput {
  operation: 'ROUTE';
  method: string;
  path: string;
  headers: Record<string, string>;
  queryParams?: Record<string, string>;
  body?: unknown;
  clientIp?: string;
}

export interface RouteMatch {
  matched: boolean;
  endpointId?: string;
  serviceName?: string;
  serviceUrl?: string;
  pathParams?: Record<string, string>;
  pathMatch: 'exact' | 'pattern' | 'prefix' | 'none';
}

export interface BackendInstance {
  id: string;
  url: string;
  healthy: boolean;
  weight: number;
  activeConnections: number;
  averageLatency: number;
}

export interface RoutingDecision {
  route: RouteMatch;
  backend: BackendInstance | null;
  authenticationStatus: 'authenticated' | 'unauthenticated' | 'expired' | 'invalid';
  rateLimitStatus: 'within' | 'approaching' | 'exceeded';
  latencyEstimate: number;
  requestId: string;
}

export interface RouteResult {
  success: boolean;
  decision: RoutingDecision;
  routingTime: number;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Simulated Service Registry
// ─────────────────────────────────────────────────────────────────────────────

const SERVICE_REGISTRY: Record<string, {
  serviceName: string;
  instances: BackendInstance[];
  supportedMethods: string[];
}> = {
  '/api/v1/users': {
    serviceName: 'user-service',
    instances: [
      { id: 'usr-1', url: 'http://user-service:8080', healthy: true, weight: 1, activeConnections: 12, averageLatency: 45 },
      { id: 'usr-2', url: 'http://user-service:8081', healthy: true, weight: 1, activeConnections: 8, averageLatency: 52 },
      { id: 'usr-3', url: 'http://user-service:8082', healthy: false, weight: 0, activeConnections: 0, averageLatency: 0 },
    ],
    supportedMethods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
  },
  '/api/v1/data': {
    serviceName: 'data-service',
    instances: [
      { id: 'dat-1', url: 'http://data-service:8080', healthy: true, weight: 1, activeConnections: 25, averageLatency: 120 },
      { id: 'dat-2', url: 'http://data-service:8081', healthy: true, weight: 2, activeConnections: 15, averageLatency: 95 },
    ],
    supportedMethods: ['GET', 'POST'],
  },
  '/api/v1/reports': {
    serviceName: 'report-service',
    instances: [
      { id: 'rpt-1', url: 'http://report-service:8080', healthy: true, weight: 1, activeConnections: 3, averageLatency: 350 },
    ],
    supportedMethods: ['GET'],
  },
  '/api/v1/auth': {
    serviceName: 'auth-service',
    instances: [
      { id: 'auth-1', url: 'http://auth-service:8080', healthy: true, weight: 1, activeConnections: 45, averageLatency: 25 },
      { id: 'auth-2', url: 'http://auth-service:8081', healthy: true, weight: 1, activeConnections: 38, averageLatency: 30 },
    ],
    supportedMethods: ['POST', 'OPTIONS'],
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// RouterBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class RouterBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    const handler = async (input: RouterInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-APIMARKETPLACE-ROUTER',
      'Router',
      handler,
      'API request routing with path matching, load balancing, and authentication checks'
    );

    this.log = new Logger('RouterBot');
    this.audit = auditLedger;
  }

  private async process(input: RouterInput): Promise<RouteResult> {
    switch (input.operation) {
      case 'ROUTE':
        return this.route(input);
      default:
        throw new Error(`RouterBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ROUTE
  // ─────────────────────────────────────────────────────────────────────────

  private route(input: RouterInput): RouteResult {
    const startTime = Date.now();
    const { method, path, headers, queryParams } = input;

    // Generate request ID
    const requestId = `req_${Buffer.from(`${Date.now()}:${path}`).toString('base64url').slice(0, 16)}`;

    // Match route
    const route = this.matchRoute(method, path);

    // Select backend instance
    const backend = route.matched && route.serviceName
      ? this.selectBackend(route.serviceName)
      : null;

    // Check authentication
    const authenticationStatus = this.checkAuthentication(headers);

    // Check rate limits
    const rateLimitStatus = this.checkRateLimit(headers);

    // Estimate latency
    const latencyEstimate = backend ? backend.averageLatency + Math.floor(Math.random() * 20) : 0;

    const decision: RoutingDecision = {
      route,
      backend,
      authenticationStatus,
      rateLimitStatus,
      latencyEstimate,
      requestId,
    };

    const routingTime = Date.now() - startTime;

    const success = route.matched && backend !== null && authenticationStatus !== 'invalid';

    this.audit.append({
      actor: 'NID-APIMARKETPLACE-ROUTER',
      action: 'REQUEST_ROUTED',
      entity: requestId,
      status: success ? 'SUCCESS' : 'FAILURE',
      meta: {
        method,
        path,
        matched: route.matched,
        serviceName: route.serviceName,
        backendId: backend?.id,
        authenticationStatus,
        rateLimitStatus,
        latencyEstimate,
        routingTime,
      },
    });

    this.log.info('Request routed', {
      requestId,
      method,
      path,
      matched: route.matched,
      backend: backend?.id,
      authStatus: authenticationStatus,
      routingTime,
    });

    return {
      success,
      decision,
      routingTime,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private matchRoute(method: string, path: string): RouteMatch {
    // Try exact match first
    for (const [routePath, service] of Object.entries(SERVICE_REGISTRY)) {
      if (path === routePath || path.startsWith(routePath + '/') || path.startsWith(routePath + '?')) {
        if (!service.supportedMethods.includes(method.toUpperCase())) {
          return {
            matched: false,
            pathMatch: 'none',
          };
        }

        // Extract path parameters (e.g., /api/v1/users/123 → { id: "123" })
        const pathParts = path.replace(routePath, '').split('/').filter(Boolean);
        const pathParams: Record<string, string> = {};
        if (pathParts.length > 0) {
          pathParams['id'] = pathParts[0];
        }

        return {
          matched: true,
          endpointId: `EP-${Object.keys(SERVICE_REGISTRY).indexOf(routePath) + 1}`,
          serviceName: service.serviceName,
          serviceUrl: service.instances[0]?.url,
          pathParams: Object.keys(pathParams).length > 0 ? pathParams : undefined,
          pathMatch: 'prefix',
        };
      }
    }

    // No match found
    return {
      matched: false,
      pathMatch: 'none',
    };
  }

  private selectBackend(serviceName: string): BackendInstance | null {
    // Find the service
    const service = Object.values(SERVICE_REGISTRY).find((s) => s.serviceName === serviceName);
    if (!service) return null;

    // Filter healthy instances
    const healthyInstances = service.instances.filter((i) => i.healthy);
    if (healthyInstances.length === 0) return null;

    // Weighted least-connections selection
    const sorted = healthyInstances.sort((a, b) => {
      const scoreA = a.activeConnections / a.weight;
      const scoreB = b.activeConnections / b.weight;
      return scoreA - scoreB;
    });

    return sorted[0];
  }

  private checkAuthentication(headers: Record<string, string>): RoutingDecision['authenticationStatus'] {
    const authHeader = headers['Authorization'] ?? headers['authorization'];

    if (!authHeader) {
      return 'unauthenticated';
    }

    // Simulate auth check
    if (authHeader.startsWith('Bearer ')) {
      // 95% valid, 4% expired, 1% invalid
      const rand = Math.random();
      if (rand < 0.95) return 'authenticated';
      if (rand < 0.99) return 'expired';
      return 'invalid';
    }

    if (authHeader.startsWith('ApiKey ')) {
      return Math.random() < 0.97 ? 'authenticated' : 'invalid';
    }

    return 'invalid';
  }

  private checkRateLimit(headers: Record<string, string>): RoutingDecision['rateLimitStatus'] {
    // Simulate rate limit check based on API key
    const apiKey = headers['X-API-Key'] ?? headers['x-api-key'];

    if (!apiKey) {
      // No API key — assume free tier
      return Math.random() < 0.1 ? 'exceeded' : 'approaching';
    }

    // With API key — better limits
    const rand = Math.random();
    if (rand < 0.85) return 'within';
    if (rand < 0.97) return 'approaching';
    return 'exceeded';
  }
}
