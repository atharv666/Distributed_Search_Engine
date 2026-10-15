"""Helpers that run a disposable cluster (own ports, copied data, fast timers) for end-to-end tests."""

import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL_DATA = ROOT / "data"
WEB_PORT = 8120
NODE_PORT_BASE = 51050
COORDINATOR_PORT_BASE = 51060


def data_available() -> bool:
    return all((REAL_DATA / name).exists() for name in
               ("documents.jsonl", "indexes/global_statistics.json", "shards/partition_manifest.json", "shards/shard_1.jsonl"))


def make_workspace(directory: Path, heartbeat_seconds: float = 1.0) -> Path:
    """Copy the base data into `directory` and write a cluster config for it. Returns the config path."""
    data = directory / "data"
    (data / "indexes").mkdir(parents=True)
    (data / "shards").mkdir(parents=True)
    shutil.copy(REAL_DATA / "documents.jsonl", data / "documents.jsonl")
    shutil.copy(REAL_DATA / "indexes" / "global_statistics.json", data / "indexes" / "global_statistics.json")
    for source in (REAL_DATA / "shards").iterdir():
        if source.is_file():
            shutil.copy(source, data / "shards" / source.name)
    config = {
        "data_directory": "data",
        "web": {"host": "127.0.0.1", "port": WEB_PORT},
        "coordinators": [{"id": f"C{i}", "address": f"127.0.0.1:{COORDINATOR_PORT_BASE + i}"} for i in (1, 2, 3)],
        "nodes": [{"id": f"N{i}", "address": f"127.0.0.1:{NODE_PORT_BASE + i}", "shard": i} for i in (1, 2, 3)],
        "timing": {"heartbeat_interval_seconds": heartbeat_seconds, "missed_beats_before_suspect": 3,
                   "rpc_timeout_seconds": 3, "election_wait_seconds": 6, "boot_grace_seconds": 1.0},
        "search": {"local_top_k": 20, "final_top_k": 10},
    }
    path = directory / "cluster_config.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


class WebServer:
    """The real web server in a subprocess; it starts and kills the coordinators and nodes."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.base = f"http://127.0.0.1:{WEB_PORT}"
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        self.process = subprocess.Popen([sys.executable, "-m", "webserver.server", "--config", str(self.config_path)],
                                        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_for(lambda: self.get("/api/health", quiet=True), 20, "web server did not start")

    def stop(self) -> None:
        try:
            self.post("/api/admin/stop-all")
        except Exception:  # noqa: BLE001
            pass
        if self.process and self.process.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], capture_output=True)
            else:
                self.process.terminate()
            self.process.wait(timeout=10)

    def get(self, path: str, quiet: bool = False):
        try:
            with urllib.request.urlopen(self.base + path, timeout=15) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if quiet:
                return None
            raise

    def post(self, path: str, body=None, timeout: float = 60):
        data = json.dumps(body if body is not None else {}).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"},
                                         method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            return {"http_error": error.code, "detail": error.read().decode("utf-8", "replace")}

    # -- convenience -------------------------------------------------------------------------
    def cluster(self) -> dict:
        return self.get("/api/cluster")

    def status_of(self, process_id: str) -> dict:
        return next(item for item in self.cluster()["processes"] if item["id"] == process_id)

    def all_events(self) -> list[dict]:
        events, last = [], 0
        while True:
            chunk = self.get(f"/api/events?since={last}&limit=10000")
            if not chunk["events"]:
                return events
            events.extend(chunk["events"])
            last = chunk["last_id"]


def wait_for(predicate, timeout: float, message: str = "condition not met", interval: float = 0.4):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"Timed out after {timeout}s: {message}")
