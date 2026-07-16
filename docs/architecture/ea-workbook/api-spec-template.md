# API Specification Template (OpenAPI 3.1)

A reusable OpenAPI 3.1 skeleton for documenting the endpoints tracked in `05_apis.csv`,
plus one fully worked example grounded in a real, already-implemented route (`API-SPARK-001`
— The Spark's MCP JSON-RPC endpoint, `src/mcp/`).

Fill in `[Service Name]`, `[Tier 3 AI Name]`, and the `x-sla`/rate-limit values directly
from the matching row in `01_business_services.csv` / `02_service_inventory.csv` /
`05_apis.csv` so the OpenAPI doc and the CMDB never drift apart.

## Base structure

```yaml
openapi: 3.1.0
info:
  title: Tranc3 [Service Name] API
  description: |
    [Service Description]

    **Service Owner:** [Tier 3 AI Name]
    **SLA:** [SLA from 02_service_inventory.csv]
    **Rate Limit:** [RateLimit from 05_apis.csv]
    **Authentication:** [AuthMethod from 05_apis.csv]
  version: 1.0.0
  contact:
    name: [Tier 3 AI Name]

servers:
  - url: http://localhost:8000
    description: tranc3-backend (production, single self-hosted host)
  - url: http://localhost:8000
    description: Development (make dev-api, hot-reload)

security:
  - OAuth2:
      - read:all
      - write:all

tags:
  - name: Resources
    description: Core resource operations
  - name: Monitoring
    description: Health and monitoring endpoints

paths:
  /health:
    get:
      summary: Health Check
      operationId: getHealth
      tags: [Monitoring]
      security: []
      responses:
        '200':
          description: Service is healthy
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HealthResponse'
        '503':
          description: Service is unhealthy
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'

components:
  securitySchemes:
    OAuth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: http://localhost:8005/oauth2/token   # Infinity — workers/infinity-auth/
          scopes:
            read:all: Read all resources
            write:all: Write all resources

  schemas:
    HealthResponse:
      type: object
      required: [status, timestamp]
      properties:
        status:
          type: string
          enum: [healthy, degraded, unhealthy]
        timestamp:
          type: string
          format: date-time

    ErrorResponse:
      type: object
      required: [error, message, timestamp]
      properties:
        error:
          type: string
        message:
          type: string
        timestamp:
          type: string
          format: date-time
        trace_id:
          type: string
          description: Distributed trace ID — correlates with The Observatory's tracing

x-rate-limit:
  default: 1000
  window: 3600

x-sla:
  availability: 99.9%
  response_time_p99_ms: 5000
```

Note the deliberate divergence from a generic template: no `staging-api.example.com` /
`dev-api.example.com` server variants, because this platform runs one production host
(`SRV-CITADEL-01`) — see `07_environments.csv`. Add a real staging server URL only once
`ENV-004` actually has a distinct routable endpoint.

## Worked example: The Spark — MCP JSON-RPC Endpoint

Matches `API-SPARK-001` in `05_apis.csv` exactly (rate limit, auth scope, timeout).

```yaml
paths:
  /mcp/rpc:
    post:
      summary: Invoke a registered MCP tool
      description: |
        JSON-RPC 2.0 endpoint for tool discovery and invocation, per src/mcp/.
        Tool selection uses RAG-MCP semantic matching (src/mcp/tool_rag.py) when
        more than one registered tool could satisfy the request.

        **Rate Limit:** 1000 requests/hour
        **Timeout:** 5 seconds
      operationId: invokeMcpTool
      tags: [Resources]
      security:
        - OAuth2: [tools:invoke]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/RpcRequest'
      responses:
        '200':
          description: Tool invocation result
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/RpcResponse'
        '400':
          description: Invalid JSON-RPC request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '401':
          description: Unauthorized
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '429':
          description: Rate limit exceeded
          headers:
            Retry-After:
              schema:
                type: integer
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'

components:
  schemas:
    RpcRequest:
      type: object
      required: [jsonrpc, method, id]
      properties:
        jsonrpc:
          type: string
          enum: ["2.0"]
        method:
          type: string
          description: Registered tool name, or "tools/list" for discovery
        params:
          type: object
        id:
          type: string

    RpcResponse:
      type: object
      required: [jsonrpc, id]
      properties:
        jsonrpc:
          type: string
          enum: ["2.0"]
        result:
          type: object
        error:
          $ref: '#/components/schemas/ErrorResponse'
        id:
          type: string
```

## Versioning strategy

Follows `MAJOR.MINOR.PATCH` against the `VersionCode` column in `05_apis.csv`:

- **MAJOR** — breaking change (removed/renamed field, removed endpoint). Set
  `DeprecationDate` and `DeprecationReplacement` on the old `APIID` row at least one
  release ahead of removal.
- **MINOR** — backward-compatible addition (new optional field, new endpoint).
- **PATCH** — bug fix, no client-visible contract change.

Every new API added to this platform should get a row in `05_apis.csv` and a filled-in
copy of this template before merging — that is what keeps the CMDB and the actual wire
contract in sync instead of drifting apart, which was one of the original gaps this
workbook exists to close.
