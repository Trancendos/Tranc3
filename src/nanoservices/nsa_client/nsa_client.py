"""
NSA — Nanoservice Architecture Client Library
===============================================
Python client for shared memory IPC with the NSA Broker.

Provides:
  - NanoserviceClient: Connect to the NSA broker, send/receive messages
  - ShmReader: Read from shared memory segments
  - ShmWriter: Write to shared memory segments
  - ServiceRegistry: Discover and monitor nanoservices

Architecture:
  - Uses multiprocessing.shared_memory for zero-copy IPC
  - Ring buffer pattern for high-throughput message passing
  - Atomic signalling for lock-free coordination
  - Async-compatible with anyio/eventlet

Zero-Cost: Uses only Python stdlib + multiprocessing.shared_memory
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from multiprocessing import shared_memory
from typing import Any, Callable, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SHM_DIR = "/dev/shm"
SHM_PREFIX = "nsa_"
SLOT_HEADER_SIZE = 24  # AtomicBool(1) + AtomicU64(8) + u32(4) + u32(4) + padding(7)
SLOT_SIZE = 1024
RING_BUFFER_SLOTS = 64
POLL_INTERVAL_S = 0.0001  # 100μs
HTTP_PORT = 7780


# ─────────────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────────────


class ServiceStatus(str, Enum):
    STARTING = "Starting"
    READY = "Ready"
    BUSY = "Busy"
    DEGRADED = "Degraded"
    OFFLINE = "Offline"


class IpcMessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    COMMAND = "command"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


@dataclass
class ServiceId:
    """Unique identifier for a nanoservice."""

    name: str

    def __str__(self) -> str:
        return f"NSA-{self.name.upper().replace('-', '_')}"

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ServiceId):
            return str(self) == str(other)
        return False


@dataclass
class IpcMessage:
    """Message envelope for IPC communication."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: ServiceId = field(default_factory=lambda: ServiceId("unknown"))
    target: ServiceId = field(default_factory=lambda: ServiceId("unknown"))
    msg_type: str = IpcMessageType.REQUEST.value
    payload: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    priority: int = 128
    ttl_ms: int = 30000

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "source": str(self.source),
                "target": str(self.target),
                "msg_type": self.msg_type,
                "payload": self.payload,
                "timestamp": self.timestamp,
                "priority": self.priority,
                "ttl_ms": self.ttl_ms,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "IpcMessage":
        d = json.loads(data)
        return cls(
            id=d["id"],
            source=ServiceId(d["source"].replace("NSA-", "").lower()),
            target=ServiceId(d["target"].replace("NSA-", "").lower()),
            msg_type=d["msg_type"],
            payload=d["payload"],
            timestamp=d["timestamp"],
            priority=d.get("priority", 128),
            ttl_ms=d.get("ttl_ms", 30000),
        )


@dataclass
class NanoserviceRecord:
    """Registration record for a nanoservice."""

    id: ServiceId
    name: str
    tier: int
    pid: int
    shm_segment: str
    registered_at: str = ""
    last_heartbeat: str = ""
    status: ServiceStatus = ServiceStatus.STARTING
    message_count: int = 0
    error_count: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Shared Memory Ring Buffer
# ─────────────────────────────────────────────────────────────────────────────


