"""HTTP API and static UI hosted by the distributed-search coordinator."""

import argparse
import subprocess
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine.config import load_config
from .engine.coordinator import SearchCoordinator

ROOT = Path(__file__).resolve().parent.parent
WEB_DIRECTORY = ROOT / "web"
app = FastAPI(title="Distributed Search", version="0.1")
coordinator: SearchCoordinator | None = None
node_processes: dict[str, subprocess.Popen] = {}


def node_launch_arguments(node_id: str) -> list[str]:
    shard_id = node_id.rsplit("_", 1)[-1]
    return [sys.executable, "-m", "search_node.server", "--node-id", node_id, "--port", str(50050 + int(shard_id)),
            "--index", str(ROOT / f"data/indexes/nodes/node_{shard_id}_index.json"),
            "--shard", str(ROOT / f"data/shards/shard_{shard_id}.jsonl"),
            "--statistics", str(ROOT / "data/indexes/global_statistics.json")]


def process_state(node_id: str) -> str:
    process = node_processes.get(node_id)
    if process is None:
        return "stopped"
    if process.poll() is None:
        return "running"
    node_processes.pop(node_id, None)
    return "stopped"


class SearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int | None = Field(default=None, ge=1, le=50)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/search")
def search(body: SearchBody) -> dict[str, object]:
    if coordinator is None:
        raise HTTPException(status_code=503, detail="Coordinator is not configured.")
    return coordinator.search(body.query.strip(), body.top_k)


@app.get("/api/nodes")
def nodes() -> list[dict[str, str]]:
    if coordinator is None:
        return []
    return [{"node_id": node.node_id, "address": node.address, "state": process_state(node.node_id)} for node in coordinator.config.nodes]


@app.post("/api/nodes/{node_id}/start")
def start_node(node_id: str) -> dict[str, str]:
    if coordinator is None or node_id not in {node.node_id for node in coordinator.config.nodes}:
        raise HTTPException(status_code=404, detail="Unknown node.")
    if process_state(node_id) == "running":
        return {"node_id": node_id, "state": "running"}
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    node_processes[node_id] = subprocess.Popen(node_launch_arguments(node_id), cwd=ROOT, creationflags=creation_flags)
    return {"node_id": node_id, "state": "starting"}


@app.post("/api/nodes/{node_id}/stop")
def stop_node(node_id: str) -> dict[str, str]:
    process = node_processes.get(node_id)
    if process and process.poll() is None:
        process.terminate()
        process.wait(timeout=3)
    node_processes.pop(node_id, None)
    return {"node_id": node_id, "state": "stopped"}


app.mount("/", StaticFiles(directory=WEB_DIRECTORY, html=True), name="web")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the browser-facing distributed search coordinator.")
    parser.add_argument("--config", type=Path, default=ROOT / "coordinator/config/coordinator_config.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()
    global coordinator
    coordinator = SearchCoordinator(load_config(arguments.config))
    uvicorn.run(app, host=arguments.host, port=arguments.port)


if __name__ == "__main__":
    main()
