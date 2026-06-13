# Tranc3 API Reference

> **Version:** 0.1.0  
> **Base URL:** `http://localhost:8000`  
> **Authentication:** Bearer token (JWT) for protected endpoints  
> **Protocol:** HTTP/REST + WebSocket  

---

## Overview

The Tranc3 platform exposes two FastAPI applications:

1. **Primary API** (`api.py`) — Core inference, auth, billing, and admin endpoints
2. **Enhanced API** (`api_enhanced.py`) — MCP, workflow, deepmind, skills, code, healing, evolution, and personality endpoints

Both applications share the same authentication middleware and can be mounted together or run independently.

---

## Authentication

All protected endpoints require a valid JWT Bearer token in the `Authorization` header:

```
Authorization: Bearer <token>
```

### Register

```
POST /auth/register
```

Register a new user account.

**Request Body:**
```json
{
  "username": "string",
  "email": "string",
  "password": "string"
}
```

### Obtain Token

```
POST /auth/token
```

Authenticate and receive a JWT access token.

**Request Body:** OAuth2 password flow (`username`, `password`, `grant_type`)

### Refresh Token

```
POST /auth/refresh
```

Refresh an expired access token using a valid refresh token.

---

## System Endpoints

### Health Check

```
GET /health
```

Returns the system health status including service availability, model readiness, and uptime.

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "uptime_seconds": 12345,
  "model_loaded": true,
  "workers_active": 13
}
```

### Readiness Check

```
GET /ready
```

Returns whether the system is ready to accept requests.

**Response:** `200 OK`
```json
{
  "ready": true,
  "checks": {
    "database": "ok",
    "model": "ok",
    "cache": "ok"
  }
}
```

### Metrics

```
GET /metrics
```

Returns Prometheus-compatible metrics for monitoring.

**Response:** `200 OK` (text/plain)

### Feature Flags

```
GET /features
```

Returns the current feature flag configuration.

**Response:** `200 OK`
```json
{
  "features": {
    "consciousness_engine": true,
    "quantum_inference": false,
    "mcp_protocol": true
  }
}
```

---

## Inference Endpoints

### Chat Completion

```
POST /chat
```

Primary inference endpoint for conversational AI.

**Request Body:**
```json
{
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "model": "tranc3-default",
  "temperature": 0.7,
  "max_tokens": 512,
  "personality": "default"
}
```

**Response:** `200 OK`
```json
{
  "response": "Hello! How can I assist you today?",
  "model": "tranc3-default",
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 8,
    "total_tokens": 18
  }
}
```

### Emotion Analysis

```
POST /analyze-emotion
```

Analyze the emotional content of text.

**Request Body:**
```json
{
  "text": "I'm so excited about this project!"
}
```

**Response:** `200 OK`
```json
{
  "emotion": "joy",
  "confidence": 0.92,
  "valence": 0.85,
  "arousal": 0.78
}
```

### Feedback Submission

```
POST /feedback
```

Submit user feedback for model improvement.

**Request Body:**
```json
{
  "message_id": "string",
  "rating": 5,
  "comment": "Great response!"
}
```

### Consciousness Score

```
POST /consciousness/score
```

Calculate consciousness metrics for the AI system.

**Request Body:**
```json
{
  "session_id": "string",
  "interaction_count": 42
}
```

**Response:** `200 OK`
```json
{
  "consciousness_score": 0.73,
  "self_awareness": 0.68,
  "empathy_index": 0.81
}
```

---

## Information Endpoints

### Supported Languages

```
GET /languages
```

Returns list of supported languages for multilingual inference.

### Available Personalities

```
GET /personalities
```

Returns list of available AI personality profiles.

---

## Billing Endpoints

### Billing Tiers

```
GET /billing/tiers
```

Returns available billing tiers and their limits.

### Usage Summary

```
GET /billing/usage
```

Returns current billing period usage for the authenticated user.

### Checkout Session

```
POST /billing/checkout
```

Create a billing checkout session.

**Request Body:**
```json
{
  "tier": "pro",
  "period": "monthly"
}
```

### Webhook

```
POST /billing/webhook
```

Stripe webhook endpoint (not included in API schema).

---

## Compliance Endpoints

### Delete User Data

```
DELETE /memory/{user_id}
```

Delete all stored data for a user (GDPR right to erasure).

**Path Parameters:**
- `user_id` (string, required) — The user identifier

---

## WebSocket

### Chat WebSocket

```
WS /ws/chat
```

Real-time chat via WebSocket protocol. Supports streaming responses.

**Message Format:**
```json
{
  "type": "chat",
  "content": "Hello",
  "personality": "default"
}
```

---

## Admin Endpoints

All admin endpoints require authentication.

### Service Registry

```
GET /admin/registry
```

List all registered services in the platform.

### Service Detail

```
GET /admin/registry/{fid}
```

Get details for a specific service by its functional ID.

### Circuit Breaker Status

```
GET /admin/circuits
```

View the status of all circuit breakers.

### Event Loops

```
GET /admin/loops
```

View active event loop statistics.

### Abuse Detection

```
GET /admin/abuse
```

View abuse detection statistics and blocked requests.

### Self-Healing Status

```
GET /admin/healing
```

View the self-healing system status and recent repairs.

---

## Enhanced API Endpoints

### MCP (Model Context Protocol)

#### Execute Tool

```
POST /mcp/tool
```

Execute an MCP tool by name.

**Request Body:**
```json
{
  "tool_name": "string",
  "arguments": {}
}
```

#### List Tools

```
GET /mcp/tools
```

List all available MCP tools.

#### RPC Call

```
POST /mcp/rpc
```

Execute an MCP JSON-RPC call.

**Request Body:**
```json
{
  "method": "string",
  "params": {}
}
```

#### SSE Stream

```
GET /mcp/sse
```

Server-Sent Events stream for MCP notifications.

---

### Workflow Engine

#### Execute Workflow

```
POST /workflow/execute
```

Execute a workflow from a template with input data.

**Request Body:**
```json
{
  "template_id": "string",
  "input_data": {}
}
```

#### List Templates

```
GET /workflow/templates
```

List available workflow templates.

#### Workflow Status

```
GET /workflow/status/{execution_id}
```

Get the status of a running or completed workflow execution.

---

### Deepmind (Planning & Reasoning)

#### Plan

```
POST /plan
```

Generate a multi-step plan for a given goal.

**Request Body:**
```json
{
  "goal": "string",
  "context": {}
}
```

#### Reason

```
POST /reason
```

Perform causal reasoning over provided facts.

**Request Body:**
```json
{
  "facts": ["string"],
  "query": "string"
}
```

---

### Skills

#### Search Skills

```
POST /skills/search
```

Search the skills registry by capability or keyword.

#### Skills Statistics

```
GET /skills/stats
```

Get skills registry statistics.

#### Detect Skill Bundle

```
POST /skills/detect-bundle
```

Auto-detect applicable skills from natural language input.

---

### Code Generation

#### Generate Code

```
POST /code/generate
```

Generate code from a natural language specification.

**Request Body:**
```json
{
  "specification": "string",
  "language": "python"
}
```

#### Improve Code

```
POST /code/improve
```

Suggest improvements for provided code.

**Request Body:**
```json
{
  "code": "string",
  "focus": ["performance", "readability"]
}
```

#### Explain Code

```
POST /code/explain
```

Generate a natural language explanation of code.

**Request Body:**
```json
{
  "code": "string"
}
```

---

### Self-Healing

#### Healing Dashboard

```
GET /healing/dashboard
```

View the self-healing dashboard with anomaly metrics.

#### Trigger Repair

```
POST /healing/repair
```

Manually trigger a self-repair action.

**Request Body:**
```json
{
  "target": "string",
  "action": "restart"
}
```

#### List Healing Bots

```
GET /healing/bots
```

List active nanocode healing bots and their status.

---

### Evolution

#### Evolution Statistics

```
GET /evolution/stats
```

View self-evolution statistics and recent adaptations.

#### Submit Feedback

```
POST /evolution/feedback
```

Submit feedback to the self-evolution engine.

**Request Body:**
```json
{
  "metric": "string",
  "value": 0.95,
  "context": {}
}
```

---

### Personality

#### List Personalities

```
GET /personality/list
```

List all available AI personality profiles.

#### Get Personality Vector

```
POST /personality/vector
```

Get the embedding vector for a personality profile.

#### Spawn Personality

```
POST /personality/spawn
```

Create a new AI personality instance.

**Request Body:**
```json
{
  "name": "string",
  "traits": ["friendly", "analytical"],
  "base_model": "tranc3-default"
}
```

---

## Error Responses

All endpoints may return the following error responses:

| Status Code | Description |
|-------------|-------------|
| 400 | Bad Request — Invalid input parameters |
| 401 | Unauthorized — Missing or invalid authentication token |
| 403 | Forbidden — Insufficient permissions |
| 404 | Not Found — Resource or endpoint not found |
| 429 | Too Many Requests — Rate limit exceeded |
| 500 | Internal Server Error — Unexpected server error |
| 503 | Service Unavailable — System not ready |

## Rate Limiting

API requests are rate-limited per user. Default limits:

| Tier | Requests/Minute | Requests/Day |
|------|-----------------|--------------|
| Free | 60 | 10,000 |
| Pro | 300 | 100,000 |
| Enterprise | Custom | Custom |

Rate limit headers are included in all responses:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1716480000
```

---

## Universal ID Taxonomy

All platform entities use a hierarchical ID system:

| ID Type | Format | Example | Description |
|---------|--------|---------|-------------|
| PID | `PID-XXX` | `PID-INF` | Product/Location ID |
| AID | `AID-XXX-NN` | `AID-INF-01` | AI Entity ID |
| SID | `SID-XXX-NN` | `SID-INF-01` | Service/Agent ID |
| NID | `NID-XXX-NN` | `NID-INF-01` | Nano-ID/Bot ID |

---

*Auto-generated from the Tranc3 codebase. Last updated: 2026-05-23*