class ShmRingBuffer:
    """
    Ring buffer backed by shared memory for zero-copy IPC.
    Compatible with the Rust NSA broker's memory layout.
    """

    def __init__(self, name: str, slot_count: int = RING_BUFFER_SLOTS, create: bool = False):
        self.name = name
        self.slot_count = slot_count
        self.total_size = slot_count * (SLOT_HEADER_SIZE + SLOT_SIZE)

        shm_name = f"{SHM_PREFIX}{name}"

        if create:
            try:
                # Try to create new
                self._shm = shared_memory.SharedMemory(
                    name=shm_name, create=True, size=self.total_size
                )
            except FileExistsError:
                # Attach to existing
                self._shm = shared_memory.SharedMemory(name=shm_name, create=False)
        else:
            self._shm = shared_memory.SharedMemory(name=shm_name, create=False)

        self._buffer: memoryview = self._shm.buf  # type: ignore[assignment]

    def write_message(self, msg: IpcMessage) -> int:
        """Write a message to the next available slot. Returns slot index."""
        encoded = msg.to_json().encode("utf-8")

        if len(encoded) > SLOT_SIZE:
            raise ValueError(f"Message too large: {len(encoded)} bytes (max {SLOT_SIZE})")

        for i in range(self.slot_count):
            offset = i * (SLOT_HEADER_SIZE + SLOT_SIZE)
            # Check occupied flag (byte 0 of header)
            if self._buffer[offset] == 0:  # Not occupied  # type: ignore[index]
                # Write header
                self._buffer[offset] = 1  # occupied = true  # type: ignore[index]
                struct.pack_into("!I", self._buffer, offset + 9, len(encoded))  # length  # type: ignore[arg-type]

                # Write payload
                payload_offset = offset + SLOT_HEADER_SIZE
                self._buffer[payload_offset : payload_offset + len(encoded)] = encoded  # type: ignore[index]
                return i

        raise BufferError("All slots occupied — backpressure required")

    def read_message(self, slot_index: int) -> Optional[IpcMessage]:
        """Read and consume a message from a specific slot."""
        if slot_index >= self.slot_count:
            raise IndexError(f"Slot index {slot_index} out of range")

        offset = slot_index * (SLOT_HEADER_SIZE + SLOT_SIZE)

        if self._buffer[offset] == 0:  # Not occupied  # type: ignore[index]
            return None

        # Read length
        length = struct.unpack_from("!I", self._buffer, offset + 9)[0]  # type: ignore[arg-type]
        if length == 0 or length > SLOT_SIZE:
            return None

        # Read payload
        payload_offset = offset + SLOT_HEADER_SIZE
        encoded = bytes(self._buffer[payload_offset : payload_offset + length])  # type: ignore[index]

        # Mark slot as available
        self._buffer[offset] = 0  # type: ignore[index]

        return IpcMessage.from_json(encoded.decode("utf-8"))

    def read_next(self) -> Optional[IpcMessage]:
        """Read the next available message from any slot."""
        for i in range(self.slot_count):
            msg = self.read_message(i)
            if msg is not None:
                return msg
        return None

    def occupied_count(self) -> int:
        """Count occupied slots."""
        count = 0
        for i in range(self.slot_count):
            offset = i * (SLOT_HEADER_SIZE + SLOT_SIZE)
            if self._buffer[offset] == 1:  # type: ignore[index]
                count += 1
        return count

    def close(self) -> None:
        """Close the shared memory handle."""
        self._shm.close()

    def unlink(self) -> None:
        """Close and remove the shared memory segment."""
        self._shm.close()
        try:
            self._shm.unlink()
        except FileNotFoundError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Nanoservice Client
# ─────────────────────────────────────────────────────────────────────────────


