"""
MCP Client — async client for calling external MCP servers over HTTP / SSE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from shared_core.error_handlers import safe_error_detail

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JSONRPC_VERSION = "2.0"
DEFAULT_TIMEOUT = 30.0  # seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 0.5  # seconds


# ---------------------------------------------------------------------------
# MCPClient
# ---------------------------------------------------------------------------


class MCPClient:
    """
    Async JSON-RPC 2.0 client for a single MCP server.

    Usage::

        client = MCPClient("http://localhost:8000/mcp", api_key="<your-api-key>")
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("search_skills", {"query": "healing"})
        await client.disconnect()

    Or as an async context manager::

        async with MCPClient("http://localhost:8000/mcp") as client:
            result = await client.call_tool("ping", {})
    """

    def __init__(
        self,
        server_url: str,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

        self._client: Optional[httpx.AsyncClient] = None
        self._initialized: bool = False
        self._server_info: Dict[str, Any] = {}
        self._known_tools: List[Dict[str, Any]] = []
        self._request_counter: int = 0
        self._sse_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the HTTP connection pool and perform the MCP `initialize` handshake."""
        if self._client is not None:
            return

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "tranc3-mcp-client/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._client = httpx.AsyncClient(
            base_url=self.server_url,
            headers=headers,
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            http2=False,  # keep h/1.1 for broad compat; flip when needed
        )

        try:
            response = await self._rpc_raw(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "tranc3-mcp-client", "version": "1.0.0"},
                    "capabilities": {},
                },
            )
            self._server_info = response.get("serverInfo", {})
            self._initialized = True
            logger.info(
                "mcp.client connected server=%s info=%s",
                self.server_url,
                self._server_info,
            )
        except Exception:
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        """Cancel SSE listener and close the HTTP connection pool."""
        if self._sse_task and not self._sse_task.done():
            self._sse_task.cancel()
            try:
                await self._sse_task
            except (asyncio.CancelledError, Exception):
                logger.debug("Graceful degradation: %s", "unknown")  # nosec B110
        self._sse_task = None

        if self._client:
            await self._client.aclose()
            self._client = None

        self._initialized = False
        logger.info("mcp.client disconnected server=%s", self.server_url)

    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Retrieve the tool list from the server and cache it locally."""
        self._ensure_connected()
        result = await self._rpc_raw("tools/list", {})
        self._known_tools = result.get("tools", [])
        return self._known_tools

    async def call_tool(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a named tool with *params* and return the result dict.

        Retries up to `self.max_retries` times with exponential back-off on
        transient network errors or 5xx HTTP responses.  Does NOT retry on
        application-level JSON-RPC errors (error field in response).
        """
        self._ensure_connected()

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = await self._rpc_raw(
                    "tools/call",
                    {"name": name, "arguments": params},
                )
                return result
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    backoff = DEFAULT_BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "mcp.client call_tool retry attempt=%d/%d tool=%s backoff=%.2fs error=%s",
                        attempt,
                        self.max_retries,
                        name,
                        backoff,
                        exc,
                    )
                    await asyncio.sleep(backoff)
            except _MCPRemoteError:
                # Application-level error — do not retry
                raise

        raise MCPClientError(
            f"Tool '{name}' failed after {self.max_retries} attempts"
        ) from last_exc

    async def subscribe_sse(self, callback: Callable[[str, Any], Any]) -> None:
        """
        Connect to the server's SSE endpoint and invoke *callback* for each event.

        *callback* signature::

            async def on_event(event_type: str, data: Any) -> None: ...

        The subscription runs in a background task; call `disconnect()` to stop it.
        """
        self._ensure_connected()

        if self._sse_task and not self._sse_task.done():
            logger.warning("mcp.client SSE already subscribed, ignoring duplicate call")
            return

        self._sse_task = asyncio.create_task(
            self._sse_loop(callback),
            name=f"mcp-sse-{self.server_url}",
        )
        logger.info("mcp.client SSE subscription started server=%s", self.server_url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        if not self._initialized or self._client is None:
            raise MCPClientError(
                "MCPClient is not connected. Call await client.connect() first."
            )

    def _next_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    async def _rpc_raw(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a JSON-RPC request and return the `result` dict.

        Raises:
            _MCPRemoteError: on JSON-RPC error responses.
            httpx.HTTPError: on transport/HTTP failures.
        """
        assert self._client is not None  # guarded by callers  # nosec B101 — assertion for type/class contract checking


        payload = {
            "jsonrpc": JSONRPC_VERSION,
            "id": self._next_id(),
            "method": method,
            "params": params,
        }

        response = await self._client.post("/rpc", json=payload)
        response.raise_for_status()

        body: Dict[str, Any] = response.json()

        if "error" in body and body["error"] is not None:
            err = body["error"]
            raise _MCPRemoteError(
                code=err.get("code", -1),
                message=err.get("message", "Unknown error"),
                data=err.get("data"),
            )

        return body.get("result") or {}

    async def _sse_loop(self, callback: Callable[[str, Any], Any]) -> None:
        """Long-running coroutine that consumes the SSE stream."""  # nosec B101 — assertion for type/class contract checking

        assert self._client is not None  # nosec B101 — contract assertion for SSE stream

        headers = dict(self._client.headers)
        headers["Accept"] = "text/event-stream"

        try:
            async with self._client.stream(
                "GET", "/sse", headers={"Accept": "text/event-stream"}
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        raw = line[len("data: ") :]
                        try:
                            payload = json.loads(raw)
                            event_type = payload.get("event", "message")
                            data = payload.get("data")
                            if asyncio.iscoroutinefunction(callback):
                                await callback(event_type, data)
                            else:
                                callback(event_type, data)
                        except Exception as exc:
                            logger.warning(
                                "mcp.client SSE parse error: %s raw=%r", exc, raw
                            )
        except asyncio.CancelledError:
            logger.debug("mcp.client SSE loop cancelled server=%s", self.server_url)
        except Exception as exc:
            logger.error(
                "mcp.client SSE loop error server=%s error=%s", self.server_url, exc
            )


# ---------------------------------------------------------------------------
# MCPClientPool
# ---------------------------------------------------------------------------


class MCPClientPool:
    """
    Manages a named collection of MCP server connections.

    Usage::

        pool = MCPClientPool()
        pool.add_server("primary", "http://localhost:8000/mcp", api_key="<your-api-key>")
        pool.add_server("secondary", "http://remote-mcp.example.com/mcp")
        await pool.connect_all()

        results = await pool.broadcast_tool("search_skills", {"query": "healing"})
        health = await pool.get_aggregate_health()

        await pool.disconnect_all()
    """

    def __init__(self) -> None:
        self._servers: Dict[str, MCPClient] = {}
        self._server_configs: Dict[str, Dict[str, Any]] = {}
        self._tool_index: Dict[str, List[str]] = {}  # tool_name → [server_names]

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------

    def add_server(
        self,
        name: str,
        url: str,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        """Register a server connection without connecting yet."""
        self._server_configs[name] = {
            "url": url,
            "api_key": api_key,
            "timeout": timeout,
            "max_retries": max_retries,
        }
        logger.debug("mcp.pool added server name=%s url=%s", name, url)

    def remove_server(self, name: str) -> None:
        """Remove a server from the pool (disconnects if connected)."""
        self._server_configs.pop(name, None)
        client = self._servers.pop(name, None)
        if client:
            asyncio.create_task(client.disconnect())

    async def connect_all(self) -> Dict[str, Optional[Exception]]:
        """
        Connect to all registered servers concurrently.
        Returns a dict of {server_name: error_or_None}.
        """
        tasks = {
            name: asyncio.create_task(self._connect_one(name))
            for name in self._server_configs
        }
        results: Dict[str, Optional[Exception]] = {}
        for name, task in tasks.items():
            try:
                await task
                results[name] = None
            except Exception as exc:
                logger.error("mcp.pool connect failed server=%s error=%s", name, exc)
                results[name] = exc
        await self._rebuild_tool_index()
        return results

    async def disconnect_all(self) -> None:
        """Disconnect all active clients."""
        await asyncio.gather(
            *(client.disconnect() for client in self._servers.values()),
            return_exceptions=True,
        )
        self._servers.clear()
        self._tool_index.clear()

    async def connect_server(self, name: str) -> None:
        """Connect a single named server (must have been added via add_server)."""
        if name not in self._server_configs:
            raise MCPClientError(f"Server '{name}' not registered in pool")
        await self._connect_one(name)
        await self._rebuild_tool_index()

    def get_client(self, name: str) -> Optional[MCPClient]:
        """Return a connected MCPClient by name, or None."""
        return self._servers.get(name)

    # ------------------------------------------------------------------
    # Broadcast / aggregate operations
    # ------------------------------------------------------------------

    async def broadcast_tool(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call *name* on every server that advertises it.
        Returns {server_name: result_or_error_dict}.
        """
        target_servers = self._tool_index.get(name, list(self._servers.keys()))

        async def _call(server_name: str) -> tuple[str, Any]:
            client = self._servers.get(server_name)
            if client is None:
                return server_name, {"error": "not connected"}
            try:
                result = await client.call_tool(name, params)
                return server_name, result
            except Exception as exc:
                logger.warning(
                    "mcp.pool broadcast_tool tool=%s server=%s error=%s",
                    name,
                    server_name,
                    exc,
                )
                return server_name, {"error": safe_error_detail(exc, 500)}

        pairs = await asyncio.gather(*(_call(s) for s in target_servers))
        return dict(pairs)

    async def get_aggregate_health(self) -> Dict[str, Any]:
        """
        Ping all servers and return a combined health report.
        """

        async def _ping(
            server_name: str, client: MCPClient
        ) -> tuple[str, Dict[str, Any]]:
            try:
                start = time.monotonic()
                await client.call_tool.__func__(client, "ping", {})  # type: ignore[attr-defined]
                latency_ms = (time.monotonic() - start) * 1000
                return server_name, {
                    "status": "ok",
                    "latency_ms": round(latency_ms, 2),
                    "server_info": client._server_info,
                }
            except Exception as exc:
                return server_name, {"status": "error", "error": safe_error_detail(exc, 500)}

        # Use raw RPC for ping (bypasses call_tool routing)
        async def _ping_rpc(
            server_name: str, client: MCPClient
        ) -> tuple[str, Dict[str, Any]]:
            try:
                start = time.monotonic()
                result = await client._rpc_raw("ping", {})
                latency_ms = (time.monotonic() - start) * 1000
                return server_name, {
                    "status": "ok",
                    "latency_ms": round(latency_ms, 2),
                    "server_info": client._server_info,
                    "result": result,
                }
            except Exception as exc:
                return server_name, {"status": "error", "error": safe_error_detail(exc, 500)}

        if not self._servers:
            return {
                "healthy": False,
                "servers": {},
                "message": "No servers connected",
                "ts": time.time(),
            }

        pairs = await asyncio.gather(
            *(_ping_rpc(n, c) for n, c in self._servers.items()),
            return_exceptions=False,
        )
        server_results: Dict[str, Any] = dict(pairs)  # type: ignore[arg-type]
        all_ok = all(v.get("status") == "ok" for v in server_results.values())

        return {
            "healthy": all_ok,
            "servers": server_results,
            "server_count": len(self._servers),
            "ts": time.time(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _connect_one(self, name: str) -> None:
        config = self._server_configs[name]
        client = MCPClient(
            server_url=config["url"],
            api_key=config.get("api_key"),
            timeout=config.get("timeout", DEFAULT_TIMEOUT),
            max_retries=config.get("max_retries", DEFAULT_MAX_RETRIES),
        )
        await client.connect()
        self._servers[name] = client

    async def _rebuild_tool_index(self) -> None:
        """
        Refresh the tool → [server_names] index by querying each connected server.
        Runs concurrently.
        """
        self._tool_index.clear()

        async def _fetch(server_name: str, client: MCPClient) -> tuple[str, List[str]]:
            try:
                tools = await client.list_tools()
                return server_name, [t["name"] for t in tools]
            except Exception as exc:
                logger.warning(
                    "mcp.pool tool index fetch failed server=%s error=%s",
                    server_name,
                    exc,
                )
                return server_name, []

        pairs = await asyncio.gather(
            *(_fetch(n, c) for n, c in self._servers.items()),
            return_exceptions=False,
        )
        for server_name, tool_names in pairs:  # type: ignore[misc]
            for tool_name in tool_names:
                self._tool_index.setdefault(tool_name, []).append(server_name)

        logger.debug(
            "mcp.pool tool index rebuilt tools=%d servers=%d",
            len(self._tool_index),
            len(self._servers),
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MCPClientError(RuntimeError):
    """Raised by MCPClient for connection or protocol-level errors."""


class _MCPRemoteError(RuntimeError):
    """Internal: raised when the server returns a JSON-RPC error object."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.data = data
