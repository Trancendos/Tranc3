"""
MCP Server — JSON-RPC 2.0 over HTTP and Server-Sent Events.

Mount the exported `router` onto the main FastAPI application::

    from src.mcp.server import router as mcp_router
    app.include_router(mcp_router)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .tools import registry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON-RPC constants
# ---------------------------------------------------------------------------

JSONRPC_VERSION = "2.0"
SERVER_NAME = "tranc3-mcp-server"
SERVER_VERSION = "1.0.0"

# Standard JSON-RPC error codes
ERR_PARSE_ERROR = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL_ERROR = -32603

# MCP-specific error codes (application range: -32000 to -32099)
ERR_TOOL_NOT_FOUND = -32001
ERR_TOOL_EXECUTION = -32002
ERR_RESOURCE_NOT_FOUND = -32003

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class MCPError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class MCPRequest(BaseModel):
    jsonrpc: str = Field(default=JSONRPC_VERSION)
    id: Optional[Any] = None          # str | int | None
    method: str
    params: Optional[Dict[str, Any]] = None


class MCPResponse(BaseModel):
    jsonrpc: str = Field(default=JSONRPC_VERSION)
    id: Optional[Any] = None
    result: Optional[Any] = None
    error: Optional[MCPError] = None

    class Config:
        # Exclude None fields so we never send both result and error
        json_encoders = {}


# ---------------------------------------------------------------------------
# SSE event bus (in-process pub/sub)
# ---------------------------------------------------------------------------

class _SSEBus:
    """Minimal in-process pub/sub for SSE subscribers."""

    def __init__(self) -> None:
        self._queues: Dict[str, asyncio.Queue] = {}

    def subscribe(self) -> tuple[str, asyncio.Queue]:
        sub_id = str(uuid.uuid4())
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._queues[sub_id] = q
        return sub_id, q

    def unsubscribe(self, sub_id: str) -> None:
        self._queues.pop(sub_id, None)

    async def publish(self, event_type: str, data: Any) -> None:
        payload = json.dumps({"event": event_type, "data": data, "ts": time.time()})
        dead = []
        for sub_id, q in list(self._queues.items()):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("mcp.sse queue full for subscriber=%s, dropping event", sub_id)
            except Exception:
                dead.append(sub_id)
        for sub_id in dead:
            self.unsubscribe(sub_id)


_bus = _SSEBus()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _ok(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


# ---------------------------------------------------------------------------
# JSON-RPC method handlers
# ---------------------------------------------------------------------------


async def _method_initialize(params: Optional[Dict[str, Any]], request_id: Any) -> Dict[str, Any]:
    client_info = (params or {}).get("clientInfo", {})
    logger.info(
        "mcp.initialize client=%s version=%s",
        client_info.get("name", "unknown"),
        client_info.get("version", "unknown"),
    )
    return _ok(
        request_id,
        {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"listChanged": True},
                "logging": {},
                "experimental": {
                    "sse": True,
                    "batchRequests": False,
                },
            },
        },
    )


async def _method_tools_list(params: Optional[Dict[str, Any]], request_id: Any) -> Dict[str, Any]:
    tools = registry.list_tools()
    return _ok(request_id, {"tools": tools})


async def _method_tools_call(params: Optional[Dict[str, Any]], request_id: Any) -> Dict[str, Any]:
    if not params:
        return _err(request_id, ERR_INVALID_PARAMS, "params required for tools/call")

    tool_name: str = params.get("name", "")
    tool_params: Dict[str, Any] = params.get("arguments", params.get("params", {}))

    tool = registry.get(tool_name)
    if tool is None:
        return _err(
            request_id,
            ERR_TOOL_NOT_FOUND,
            f"Tool '{tool_name}' not found",
            {"available_tools": [t["name"] for t in registry.list_tools()]},
        )

    try:
        start = time.monotonic()
        result = await asyncio.wait_for(tool.handler(tool_params), timeout=60.0)
        elapsed_ms = (time.monotonic() - start) * 1000

        await _bus.publish(
            "tool_result",
            {
                "tool": tool_name,
                "request_id": request_id,
                "elapsed_ms": round(elapsed_ms, 2),
                "result": result,
            },
        )

        return _ok(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(result)}],
                "isError": False,
                "_meta": {"elapsed_ms": round(elapsed_ms, 2)},
            },
        )
    except asyncio.TimeoutError:
        msg = f"Tool '{tool_name}' timed out after 60 s"
        logger.error("mcp.tools_call timeout tool=%s", tool_name)
        await _bus.publish("error", {"tool": tool_name, "error": msg, "request_id": request_id})
        return _err(request_id, ERR_TOOL_EXECUTION, msg)
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        logger.exception("mcp.tools_call error tool=%s", tool_name)
        await _bus.publish("error", {"tool": tool_name, "error": msg, "request_id": request_id})
        return _err(request_id, ERR_TOOL_EXECUTION, f"Tool execution failed: {msg}")


async def _method_resources_list(
    params: Optional[Dict[str, Any]], request_id: Any
) -> Dict[str, Any]:
    resources: List[Dict[str, Any]] = [
        {
            "uri": "tranc3://skills",
            "name": "Skill Library",
            "description": "All registered Tranc3 skills with metadata",
            "mimeType": "application/json",
        },
        {
            "uri": "tranc3://workflows",
            "name": "Workflow Registry",
            "description": "All defined Tranc3 workflows",
            "mimeType": "application/json",
        },
        {
            "uri": "tranc3://health",
            "name": "System Health",
            "description": "Real-time system health snapshot",
            "mimeType": "application/json",
        },
        {
            "uri": "tranc3://evolution",
            "name": "Evolution Stats",
            "description": "Model and skill evolutionary statistics",
            "mimeType": "application/json",
        },
    ]
    return _ok(request_id, {"resources": resources})


async def _method_ping(params: Optional[Dict[str, Any]], request_id: Any) -> Dict[str, Any]:
    return _ok(request_id, {"pong": True, "ts": time.time(), "server": SERVER_NAME})


# Dispatch table: method name → handler
_METHOD_DISPATCH: Dict[str, Any] = {
    "initialize": _method_initialize,
    "tools/list": _method_tools_list,
    "tools/call": _method_tools_call,
    "resources/list": _method_resources_list,
    "ping": _method_ping,
}


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.post("/rpc")
async def rpc_endpoint(request: Request) -> JSONResponse:
    """
    JSON-RPC 2.0 entry-point.  Accepts a single request object or a batch array.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            content=_err(None, ERR_PARSE_ERROR, "Parse error: request body is not valid JSON"),
            status_code=200,
        )

    # Batch not supported — detect and reject gracefully
    if isinstance(body, list):
        return JSONResponse(
            content=_err(
                None, ERR_INVALID_REQUEST, "Batch requests are not supported by this server"
            ),
            status_code=200,
        )

    if not isinstance(body, dict):
        return JSONResponse(
            content=_err(None, ERR_INVALID_REQUEST, "Request must be a JSON object"),
            status_code=200,
        )

    # Validate basic JSON-RPC structure
    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params")

    if body.get("jsonrpc") != JSONRPC_VERSION:
        return JSONResponse(
            content=_err(req_id, ERR_INVALID_REQUEST, "jsonrpc must be '2.0'"),
            status_code=200,
        )
    if not method or not isinstance(method, str):
        return JSONResponse(
            content=_err(req_id, ERR_INVALID_REQUEST, "method must be a non-empty string"),
            status_code=200,
        )

    handler = _METHOD_DISPATCH.get(method)
    if handler is None:
        return JSONResponse(
            content=_err(req_id, ERR_METHOD_NOT_FOUND, f"Method '{method}' not found"),
            status_code=200,
        )

    try:
        result = await handler(params, req_id)
        return JSONResponse(content=result, status_code=200)
    except Exception as exc:
        logger.exception("mcp.rpc unhandled error method=%s", method)
        return JSONResponse(
            content=_err(req_id, ERR_INTERNAL_ERROR, f"Internal error: {type(exc).__name__}"),
            status_code=200,
        )


