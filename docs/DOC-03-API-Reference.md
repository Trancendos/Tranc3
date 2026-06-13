# TRANC3 API Reference
**Version:** 2.0.0 | **Base URL:** https://api.tranc3.ai/v2

---

## Authentication
All endpoints require JWT Bearer token:
```
Authorization: Bearer <token>
```

## Rate Limits
| Tier | Limit |
|------|-------|
| Free | 100 req/hour |
| Pro | 1,000 req/hour |
| Enterprise | Unlimited |

---

## Endpoints

### POST /chat
Main inference endpoint.

**Request:**
```json
{
  "message": "Hello TRANC3",
  "language": "en",
  "personality": "tranc3-base",
  "user_emotion": "neutral",
  "user_id": "user_123",
  "conversation_history": [
    {"role": "user", "content": "previous message"},
    {"role": "assistant", "content": "previous response"}
  ],
  "options": {
    "enable_quantum": true,
    "enable_consciousness": true,
    "max_tokens": 150,
    "temperature": 0.8,
    "top_p": 0.9
  }
}
```

**Response:**
```json
{
  "response": "Hello! I am TRANC3...",
  "detected_emotion": "neutral",
  "language": "en",
  "personality": "tranc3-base",
  "timestamp": "2026-04-20T03:30:00Z",
  "processing_time_ms": 245.3,
  "request_id": "a1b2c3d4e5f6",
  "advanced_metrics": {
    "quantum_used": true,
    "consciousness_level": 2.4,
    "swarm_participation": false,
    "evolution_applied": true
  }
}
```

---

### GET /health
Health check.

**Response:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2026-04-20T03:30:00Z",
  "components": {
    "api": "healthy",
    "redis": "healthy",
    "model": "healthy",
    "tokenizer": "healthy",
    "quantum": "healthy",
    "consciousness": "healthy"
  },
  "uptime_seconds": 86400
}
```

---

### GET /ready
Kubernetes readiness probe.

**Response 200:**
```json
{ "ready": true }
```

**Response 503:**
```json
{ "detail": "Service not ready" }
```

---

### GET /metrics
Prometheus metrics (text/plain).

---

### GET /languages
List supported languages.

**Response:**
```json
{
  "languages": ["en","es","fr","de","zh","ja","ko","ar","ru","pt"],
  "primary": "en",
  "total": 50
}
```

---

### GET /personalities
List available personalities.

**Response:**
```json
{
  "personalities": [
    "tranc3-base",
    "tranc3-multilingual",
    "tranc3-creative",
    "tranc3-analytical",
    "tranc3-empathetic"
  ]
}
```

---

### GET /features
Get feature flag status.

**Response:**
```json
{
  "quantum_optimization": { "enabled": true, "rollout_percentage": 50 },
  "consciousness_engine": { "enabled": true, "rollout_percentage": 25 },
  "neuromorphic_processing": { "enabled": false, "rollout_percentage": 0 },
  "holographic_memory": { "enabled": false, "rollout_percentage": 0 },
  "self_evolution": { "enabled": true, "rollout_percentage": 10 },
  "swarm_intelligence": { "enabled": false, "rollout_percentage": 0 }
}
```

---

### POST /feedback
Submit user feedback for self-evolution.

**Request:**
```json
{
  "request_id": "a1b2c3d4e5f6",
  "rating": 5,
  "comments": "Excellent response!",
  "categories": ["accuracy", "creativity"]
}
```

**Response:**
```json
{ "message": "Feedback recorded", "impact": "evolution_queued" }
```

---

### POST /auth/token
Get JWT token.

**Request:**
```json
{
  "username": "user@example.com",
  "password": "<your-secure-password>"
}
```

**Response:**
```json
{
  "access_token": "<your-jwt-access-token>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Validation Error |
| 429 | Rate Limited |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

---

## WebSocket API

### WS /ws/chat
Real-time streaming chat.

**Connect:**
```javascript
const ws = new WebSocket('wss://api.tranc3.ai/v2/ws/chat?token=<jwt>');
```

**Send:**
```json
{ "message": "Hello", "language": "en" }
```

**Receive (streaming):**
```json
{ "chunk": "Hello", "done": false }
{ "chunk": "! I am", "done": false }
{ "chunk": " TRANC3.", "done": true, "metadata": {...} }
```