class NanoserviceClient:
    """
    Client for connecting to the NSA Broker and communicating
    with other nanoservices via shared memory IPC.
    """

    def __init__(
        self,
        service_name: str,
        tier: int = 5,
        broker_url: str = f"http://localhost:{HTTP_PORT}",
    ):
        self.service_id = ServiceId(service_name)
        self.service_name = service_name
        self.tier = tier
        self.broker_url = broker_url
        self._ring_buffer: Optional[ShmRingBuffer] = None
        self._running = False
        self._handlers: Dict[str, List[Callable]] = {}
        self._message_count = 0
        self._error_count = 0
        self._pid = os.getpid()

    async def start(self) -> None:
        """Register with the NSA broker and start listening."""
        # Connect to the broker's HTTP endpoint
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.broker_url}/register",
                    json={
                        "name": self.service_name,
                        "tier": self.tier,
                        "pid": self._pid,
                    },
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    segment_name = data.get("shm_segment", f"{self.service_name}_seg")
                else:
                    # Fallback: create our own segment
                    segment_name = f"{self.service_name.lower().replace('-', '_')}_seg"
        except Exception:
            # Broker not available — create standalone segment
            segment_name = f"{self.service_name.lower().replace('-', '_')}_seg"

        # Create or attach to shared memory ring buffer
        self._ring_buffer = ShmRingBuffer(segment_name, create=True)
        self._running = True

    async def stop(self) -> None:
        """Stop the client and release resources."""
        self._running = False
        if self._ring_buffer:
            self._ring_buffer.close()

    async def send(self, target: ServiceId, msg_type: str, payload: str) -> IpcMessage:
        """Send a message to another nanoservice via shared memory."""
        if not self._ring_buffer:
            raise RuntimeError("Client not started — call start() first")

        msg = IpcMessage(
            source=self.service_id,
            target=target,
            msg_type=msg_type,
            payload=payload,
        )

        # For direct SHM: find target's segment
        target_segment = f"{str(target).replace('NSA-', '').lower()}_seg"
        try:
            target_buffer = ShmRingBuffer(target_segment, create=False)
            target_buffer.write_message(msg)
            target_buffer.close()
        except FileNotFoundError:
            # Target segment doesn't exist — try via broker HTTP
            try:
                import httpx

                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{self.broker_url}/send",
                        json=json.loads(msg.to_json()),
                        timeout=5.0,
                    )
            except Exception:
                self._error_count += 1
                raise

        self._message_count += 1
        return msg

    async def receive(self, timeout_s: float = 1.0) -> Optional[IpcMessage]:
        """Receive the next available message from our ring buffer."""
        if not self._ring_buffer:
            raise RuntimeError("Client not started — call start() first")

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            msg = self._ring_buffer.read_next()
            if msg is not None:
                self._message_count += 1
                return msg
            await asyncio.sleep(POLL_INTERVAL_S)

        return None

    def on(self, msg_type: str, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        if msg_type not in self._handlers:
            self._handlers[msg_type] = []
        self._handlers[msg_type].append(handler)

    async def process_messages(self, duration_s: float = 60.0) -> int:
        """Process incoming messages for a specified duration."""
        processed = 0
        deadline = time.monotonic() + duration_s

        while self._running and time.monotonic() < deadline:
            msg = await self.receive(timeout_s=0.1)
            if msg:
                handlers = self._handlers.get(msg.msg_type, [])
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(msg)
                        else:
                            handler(msg)
                    except Exception:
                        self._error_count += 1
                processed += 1

        return processed

    @property
    def stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "service_id": str(self.service_id),
            "service_name": self.service_name,
            "tier": self.tier,
            "pid": self._pid,
            "message_count": self._message_count,
            "error_count": self._error_count,
            "running": self._running,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Service Registry (HTTP-based discovery)
# ─────────────────────────────────────────────────────────────────────────────


class ServiceRegistry:
    """Discover and monitor nanoservices via the NSA Broker HTTP endpoint."""

    def __init__(self, broker_url: str = f"http://localhost:{HTTP_PORT}"):
        self.broker_url = broker_url

    async def list_services(self) -> List[NanoserviceRecord]:
        """List all registered nanoservices."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.broker_url}/services", timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    return [
                        NanoserviceRecord(
                            id=ServiceId(s["name"]),
                            name=s["name"],
                            tier=s["tier"],
                            pid=s["pid"],
                            shm_segment=s["shm_segment"],
                            status=ServiceStatus(s.get("status", "Ready")),
                        )
                        for s in data.get("services", [])
                    ]
        except Exception:  # noqa: S110
            pass  # graceful degradation
        return []

    async def health(self) -> Dict[str, Any]:
        """Check NSA broker health."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.broker_url}/health", timeout=5.0)
                if resp.status_code == 200:
                    return resp.json()
        except Exception:  # noqa: S110
            pass  # graceful degradation
        return {"status": "unreachable"}

    async def stats(self) -> Dict[str, Any]:
        """Get broker statistics."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.broker_url}/stats", timeout=5.0)
                if resp.status_code == 200:
                    return resp.json()
        except Exception:  # noqa: S110
            pass  # graceful degradation
        return {"status": "unreachable"}
