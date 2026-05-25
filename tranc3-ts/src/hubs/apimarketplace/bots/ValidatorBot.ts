/**
 * ValidatorBot — API Contract Validation Bot for The API Marketplace
 *
 * Identity:  NID-APIMARKETPLACE-VALIDATOR
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheAPIMarketplaceAI (AID-APIMARKETPLACE)
 *
 * Responsibilities:
 *   - Validate API contracts against schemas (request/response)
 *   - Check for common API anti-patterns
 *   - Verify versioning and naming conventions
 *   - Validate authentication configuration
 *   - Generate validation reports with pass/fail/suggestion items
 *
 * "A contract is only as strong as its validation."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface ValidatorInput {
  operation: 'VALIDATE';
  endpointId: string;
  contract: {
    requestSchema?: Record<string, unknown>;
    responseSchema?: Record<string, unknown>;
    errorSchemas?: Record<string, Record<string, unknown>>;
    headers?: Record<string, string>;
    queryParams?: Record<string, { type: string; required: boolean; description: string }>;
  };
  strictMode?: boolean;  // fail on warnings too
}

export interface ValidationItem {
  category: 'schema' | 'naming' | 'versioning' | 'security' | 'best-practice' | 'performance';
  severity: 'error' | 'warning' | 'info';
  rule: string;
  message: string;
  path?: string;
  suggestion?: string;
}

export interface ValidationReport {
  endpointId: string;
  valid: boolean;
  totalChecks: number;
  errors: number;
  warnings: number;
  infos: number;
  items: ValidationItem[];
  score: number; // 0-100
  validatedAt: number;
}

export interface ValidateResult {
  success: boolean;
  endpointId: string;
  report: ValidationReport;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Validation Rules
// ─────────────────────────────────────────────────────────────────────────────

const NAMING_PATTERNS = {
  pathSegment: /^[a-z0-9\-\.]+$/,          // lowercase, digits, hyphens, dots
  queryParam: /^[a-z][a-zA-Z0-9]*$/,       // camelCase starting lowercase
  header: /^[A-Z][a-zA-Z0-9\-]*$/,         // PascalCase-Header
  errorKey: /^[0-9]{3}$/,                   // HTTP status codes
};

// ─────────────────────────────────────────────────────────────────────────────
// ValidatorBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class ValidatorBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    const handler = async (input: ValidatorInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-APIMARKETPLACE-VALIDATOR',
      'Validator',
      handler,
      'API contract validation with schema checks, naming conventions, and best-practice enforcement'
    );

    this.log = new Logger('ValidatorBot');
    this.audit = AuditLedger.getInstance();
  }

  private async process(input: ValidatorInput): Promise<ValidateResult> {
    switch (input.operation) {
      case 'VALIDATE':
        return this.validate(input);
      default:
        throw new Error(`ValidatorBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // VALIDATE
  // ─────────────────────────────────────────────────────────────────────────

  private validate(input: ValidatorInput): ValidateResult {
    const { endpointId, contract, strictMode } = input;
    const items: ValidationItem[] = [];

    // ─── Schema Validation ───────────────────────────────────────────────
    if (!contract.requestSchema && !contract.responseSchema) {
      items.push({
        category: 'schema',
        severity: 'error',
        rule: 'SCHEMA_REQUIRED',
        message: 'At least one of requestSchema or responseSchema must be defined',
        suggestion: 'Define request and response schemas for full contract coverage',
      });
    } else {
      if (contract.requestSchema) {
        items.push({
          category: 'schema',
          severity: 'info',
          rule: 'REQUEST_SCHEMA_DEFINED',
          message: 'Request schema is defined',
        });
      } else {
        items.push({
          category: 'schema',
          severity: 'warning',
          rule: 'REQUEST_SCHEMA_MISSING',
          message: 'Request schema is not defined',
          suggestion: 'Define a request schema to enable input validation',
        });
      }

      if (contract.responseSchema) {
        items.push({
          category: 'schema',
          severity: 'info',
          rule: 'RESPONSE_SCHEMA_DEFINED',
          message: 'Response schema is defined',
        });
      } else {
        items.push({
          category: 'schema',
          severity: 'warning',
          rule: 'RESPONSE_SCHEMA_MISSING',
          message: 'Response schema is not defined',
          suggestion: 'Define a response schema for contract completeness',
        });
      }
    }

    // ─── Error Schemas ──────────────────────────────────────────────────
    if (contract.errorSchemas) {
      const errorKeys = Object.keys(contract.errorSchemas);
      if (errorKeys.length === 0) {
        items.push({
          category: 'schema',
          severity: 'warning',
          rule: 'ERROR_SCHEMAS_EMPTY',
          message: 'Error schemas object is empty',
          suggestion: 'Define error schemas for 4xx and 5xx responses',
        });
      } else {
        // Validate error key format (should be HTTP status codes)
        for (const key of errorKeys) {
          if (!NAMING_PATTERNS.errorKey.test(key) && !key.startsWith('4') && !key.startsWith('5')) {
            items.push({
              category: 'naming',
              severity: 'warning',
              rule: 'ERROR_KEY_FORMAT',
              message: `Error key "${key}" doesn't follow HTTP status code format`,
              path: `errorSchemas.${key}`,
              suggestion: 'Use HTTP status codes (e.g., "400", "404", "500") as error schema keys',
            });
          }
        }

        items.push({
          category: 'schema',
          severity: 'info',
          rule: 'ERROR_SCHEMAS_DEFINED',
          message: `${errorKeys.length} error schema(s) defined: ${errorKeys.join(', ')}`,
        });
      }
    } else {
      items.push({
        category: 'schema',
        severity: 'warning',
        rule: 'ERROR_SCHEMAS_MISSING',
        message: 'Error schemas are not defined',
        suggestion: 'Define error response schemas for common HTTP errors (400, 404, 500)',
      });
    }

    // ─── Headers Validation ──────────────────────────────────────────────
    if (contract.headers) {
      const headers = Object.keys(contract.headers);
      const standardHeaders = ['Content-Type', 'Authorization', 'X-Request-ID', 'X-Correlation-ID'];

      for (const stdHeader of standardHeaders) {
        if (!headers.includes(stdHeader)) {
          items.push({
            category: 'best-practice',
            severity: 'info',
            rule: 'STANDARD_HEADER_MISSING',
            message: `Standard header "${stdHeader}" not specified`,
            suggestion: `Consider adding "${stdHeader}" to your API headers for better interoperability`,
          });
        }
      }

      items.push({
        category: 'schema',
        severity: 'info',
        rule: 'HEADERS_DEFINED',
        message: `${headers.length} header(s) defined: ${headers.join(', ')}`,
      });
    }

    // ─── Query Parameters Validation ─────────────────────────────────────
    if (contract.queryParams) {
      const params = Object.entries(contract.queryParams);
      for (const [paramName, config] of params) {
        if (!NAMING_PATTERNS.queryParam.test(paramName)) {
          items.push({
            category: 'naming',
            severity: 'warning',
            rule: 'QUERY_PARAM_NAMING',
            message: `Query parameter "${paramName}" doesn't follow camelCase convention`,
            suggestion: 'Use camelCase for query parameter names (e.g., myParam, pageSize)',
          });
        }

        if (!config.description) {
          items.push({
            category: 'best-practice',
            severity: 'warning',
            rule: 'QUERY_PARAM_DESCRIPTION',
            message: `Query parameter "${paramName}" lacks a description`,
            suggestion: 'Add descriptions to all query parameters for documentation',
          });
        }
      }
    }

    // ─── Security Checks ─────────────────────────────────────────────────
    if (contract.headers?.['Authorization']) {
      items.push({
        category: 'security',
        severity: 'info',
        rule: 'AUTH_HEADER_PRESENT',
        message: 'Authorization header is specified',
      });
    } else {
      items.push({
        category: 'security',
        severity: 'warning',
        rule: 'AUTH_HEADER_MISSING',
        message: 'No Authorization header specified',
        suggestion: 'Consider requiring authentication for API security',
      });
    }

    // ─── Best Practices ──────────────────────────────────────────────────
    if (!contract.queryParams || Object.keys(contract.queryParams).length === 0) {
      items.push({
        category: 'best-practice',
        severity: 'info',
        rule: 'NO_QUERY_PARAMS',
        message: 'No query parameters defined — consider pagination for list endpoints',
      });
    }

    // ─── Performance ─────────────────────────────────────────────────────
    items.push({
      category: 'performance',
      severity: 'info',
      rule: 'CONTRACT_SIZE',
      message: `Contract contains ${JSON.stringify(contract).length} bytes of schema definition`,
    });

    // ─── Calculate Results ───────────────────────────────────────────────
    const errors = items.filter((i) => i.severity === 'error').length;
    const warnings = items.filter((i) => i.severity === 'warning').length;
    const infos = items.filter((i) => i.severity === 'info').length;

    // Score calculation: start at 100, subtract for errors/warnings
    const score = Math.max(0, Math.min(100, 100 - (errors * 25) - (warnings * 5)));

    const valid = strictMode ? (errors === 0 && warnings === 0) : (errors === 0);

    const report: ValidationReport = {
      endpointId,
      valid,
      totalChecks: items.length,
      errors,
      warnings,
      infos,
      items,
      score,
      validatedAt: Date.now(),
    };

    this.audit.append({
      actor: 'NID-APIMARKETPLACE-VALIDATOR',
      action: 'CONTRACT_VALIDATED',
      entity: endpointId,
      status: valid ? 'SUCCESS' : 'FAILURE',
      meta: {
        valid,
        score,
        errors,
        warnings,
        infos,
        strictMode: strictMode ?? false,
      },
    });

    this.log.info('Contract validated', {
      endpointId,
      valid,
      score,
      errors,
      warnings,
    });

    return {
      success: valid,
      endpointId,
      report,
      timestamp: Date.now(),
    };
  }
}
