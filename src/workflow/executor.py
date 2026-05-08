"""Async workflow execution engine with topological scheduling and event bus."""

from typing import Dict, Any, Optional, List, Callable, Set
import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field

from .builder import WorkflowDefinition
from .nodes import NodeConfig, NodeResult, create_node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Execution state
# ---------------------------------------------------------------------------

@dataclass
class ExecutionState:
    """Mutable state tracked for a single workflow run."""

    execution_id: str
    workflow_id: str
    status: str = "pending"                                  # pending | running | completed | failed | cancelled
    node_outputs: Dict[str, Any] = field(default_factory=dict)
    node_statuses: Dict[str, str] = field(default_factory=dict)  # node_id -> pending|running|completed|failed|skipped
    started_at: float = field(default_factory=time.monotonic)
    finished_at: Optional[float] = None
    error: Optional[str] = None

    @property
    def elapsed_ms(self) -> float:
        end = self.finished_at or time.monotonic()
        return (end - self.started_at) * 1000


# ---------------------------------------------------------------------------
# Workflow event bus
# ---------------------------------------------------------------------------

class WorkflowEventBus:
    """
    Simple async pub/sub event bus for workflow lifecycle events.

    Supported events:
        workflow.started, workflow.completed, workflow.failed,
        node.started, node.completed, node.failed
    """

    def __init__(self) -> None:
        # event_name -> list of async or sync callables
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def subscribe(self, event: str, callback: Callable) -> None:
        """Register a callback for a named event. Wildcards (*) match all events."""
        self._subscribers[event].append(callback)
        logger.debug("Subscribed to event '%s': %s", event, callback)

    def unsubscribe(self, event: str, callback: Callable) -> bool:
        """Remove a previously registered callback. Returns True if found."""
        listeners = self._subscribers.get(event, [])
        try:
            listeners.remove(callback)
            return True
        except ValueError:
            return False

    async def publish(self, event: str, data: Any = None) -> None:
        """
        Dispatch an event to all matching subscribers.

        Wildcard subscribers (registered under "*") receive every event.
        Callbacks are run concurrently; individual failures are logged, not raised.
        """
        targets = list(self._subscribers.get(event, []))
        targets += list(self._subscribers.get("*", []))
        if not targets:
            return

        async def _call(cb: Callable) -> None:
            try:
                payload = {"event": event, "data": data}
                if asyncio.iscoroutinefunction(cb):
                    await cb(payload)
                else:
                    cb(payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Event handler error for '%s': %s", event, exc)

        await asyncio.gather(*[_call(cb) for cb in targets], return_exceptions=True)


# ---------------------------------------------------------------------------
# Topological scheduling helpers
# ---------------------------------------------------------------------------

def _build_adjacency(
    nodes: Dict[str, NodeConfig],
    edges: List[tuple],
) -> tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """
    Return (successors, predecessors) adjacency maps.
    edges is a list of (from_id, to_id, label).
    """
    succ: Dict[str, List[str]] = {nid: [] for nid in nodes}
    pred: Dict[str, List[str]] = {nid: [] for nid in nodes}
    for from_id, to_id, _ in edges:
        if from_id in succ and to_id in pred:
            succ[from_id].append(to_id)
            pred[to_id].append(from_id)
    return succ, pred


def _topological_sort(
    nodes: Dict[str, NodeConfig],
    edges: List[tuple],
) -> List[List[str]]:
    """
    Kahn's BFS-based topological sort, returning *layers*.

    Each layer is a list of node_ids that can run concurrently
    (all their predecessors completed in previous layers).
    """
    succ, pred = _build_adjacency(nodes, edges)
    in_degree: Dict[str, int] = {nid: len(pred[nid]) for nid in nodes}

    queue: deque = deque([nid for nid, deg in in_degree.items() if deg == 0])
    layers: List[List[str]] = []

    while queue:
        # Drain the whole current-layer queue in one batch
        layer = []
        next_queue: deque = deque()
        while queue:
            nid = queue.popleft()
            layer.append(nid)
            for child in succ[nid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    next_queue.append(child)
        layers.append(layer)
        queue = next_queue

    total_sorted = sum(len(l) for l in layers)
    if total_sorted != len(nodes):
        raise ValueError(
            f"Workflow contains a cycle or disconnected subgraph: "
            f"sorted {total_sorted} of {len(nodes)} nodes."
        )

    return layers


def _gather_inputs(
    node_id: str,
    edges: List[tuple],
    node_outputs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Collect the outputs of all upstream nodes as inputs for node_id.

    If a single upstream node produced the output, we merge its dict directly.
    Multiple upstream nodes are stored under their node_id key.
    """
    upstream_ids = [from_id for from_id, to_id, _ in edges if to_id == node_id]
    if not upstream_ids:
        return {}

    if len(upstream_ids) == 1:
        out = node_outputs.get(upstream_ids[0], {})
        # If the upstream output is a dict, spread it; otherwise wrap it
        if isinstance(out, dict):
            return dict(out)
        return {"input": out}

    # Multiple upstream nodes
    merged: Dict[str, Any] = {}
    for uid in upstream_ids:
        out = node_outputs.get(uid, {})
        if isinstance(out, dict):
            # Merge into the flat namespace; later nodes override earlier ones
            merged.update(out)
        merged[uid] = out  # also keep under the node_id key for explicit access
    return merged


# ---------------------------------------------------------------------------
# Workflow executor
# ---------------------------------------------------------------------------

class WorkflowExecutor:
    """
    Async engine that executes a WorkflowDefinition against live node implementations.

    Features:
    - Topological (BFS-layered) execution order.
    - Parallel execution within each layer via asyncio.gather.
    - Per-node timeout and retry (delegated to BaseNode).
    - Live ExecutionState tracking.
    - Cancellation support.
    - Publishes lifecycle events to the shared event_bus.
    """

    def __init__(self) -> None:
        self.executions: Dict[str, ExecutionState] = {}
        self._cancel_flags: Dict[str, asyncio.Event] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        workflow: WorkflowDefinition,
        initial_inputs: Dict[str, Any] = None,  # type: ignore[assignment]
        context: Dict[str, Any] = None,          # type: ignore[assignment]
    ) -> ExecutionState:
        """
        Execute a workflow and return the final ExecutionState.

        initial_inputs are injected into the first (root) nodes.
        context is passed through to every node's execute() call.
        """
        if initial_inputs is None:
            initial_inputs = {}
        if context is None:
            context = {}

        execution_id = str(uuid.uuid4())
        cancel_flag = asyncio.Event()
        self._cancel_flags[execution_id] = cancel_flag

        state = ExecutionState(
            execution_id=execution_id,
            workflow_id=workflow.id,
            status="running",
            started_at=time.monotonic(),
        )
        self.executions[execution_id] = state

        await event_bus.publish("workflow.started", {
            "execution_id": execution_id,
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
        })

        logger.info(
            "Starting workflow '%s' (execution %s)", workflow.name, execution_id
        )

        try:
            layers = _topological_sort(workflow.nodes, workflow.edges)
        except ValueError as exc:
            state.status = "failed"
            state.error = str(exc)
            state.finished_at = time.monotonic()
            await event_bus.publish("workflow.failed", {
                "execution_id": execution_id,
                "error": state.error,
            })
            logger.error("Topological sort failed: %s", exc)
            return state

        # Seed initial outputs — root nodes will use initial_inputs
        node_outputs: Dict[str, Any] = {}

        try:
            for layer in layers:
                if cancel_flag.is_set():
                    state.status = "cancelled"
                    state.finished_at = time.monotonic()
                    logger.info("Execution %s cancelled.", execution_id)
                    return state

                await self._execute_layer(
                    layer=layer,
                    workflow=workflow,
                    node_outputs=node_outputs,
                    initial_inputs=initial_inputs,
                    context={**context, "execution_id": execution_id, "workflow_id": workflow.id},
                    state=state,
                    cancel_flag=cancel_flag,
                )

                # Stop on first node failure (fail-fast)
                if any(
                    state.node_statuses.get(nid) == "failed"
                    for nid in layer
                ):
                    raise RuntimeError(
                        f"Layer {layer} had a node failure; aborting workflow."
                    )

            state.status = "completed"
            state.finished_at = time.monotonic()
            state.node_outputs = node_outputs

            await event_bus.publish("workflow.completed", {
                "execution_id": execution_id,
                "workflow_id": workflow.id,
                "elapsed_ms": state.elapsed_ms,
            })
            logger.info(
                "Workflow '%s' completed in %.1fms.", workflow.name, state.elapsed_ms
            )

        except asyncio.CancelledError:
            state.status = "cancelled"
            state.finished_at = time.monotonic()
            logger.info("Execution %s cancelled via CancelledError.", execution_id)

        except Exception as exc:  # noqa: BLE001
            state.status = "failed"
            state.error = str(exc)
            state.finished_at = time.monotonic()
            state.node_outputs = node_outputs
            await event_bus.publish("workflow.failed", {
                "execution_id": execution_id,
                "error": state.error,
                "elapsed_ms": state.elapsed_ms,
            })
            logger.error(
                "Workflow '%s' failed: %s", workflow.name, exc, exc_info=True
            )

        finally:
            self._cancel_flags.pop(execution_id, None)

        return state

    async def get_status(self, execution_id: str) -> Optional[ExecutionState]:
        """Return the current ExecutionState for the given execution_id, or None."""
        return self.executions.get(execution_id)

    async def cancel(self, execution_id: str) -> bool:
        """
        Signal an in-flight execution to stop after the current node completes.

        Returns True if the cancellation flag was set, False if execution not found.
        """
        flag = self._cancel_flags.get(execution_id)
        if flag is None:
            # Already finished or never started
            state = self.executions.get(execution_id)
            return state is not None and state.status == "running"
        flag.set()
        logger.info("Cancel requested for execution %s.", execution_id)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_layer(
        self,
        layer: List[str],
        workflow: WorkflowDefinition,
        node_outputs: Dict[str, Any],
        initial_inputs: Dict[str, Any],
        context: Dict[str, Any],
        state: ExecutionState,
        cancel_flag: asyncio.Event,
    ) -> None:
        """Execute all nodes in a layer concurrently."""

        async def _run_node(node_id: str) -> None:
            if cancel_flag.is_set():
                state.node_statuses[node_id] = "skipped"
                return

            nc: Optional[NodeConfig] = workflow.nodes.get(node_id)
            if nc is None:
                state.node_statuses[node_id] = "failed"
                logger.error("Node '%s' not found in workflow definition.", node_id)
                return

            # Collect inputs from upstream, fall back to initial_inputs for roots
            upstream = _gather_inputs(node_id, workflow.edges, node_outputs)
            node_inputs = {**initial_inputs, **upstream} if not upstream else upstream
            if not upstream:
                node_inputs = dict(initial_inputs)

            state.node_statuses[node_id] = "running"
            await event_bus.publish("node.started", {
                "node_id": node_id,
                "node_name": nc.name,
                "node_type": nc.type.value,
                "execution_id": context.get("execution_id"),
            })

            try:
                node = create_node(nc)
                result: NodeResult = await node.execute(node_inputs, context)
            except Exception as exc:  # noqa: BLE001
                result = NodeResult(
                    node_id=node_id,
                    success=False,
                    output=None,
                    error=str(exc),
                    duration_ms=0.0,
                )

            if result.success:
                state.node_statuses[node_id] = "completed"
                node_outputs[node_id] = result.output
                await event_bus.publish("node.completed", {
                    "node_id": node_id,
                    "node_name": nc.name,
                    "duration_ms": result.duration_ms,
                    "execution_id": context.get("execution_id"),
                })
                logger.debug(
                    "Node '%s' completed in %.1fms.", node_id, result.duration_ms
                )
            else:
                state.node_statuses[node_id] = "failed"
                node_outputs[node_id] = None
                await event_bus.publish("node.failed", {
                    "node_id": node_id,
                    "node_name": nc.name,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                    "execution_id": context.get("execution_id"),
                })
                logger.warning(
                    "Node '%s' failed: %s", node_id, result.error
                )

        await asyncio.gather(*[_run_node(nid) for nid in layer])

    def _topological_sort(
        self,
        nodes: Dict[str, NodeConfig],
        edges: List[tuple],
    ) -> List[List[str]]:
        """Module-level helper exposed as an instance method for external testing."""
        return _topological_sort(nodes, edges)

    def _gather_inputs(
        self,
        node_id: str,
        edges: List[tuple],
        node_outputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Module-level helper exposed as an instance method for external testing."""
        return _gather_inputs(node_id, edges, node_outputs)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

executor = WorkflowExecutor()
event_bus = WorkflowEventBus()
