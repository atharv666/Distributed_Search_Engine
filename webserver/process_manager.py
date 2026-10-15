"""Start and kill the coordinator and node processes from the admin page."""

import subprocess
import sys
import threading
import time
from pathlib import Path

from distributed_systems.cluster_config import ClusterConfig

ROOT = Path(__file__).resolve().parent.parent


class ProcessManager:
    def __init__(self, config: ClusterConfig) -> None:
        self.cfg = config
        self.processes: dict[str, subprocess.Popen] = {}
        self.started_at: dict[str, float] = {}
        self._logs: dict[str, object] = {}
        self._lock = threading.Lock()

    def _command(self, process_id: str) -> list[str]:
        module = "coordinator.server" if process_id.startswith("C") else "search_node.server"
        return [sys.executable, "-m", module, "--id", process_id, "--config", str(self.cfg.path)]

    def known(self, process_id: str) -> bool:
        return process_id in self.cfg.process_ids()

    def running(self, process_id: str) -> bool:
        process = self.processes.get(process_id)
        return process is not None and process.poll() is None

    def start(self, process_id: str) -> str:
        with self._lock:
            if self.running(process_id):
                return "running"
            log_directory = self.cfg.data_directory / "logs"
            log_directory.mkdir(parents=True, exist_ok=True)
            log = open(log_directory / f"{process_id}.log", "ab")
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.processes[process_id] = subprocess.Popen(
                self._command(process_id), cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            self._logs[process_id] = log
            self.started_at[process_id] = time.time()
            return "starting"

    def stop(self, process_id: str) -> str:
        """Kill the process and anything it spawned (a venv python can be a thin redirector on Windows)."""
        with self._lock:
            process = self.processes.pop(process_id, None)
            if process is not None and process.poll() is None:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            log = self._logs.pop(process_id, None)
            if log is not None:
                log.close()
            return "stopped"

    def start_all(self) -> None:
        """Highest-ranked coordinators first so the cluster settles on C3 without needless elections."""
        for coordinator in sorted(self.cfg.coordinators, key=lambda entry: -entry.rank):
            self.start(coordinator.id)
        for node in self.cfg.nodes:
            self.start(node.id)

    def stop_all(self) -> None:
        for process_id in list(self.processes):
            self.stop(process_id)