@router.get("/sse")
async def sse_endpoint(request: Request) -> StreamingResponse:
    """
    Server-Sent Events stream.  Clients connect here to receive async events
    (tool_result, progress, error) pushed from the MCP server.
    """
    sub_id, queue = _bus.subscribe()
    logger.info("mcp.sse client connected sub_id=%s", sub_id)

    async def _event_generator() -> AsyncGenerator[str, None]:
        # Greeting
        yield f"event: connected\ndata: {json.dumps({'sub_id': sub_id, 'server': SERVER_NAME})}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat
                    yield f": heartbeat {time.time()}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _bus.unsubscribe(sub_id)
            logger.info("mcp.sse client disconnected sub_id=%s", sub_id)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/tools")
async def list_tools_endpoint() -> JSONResponse:
    """Return all registered MCP tools in JSON-schema format."""
    tools = registry.list_tools()
    return JSONResponse(
        content={
            "tools": tools,
            "count": len(tools),
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
        }
    )


@router.get("/health")
async def health_endpoint() -> JSONResponse:
    """MCP server health check."""
    tool_count = len(registry.list_tools())
    subscriber_count = len(_bus._queues)
    return JSONResponse(
        content={
            "status": "ok",
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "tools_registered": tool_count,
            "sse_subscribers": subscriber_count,
            "ts": time.time(),
        }
    )


# ---------------------------------------------------------------------------
# Publish helper — usable from other parts of the codebase
# ---------------------------------------------------------------------------


async def publish_event(event_type: str, data: Any) -> None:
    """Push an event to all active SSE subscribers."""
    await _bus.publish(event_type, data)


# ---------------------------------------------------------------------------
# Standalone handle_rpc — callable from api_enhanced.py
# ---------------------------------------------------------------------------

async def handle_rpc(body: Dict[str, Any], enhanced: Any = None) -> Dict[str, Any]:
    """
    Process a raw JSON-RPC 2.0 request dict and return a response dict.
    Usable outside the FastAPI router context.
    """
    rpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params") or {}

    try:
        request_obj = MCPRequest(
            jsonrpc=body.get("jsonrpc", "2.0"),
            id=rpc_id,
            method=method,
            params=params,
        )
    except Exception as e:
        return _err(rpc_id, PARSE_ERROR, f"Invalid request: {e}")

    result = await _dispatch(request_obj)
    return MCPResponse(jsonrpc="2.0", id=rpc_id, result=result).model_dump()
