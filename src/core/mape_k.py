"""
Reusable MAPE-K (Monitor-Analyze-Plan-Execute-Knowledge) loop.
Runs in background thread, self-heals workers autonomously.
"""

import json
import sqlite3
import statistics
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class MAPEKLoop:
    def __init__(
        self,
        name: str,
        monitor_fn: Callable[[], Dict],
        analyze_fn: Optional[Callable] = None,
        plan_fn: Optional[Callable] = None,
        execute_fn: Optional[Callable] = None,
        db_path: Optional[Path] = None,
        interval_seconds: int = 30,
    ):
        self.name = name
        self._monitor_fn = monitor_fn
        self._analyze_fn = analyze_fn or self._default_analyze
        self._plan_fn = plan_fn or self._default_plan
        self._execute_fn = execute_fn or self._default_execute
        self._interval = interval_seconds
        self._history: deque = deque(maxlen=1000)
        self._knowledge: Dict[str, Any] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._db_path = db_path
        self._lock = threading.Lock()

        if db_path:
            self._init_db(db_path)

    def _init_db(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mapek_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    loop_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    metrics TEXT,
                    analysis TEXT,
                    plan TEXT,
                    executed INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mapek_knowledge (
                    loop_name TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (loop_name, key)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def start(self):
        """Start the MAPE-K loop in a daemon thread."""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name=f"mapek-{self.name}")
        self._thread.start()

    def stop(self):
        """Stop the MAPE-K loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._interval + 5)

    def _default_analyze(self, metrics: Dict) -> Dict:
        """Z-score anomaly detection on numeric values in metrics."""
        with self._lock:
            history_list = list(self._history)

        numeric_keys = [k for k, v in metrics.items() if isinstance(v, (int, float))]
        anomaly_score = 0.0
        anomalies = []

        for key in numeric_keys:
            historical_values = [
                entry["metrics"].get(key)
                for entry in history_list
                if isinstance(entry.get("metrics", {}).get(key), (int, float))
            ]
            if len(historical_values) >= 5:
                mean = statistics.mean(historical_values)
                stdev = statistics.stdev(historical_values) if len(historical_values) > 1 else 0
                if stdev > 0:
                    z = abs((metrics[key] - mean) / stdev)
                    if z > 2.0:
                        anomaly_score = max(anomaly_score, z)
                        anomalies.append(
                            {"key": key, "z_score": z, "value": metrics[key], "mean": mean}
                        )

        needs_action = anomaly_score > 2.0
        action = "none"
        if anomaly_score > 3.0:
            action = "critical_alert"
        elif anomaly_score > 2.5:
            action = "scale_down"
        elif anomaly_score > 2.0:
            action = "investigate"

        return {
            "anomaly_score": anomaly_score,
            "needs_action": needs_action,
            "action": action,
            "anomalies": anomalies,
            "metrics_checked": len(numeric_keys),
        }

    def _default_plan(self, analysis: Dict) -> Dict:
        """Map action → plan dict with parameters."""
        action = analysis.get("action", "none")
        plans = {
            "none": {"steps": [], "priority": 0},
            "investigate": {
                "steps": ["log_anomaly", "notify_ops"],
                "priority": 1,
                "message": f"Anomaly detected: score={analysis.get('anomaly_score', 0):.2f}",
            },
            "scale_down": {
                "steps": ["reduce_rate_limit", "drain_queue", "notify_ops"],
                "priority": 2,
                "reduce_by": 0.2,
            },
            "critical_alert": {
                "steps": ["page_oncall", "capture_diagnostics", "circuit_break"],
                "priority": 3,
                "message": f"Critical anomaly: score={analysis.get('anomaly_score', 0):.2f}",
            },
        }
        return plans.get(action, {"steps": [], "priority": 0})

    def _default_execute(self, plan: Dict) -> bool:
        """Default executor: logs the plan steps."""
        if plan.get("priority", 0) > 0:
            steps = plan.get("steps", [])
            self.update_knowledge(
                "last_executed_plan",
                {
                    "steps": steps,
                    "timestamp": time.time(),
                    "priority": plan.get("priority", 0),
                },
            )
        return True

    def _loop(self):
        """Runs the Monitor→Analyze→Plan→Execute cycle."""
        while self._running:
            cycle_start = time.time()
            try:
                # Monitor
                metrics = self._monitor_fn()

                # Analyze
                analysis = self._analyze_fn(metrics)

                # Plan
                plan = self._plan_fn(analysis)

                # Execute
                executed = False
                if analysis.get("needs_action", False):
                    executed = bool(self._execute_fn(plan))

                # Record cycle
                record = {
                    "timestamp": cycle_start,
                    "metrics": metrics,
                    "analysis": analysis,
                    "plan": plan,
                    "executed": executed,
                }
                with self._lock:
                    self._history.append(record)

                if self._db_path:
                    self._persist_cycle(record)

            except Exception as exc:
                with self._lock:
                    self._history.append(
                        {
                            "timestamp": cycle_start,
                            "error": str(exc),
                            "metrics": {},
                            "analysis": {},
                            "plan": {},
                            "executed": False,
                        }
                    )

            elapsed = time.time() - cycle_start
            sleep_time = max(0, self._interval - elapsed)
            time.sleep(sleep_time)

    def _persist_cycle(self, record: Dict):
        try:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute(
                    "INSERT INTO mapek_history (loop_name, timestamp, metrics, analysis, plan, executed) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        self.name,
                        record["timestamp"],
                        json.dumps(record.get("metrics", {})),
                        json.dumps(record.get("analysis", {})),
                        json.dumps(record.get("plan", {})),
                        1 if record.get("executed") else 0,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    def get_history(self) -> List[Dict]:
        """Return the in-memory history as a list."""
        with self._lock:
            return list(self._history)

    def update_knowledge(self, key: str, value: Any):
        """Update the knowledge base."""
        with self._lock:
            self._knowledge[key] = value

        if self._db_path:
            try:
                conn = sqlite3.connect(str(self._db_path))
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO mapek_knowledge (loop_name, key, value, updated_at) "
                        "VALUES (?, ?, ?, ?)",
                        (self.name, key, json.dumps(value), time.time()),
                    )
                    conn.commit()
                finally:
                    conn.close()
            except Exception:
                pass

    def get_knowledge(self) -> Dict:
        """Return the current knowledge base."""
        with self._lock:
            return dict(self._knowledge)
