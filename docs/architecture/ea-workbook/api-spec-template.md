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
        authorizationCode:
          authorizationUrl: http://localhost:8005/auth/authorize
          tokenUrl: http://localhost:8005/auth/token   # Infinity — workers/infinity-auth/, authorization_code + PKCE only
          scopes:
            read:all: Read all resources
            write:all: Write all resources

  schemas:
    HealthResponse:
      type: object
      description: |
        Generic template shape. The Spark's real /mcp/health (src/mcp/server.py) returns
        status as a literal "ok" string plus a numeric `ts` (time.time()) rather than an
        enum + ISO timestamp — adjust required/properties per service to match its actual
        payload rather than assuming this generic shape.
      required: [status]
      properties:
        status:
          type: string
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
        JSON-RPC 2.0 endpoint for tool discovery and invocation, per src/mcp/. Valid
        `method` values are "tools/list" and "tools/call" only — the actual tool name
        goes under `params`, not `method`. RAG-MCP semantic matching (src/mcp/tool_rag.py)
        is a separate, optional discovery path (backed by an optional Qdrant client) used
        to help select a tool; it is not part of the tools/call request/response contract
        itself.

        **Rate Limit:** 1000 requests/hour
        **Timeout:** 60 seconds (asyncio.wait_for around the tool handler)
      operationId: invokeMcpTool
      tags: [Resources]
      security:
        - OAuth2: []
      # Real auth is Depends(get_current_user) — bearer JWT via Infinity. No OAuth2
      # scope is declared or enforced by the actual route; the empty list above
      # reflects that rather than inventing a "tools:invoke" scope that doesn't exist.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/RpcRequest'
      responses:
        '200':
          description: |
            JSON-RPC response envelope. The real implementation returns HTTP 200 for
            BOTH success and error outcomes — a failed call (invalid request, unknown
            tool, handler exception, timeout) comes back as this same 200 response
            with a populated `error` field inside RpcResponse, not as a 4xx/5xx status.
            There is no separate top-level ErrorResponse for JSON-RPC-level failures.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/RpcResponse'
        '401':
          description: Unauthorized — bearer JWT missing/invalid (rejected before the JSON-RPC layer is reached)
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
      required: [jsonrpc, method]
      properties:
        jsonrpc:
          type: string
          enum: ["2.0"]
        method:
          type: string
          enum: ["tools/list", "tools/call"]
          description: |
            JSON-RPC method name — only "tools/list" and "tools/call" are valid.
            The registered tool name itself is passed inside `params`, not here.
        params:
          type: object
        id:
          description: |
            Per JSON-RPC 2.0, optional and may be a string, number, or null — not
            required. A request with no `id` is treated as a notification.
          oneOf:
            - type: string
            - type: number
            - type: "null"

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
