"""
The Digital Grid — 8-Tier Adaptive Workflow Engine
====================================================
Tier 1: Internal Python DAG executor (built-in, always available)
Tier 2: n8n           REST API  — visual workflow builder     (port 5678)
Tier 3: Prefect       REST API  — Python-native orchestration (port 4200)
Tier 4: Temporal      gRPC      — durable workflow execution  (port 7233)
Tier 5: Apache Airflow REST API — battle-tested DAG scheduler (port 8089)
Tier 6: Dagster       GraphQL   — asset-centric orchestration (port 3002)
Tier 7: Luigi         in-process— dependency-graph executor   (in-process)
Tier 8: Offline stub  — deterministic fallback               (always works)

Selection uses ACO-inspired pheromone-trail routing:
  - Each engine starts with equal pheromone weight
  - Success → increase pheromone; failure/timeout → decrease
  - ThresholdGuard per engine: sliding-window hard-stop at N requests/hr
  - FORCE_ENGINE env var overrides selection entirely
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

import config
from models import (
    EngineType,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStatus,
    WorkflowStep,
    EngineStatus,
)
from database import GridDatabase

logger = logging.getLogger("the-grid.service")


# ── Threshold Guard ───────────────────────────────────────────────────────────


class ThresholdGuard:
    """Sliding-window request counter with hard-stop enforcement."""

    def __init__(self, limit: int, window_seconds: int = 3600):
        self._limit = limit
        self._window = window_seconds
        self._timestamps: deque[float] = deque()

    def check(self) -> bool:
        """Return True if request is allowed, False if threshold exceeded."""
        now = time.monotonic()
        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self._limit:
            return False
        self._timestamps.append(now)
        return True

    @property
    def current_count(self) -> int:
        now = time.monotonic()
        cutoff = now - self._window
        return sum(1 for t in self._timestamps if t >= cutoff)

    @property
    def limit(self) -> int:
        return self._limit


# ── ACO Pheromone State ───────────────────────────────────────────────────────


class PheromoneState:
    """
    ACO-inspired adaptive engine selection.
    Pheromone in [0.1, 1.0]. Higher = more likely to be chosen.
    """

    _INIT = 0.8
    _MAX = 1.0
    _MIN = 0.1
    _SUCCESS_BUMP = 0.05
    _FAILURE_DROP = 0.15
    _TIMEOUT_DROP = 0.10

    def __init__(self, engines: List[str], decay: float = 0.9):
        self._decay = decay
        self._ph: Dict[str, float] = {e: self._INIT for e in engines}

    def select(self, candidates: List[str]) -> Optional[str]:
        """Roulette-wheel selection weighted by pheromone."""
        if not candidates:
            return None
        total = sum(self._ph.get(e, self._MIN) for e in candidates)
        if total == 0:
            return candidates[0]
        import random
        r = random.uniform(0, total)
        cumulative = 0.0
        for e in candidates:
            cumulative += self._ph.get(e, self._MIN)
            if cumulative >= r:
                return e
        return candidates[-1]

    def success(self, engine: str) -> None:
        self._ph[engine] = min(self._MAX, self._ph.get(engine, self._INIT) + self._SUCCESS_BUMP)
        self._decay_others(engine)

    def failure(self, engine: str) -> None:
        self._ph[engine] = max(self._MIN, self._ph.get(engine, self._INIT) - self._FAILURE_DROP)

    def timeout(self, engine: str) -> None:
        self._ph[engine] = max(self._MIN, self._ph.get(engine, self._INIT) - self._TIMEOUT_DROP)

    def _decay_others(self, chosen: str) -> None:
        for e in self._ph:
            if e != chosen:
                self._ph[e] = max(self._MIN, self._ph[e] * self._decay)

    def get(self, engine: str) -> float:
        return self._ph.get(engine, self._INIT)

    def all(self) -> Dict[str, float]:
        return dict(self._ph)


# ── Internal Python DAG executor (Tier 1) ────────────────────────────────────


class InternalDagExecutor:
    """Original in-process topological executor — always available."""

    async def execute(
        self, wf_def: WorkflowDefinition, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        from collections import defaultdict as dd

        steps = wf_def.steps
        step_map = {s.step_id: s for s in steps}
        in_degree = {s.step_id: 0 for s in steps}
        adj = dd(list)
        for s in steps:
            for dep in s.depends_on:
                if dep in step_map:
                    adj[dep].append(s.step_id)
                    in_degree[s.step_id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        ordered: List[WorkflowStep] = []
        while queue:
            sid = queue.pop(0)
            ordered.append(step_map[sid])
            for nb in adj[sid]:
                in_degree[nb] -= 1
                if in_degree[nb] == 0:
                    queue.append(nb)

        step_results: Dict[str, Any] = {}
        for step in ordered:
            deps_met = all(
                step_results.get(dep, {}).get("status") == "completed"
                for dep in step.depends_on
                if dep in step_results
            )
            if not deps_met and step.depends_on:
                step_results[step.step_id] = {"status": "skipped", "reason": "deps unmet"}
                continue
            result = await self._run_step(step, step_results, input_data)
            step_results[step.step_id] = result
            if result.get("status") == "failed":
                return {
                    "status": "failed",
                    "step_results": step_results,
                    "error": f"Step '{step.name}' failed: {result.get('error', '')}",
                }

        outputs = {sid: r["output"] for sid, r in step_results.items() if "output" in r}
        return {"status": "completed", "step_results": step_results, "output_data": outputs}

    async def _run_step(self, step, step_results, input_data) -> Dict[str, Any]:
        try:
            action = step.action
            if action == "http_call":
                return await self._http_call(step)
            elif action == "transform":
                return self._transform(step, step_results, input_data)
            elif action == "notify":
                return await self._notify(step)
            elif action == "script":
                return self._script(step, step_results, input_data)
            elif action == "delay":
                await asyncio.sleep(step.config.get("seconds", 1))
                return {"status": "completed", "output": {"delayed": step.config.get("seconds", 1)}}
            else:
                return {"status": "completed", "output": {"action": action, "ack": True}}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    async def _http_call(self, step) -> Dict[str, Any]:
        url = step.config.get("url", "")
        method = step.config.get("method", "GET").upper()
        headers = step.config.get("headers", {})
        body = step.config.get("body", {})
        timeout = step.timeout_seconds or 30
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, headers=headers, json=body if body else None)
            return {
                "status": "completed",
                "output": {"status_code": resp.status_code, "body": resp.text[:5000]},
            }

    def _transform(self, step, step_results, input_data) -> Dict[str, Any]:
        mapping = step.config.get("mapping", {})
        source = step.config.get("source", "input")
        data = input_data if source == "input" else step_results.get(source, {})
        result = {}
        for tk, sp in mapping.items():
            val: Any = data
            for part in sp.split("."):
                val = val.get(part) if isinstance(val, dict) else None
            result[tk] = val
        return {"status": "completed", "output": result}

    async def _notify(self, step) -> Dict[str, Any]:
        url = step.config.get("notifications_url", "http://localhost:8008/notifications/send")
        payload = {
            "user_id": step.config.get("user_id", "system"),
            "channel": step.config.get("channel", "in_app"),
            "subject": step.config.get("subject", "Workflow Notification"),
            "body": step.config.get("body", ""),
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json=payload)
            return {"status": "completed", "output": {"notified": True}}
        except Exception as e:
            return {"status": "completed", "output": {"notified": False, "error": str(e)}}

    def _script(self, step, step_results, input_data) -> Dict[str, Any]:
        code = step.config.get("code", "result = input_data")
        local_vars: Dict[str, Any] = {
            "input_data": input_data,
            "step_results": step_results,
            "result": None,
        }
        exec(code, {"__builtins__": {}}, local_vars)  # noqa: S102
        return {"status": "completed", "output": local_vars.get("result", {})}


# ── n8n engine (Tier 2) ───────────────────────────────────────────────────────


class N8nEngine:
    """Trigger an n8n workflow via webhook or REST API."""

    async def execute(self, wf_def: WorkflowDefinition, input_data: Dict[str, Any]) -> Dict:
        webhook_url = wf_def.metadata.get("n8n_webhook_url")
        headers = {"Accept": "application/json"}
        if config.N8N_API_KEY:
            headers["X-N8N-API-KEY"] = config.N8N_API_KEY

        if webhook_url:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(webhook_url, json=input_data, headers=headers)
                resp.raise_for_status()
                return {"status": "completed", "output_data": resp.json()}

        # Use REST API to trigger by workflow name
        list_url = f"{config.N8N_URL}/api/v1/workflows"
        async with httpx.AsyncClient(timeout=30) as client:
            wf_list = await client.get(list_url, headers=headers)
            wf_list.raise_for_status()
            workflows = wf_list.json().get("data", [])
            matched = next((w for w in workflows if w.get("name") == wf_def.name), None)
            if not matched:
                raise RuntimeError(f"n8n workflow '{wf_def.name}' not found")
            exec_url = f"{config.N8N_URL}/api/v1/workflows/{matched['id']}/execute"
            resp = await client.post(exec_url, json={"data": input_data}, headers=headers)
            resp.raise_for_status()
            return {"status": "completed", "output_data": resp.json()}


# ── Prefect engine (Tier 3) ───────────────────────────────────────────────────


class PrefectEngine:
    """Trigger a Prefect flow run via the Prefect REST API."""

    async def execute(self, wf_def: WorkflowDefinition, input_data: Dict[str, Any]) -> Dict:
        flow_name = wf_def.metadata.get("prefect_flow_name", wf_def.name)
        # Get flow ID
        async with httpx.AsyncClient(base_url=config.PREFECT_URL, timeout=30) as client:
            resp = await client.post(
                "/api/flows/filter",
                json={"flows": {"name": {"any_": [flow_name]}}},
            )
            resp.raise_for_status()
            flows = resp.json()
            if not flows:
                raise RuntimeError(f"Prefect flow '{flow_name}' not registered")
            flow_id = flows[0]["id"]

            # Get default deployment
            dep_resp = await client.post(
                "/api/deployments/filter",
                json={"deployments": {"flow_id": {"any_": [flow_id]}}},
            )
            dep_resp.raise_for_status()
            deployments = dep_resp.json()
            if not deployments:
                raise RuntimeError(f"No deployment found for flow '{flow_name}'")
            deployment_id = deployments[0]["id"]

            # Create flow run
            run_resp = await client.post(
                f"/api/deployments/{deployment_id}/create_flow_run",
                json={"parameters": input_data, "state": {"type": "SCHEDULED"}},
            )
            run_resp.raise_for_status()
            run = run_resp.json()
            return {"status": "completed", "output_data": {"prefect_run_id": run.get("id")}}


# ── Temporal engine (Tier 4) ──────────────────────────────────────────────────


class TemporalEngine:
    """Schedule a Temporal workflow via temporalio Python SDK or REST API."""

    async def execute(self, wf_def: WorkflowDefinition, input_data: Dict[str, Any]) -> Dict:
        # Attempt SDK path first; fall back to temporalite REST if SDK absent
        try:
            from temporalio.client import Client  # type: ignore

            client = await Client.connect(config.TEMPORAL_HOST)
            wf_type = wf_def.metadata.get("temporal_workflow_type", wf_def.name)
            task_queue = wf_def.metadata.get("temporal_task_queue", "the-grid")
            handle = await client.start_workflow(
                wf_type,
                input_data,
                id=f"grid-{wf_def.workflow_id}",
                task_queue=task_queue,
            )
            return {"status": "completed", "output_data": {"temporal_run_id": handle.result_run_id}}
        except ImportError:
            raise RuntimeError("temporalio SDK not installed; add temporalio to requirements")


# ── Airflow engine (Tier 5) ───────────────────────────────────────────────────


class AirflowEngine:
    """Trigger an Airflow DAG run via the stable REST API v1."""

    async def execute(self, wf_def: WorkflowDefinition, input_data: Dict[str, Any]) -> Dict:
        dag_id = wf_def.metadata.get("airflow_dag_id", wf_def.name.lower().replace(" ", "_"))
        url = f"{config.AIRFLOW_URL}/api/v1/dags/{dag_id}/dagRuns"
        auth = (config.AIRFLOW_USER, config.AIRFLOW_PASS)
        payload = {"conf": input_data}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, auth=auth)
            resp.raise_for_status()
            data = resp.json()
            return {"status": "completed", "output_data": {"airflow_run_id": data.get("dag_run_id")}}


# ── Dagster engine (Tier 6) ───────────────────────────────────────────────────


class DagsterEngine:
    """Launch a Dagster job via its GraphQL API."""

    async def execute(self, wf_def: WorkflowDefinition, input_data: Dict[str, Any]) -> Dict:
        job_name = wf_def.metadata.get("dagster_job_name", wf_def.name)
        repo_loc = wf_def.metadata.get("dagster_repo_location", "the_grid")
        repo_name = wf_def.metadata.get("dagster_repo_name", "the_grid_repo")
        gql = f"""
        mutation LaunchRun {{
          launchRun(executionParams: {{
            selector: {{
              repositoryLocationName: "{repo_loc}"
              repositoryName: "{repo_name}"
              jobName: "{job_name}"
            }}
            runConfigData: {json.dumps(json.dumps({"ops": {"input": {"config": input_data}}}))}
          }}) {{
            __typename
            ... on LaunchRunSuccess {{ run {{ runId }} }}
            ... on PythonError {{ message }}
          }}
        }}
        """
        async with httpx.AsyncClient(base_url=config.DAGSTER_URL, timeout=30) as client:
            resp = await client.post("/graphql", json={"query": gql})
            resp.raise_for_status()
            body = resp.json()
            launch = body.get("data", {}).get("launchRun", {})
            if launch.get("__typename") != "LaunchRunSuccess":
                raise RuntimeError(f"Dagster error: {launch.get('message', body)}")
            run_id = launch.get("run", {}).get("runId")
            return {"status": "completed", "output_data": {"dagster_run_id": run_id}}


# ── Luigi engine (Tier 7) ─────────────────────────────────────────────────────


class LuigiEngine:
    """Run a Luigi task graph in-process (no server required)."""

    async def execute(self, wf_def: WorkflowDefinition, input_data: Dict[str, Any]) -> Dict:
        try:
            import luigi  # type: ignore
        except ImportError:
            raise RuntimeError("luigi not installed; add luigi to requirements")

        class GridTask(luigi.Task):
            workflow_id = luigi.Parameter()
            step_index = luigi.IntParameter(default=0)

            def requires(self):
                return []

            def run(self):
                with self.output().open("w") as f:
                    json.dump({"status": "completed", "input": input_data}, f)

            def output(self):
                return luigi.LocalTarget(f"/tmp/grid_{self.workflow_id}_{self.step_index}.json")

        tasks = [
            GridTask(workflow_id=wf_def.workflow_id, step_index=i)
            for i in range(len(wf_def.steps))
        ]
        result = luigi.build(tasks, local_scheduler=True, log_level="WARNING")
        return {
            "status": "completed" if result else "failed",
            "output_data": {"luigi_tasks": len(tasks)},
        }


# ── Offline stub (Tier 8) ─────────────────────────────────────────────────────


class OfflineEngine:
    """Deterministic stub — always succeeds, returns synthetic output."""

    async def execute(self, wf_def: WorkflowDefinition, input_data: Dict[str, Any]) -> Dict:
        return {
            "status": "completed",
            "output_data": {
                "engine": "offline",
                "workflow": wf_def.name,
                "steps": len(wf_def.steps),
                "input_echo": input_data,
                "note": "Offline stub — no external engine available",
            },
        }


# ── Adaptive Router ───────────────────────────────────────────────────────────

_TIER_ORDER = [
    EngineType.internal,
    EngineType.n8n,
    EngineType.prefect,
    EngineType.temporal,
    EngineType.airflow,
    EngineType.dagster,
    EngineType.luigi,
    EngineType.offline,
]

_THRESHOLDS = {
    EngineType.n8n: config.THRESHOLD_N8N,
    EngineType.prefect: config.THRESHOLD_PREFECT,
    EngineType.temporal: config.THRESHOLD_TEMPORAL,
    EngineType.airflow: config.THRESHOLD_AIRFLOW,
    EngineType.dagster: config.THRESHOLD_DAGSTER,
    EngineType.luigi: config.THRESHOLD_LUIGI,
    EngineType.internal: 999999,
    EngineType.offline: 999999,
}


class WorkflowEngineRouter:
    """
    8-tier adaptive workflow engine router with:
    - ACO pheromone-trail selection
    - Per-engine ThresholdGuard (sliding-window hard-stop)
    - Waterfall fallback on error/threshold breach
    """

    def __init__(self, db: GridDatabase):
        self.db = db
        self._pheromone = PheromoneState(
            [e.value for e in _TIER_ORDER], decay=config.ACO_DECAY
        )
        self._guards: Dict[str, ThresholdGuard] = {
            e.value: ThresholdGuard(_THRESHOLDS[e], config.THRESHOLD_WINDOW_SECONDS)
            for e in _TIER_ORDER
        }
        self._engines: Dict[str, Any] = {
            EngineType.internal.value: InternalDagExecutor(),
            EngineType.n8n.value: N8nEngine(),
            EngineType.prefect.value: PrefectEngine(),
            EngineType.temporal.value: TemporalEngine(),
            EngineType.airflow.value: AirflowEngine(),
            EngineType.dagster.value: DagsterEngine(),
            EngineType.luigi.value: LuigiEngine(),
            EngineType.offline.value: OfflineEngine(),
        }
        self._health: Dict[str, bool] = {e.value: True for e in _TIER_ORDER}

    def engine_statuses(self) -> List[EngineStatus]:
        statuses = []
        for e in _TIER_ORDER:
            guard = self._guards[e.value]
            statuses.append(
                EngineStatus(
                    engine=e.value,
                    healthy=self._health[e.value],
                    pheromone=round(self._pheromone.get(e.value), 3),
                    requests_in_window=guard.current_count,
                    threshold=guard.limit,
                    blocked=not guard.check() if False else guard.current_count >= guard.limit,
                )
            )
        return statuses

    def _available_engines(self, preferred: Optional[str] = None) -> List[str]:
        """Return engines that are healthy and under threshold, in tier order."""
        available = []
        for e in _TIER_ORDER:
            ev = e.value
            guard = self._guards[ev]
            if not self._health[ev]:
                continue
            if guard.current_count >= guard.limit:
                logger.warning("Engine %s at threshold (%d), skipping", ev, guard.limit)
                continue
            available.append(ev)
        if preferred and preferred in available:
            # Move preferred to front but keep rest for fallback
            available = [preferred] + [e for e in available if e != preferred]
        return available

    async def execute(
        self,
        wf_def: WorkflowDefinition,
        input_data: Dict[str, Any],
    ) -> WorkflowExecution:
        execution = WorkflowExecution(
            workflow_id=wf_def.workflow_id,
            input_data=input_data,
            status=WorkflowStatus.running,
            started_at=datetime.now(timezone.utc),
        )
        self.db.save_execution(execution)

        forced = config.FORCE_ENGINE
        preferred = (
            forced or (wf_def.preferred_engine.value if wf_def.preferred_engine else None)
        )

        if forced:
            candidates = [forced] if forced in self._engines else [EngineType.offline.value]
        else:
            candidates = self._available_engines(preferred)

        if not candidates:
            candidates = [EngineType.offline.value]

        # ACO selection from top candidates (pick from first 3 available by pheromone)
        top = candidates[:3]
        chosen = self._pheromone.select(top) if len(top) > 1 else top[0]
        # Ensure chosen is first, rest follow as fallback
        fallback_order = [chosen] + [c for c in candidates if c != chosen]

        last_error: str = "no engines attempted"
        for engine_name in fallback_order:
            engine = self._engines[engine_name]
            guard = self._guards[engine_name]
            if not guard.check():
                logger.warning("Engine %s threshold hit during attempt, skipping", engine_name)
                continue

            logger.info("Attempting engine: %s", engine_name)
            t0 = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    engine.execute(wf_def, input_data),
                    timeout=300,
                )
                elapsed = time.monotonic() - t0
                self._pheromone.success(engine_name)
                self._health[engine_name] = True
                logger.info("Engine %s succeeded in %.2fs", engine_name, elapsed)

                execution.engine_used = engine_name
                execution.status = (
                    WorkflowStatus.completed
                    if result.get("status") == "completed"
                    else WorkflowStatus.failed
                )
                execution.output_data = result.get("output_data", {})
                execution.step_results = result.get("step_results", {})
                if result.get("status") != "completed":
                    execution.error_message = result.get("error", "Engine reported failure")
                execution.completed_at = datetime.now(timezone.utc)
                self.db.save_execution(execution)
                return execution

            except asyncio.TimeoutError:
                self._pheromone.timeout(engine_name)
                self._health[engine_name] = False
                last_error = f"Engine {engine_name} timed out"
                logger.warning("%s", last_error)

            except Exception as exc:
                self._pheromone.failure(engine_name)
                self._health[engine_name] = False
                last_error = f"Engine {engine_name} failed: {exc}"
                logger.warning("%s", last_error)

        # All engines exhausted
        execution.engine_used = EngineType.offline.value
        execution.status = WorkflowStatus.failed
        execution.error_message = f"All engines exhausted. Last error: {last_error}"
        execution.completed_at = datetime.now(timezone.utc)
        self.db.save_execution(execution)
        return execution
