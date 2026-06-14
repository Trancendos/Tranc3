"""The Ice Box — lightweight sandbox API stub.

Full CAPEv2 requires KVM/QEMU VMs with analyst setup. This stub provides
the API surface so integrations can be built before the full sandbox is deployed.
Follow https://capev2.readthedocs.io for the complete installation guide.
"""
import json
import os
import uuid
import hashlib
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

SECRET = os.getenv("ICEBOX_SECRET", "change-me")
PORT = int(os.getenv("ICEBOX_PORT", "8090"))
DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)

SAMPLES: dict = {}


class IceBoxHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: D102
        print(f"[icebox] {fmt % args}")

    def _json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ok", "service": "the-ice-box", "mode": "stub"})
        elif self.path == "/tasks/list":
            self._json(200, {"tasks": list(SAMPLES.values())})
        elif self.path.startswith("/tasks/report/"):
            task_id = self.path.split("/")[-1]
            if task_id in SAMPLES:
                self._json(200, {"task": SAMPLES[task_id], "report": "pending"})
            else:
                self._json(404, {"error": "task not found"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/tasks/create/file":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            task_id = str(uuid.uuid4())[:8]
            sha256 = hashlib.sha256(body).hexdigest()
            SAMPLES[task_id] = {
                "id": task_id,
                "sha256": sha256,
                "status": "pending",
                "submitted": datetime.datetime.utcnow().isoformat(),
                "size": len(body),
            }
            self._json(200, {"task_id": task_id, "sha256": sha256})
        else:
            self._json(404, {"error": "not found"})


if __name__ == "__main__":
    print(f"[icebox] The Ice Box stub listening on :{PORT}")
    print("[icebox] NOTE: This is a stub. Deploy CAPEv2 for real sandbox analysis.")
    HTTPServer(("0.0.0.0", PORT), IceBoxHandler).serve_forever()
