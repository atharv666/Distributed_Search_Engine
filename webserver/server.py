"""Web server: serves the search and admin pages and sits between the browser and the coordinators.

It is an outside observer of the cluster, not a participant: it takes no part in the vector
clocks, it only fetches/parses URLs, forwards requests to the leader, controls the processes
and collects the clocked events that every coordinator and node reports.
"""

import argparse
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import grpc
import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from distributed_systems.cluster_config import ClusterConfig, load_cluster_config
from distributed_systems.rpc import fan_out, quiet_call
from partitioning.partitioner.config import PartitionConfig
from partitioning.partitioner.partitioner import partition_documents
from proto import search_pb2, search_pb2_grpc

from .ingest import DocumentBuilder, IngestError
from .process_manager import ProcessManager

ROOT = Path(__file__).resolve().parent.parent
WEB_DIRECTORY = ROOT / "web"
DEFAULT_CONFIG = ROOT / "coordinator" / "config" / "cluster_config.json"
CoordinatorStub = search_pb2_grpc.CoordinatorServiceStub
NodeStub = search_pb2_grpc.NodeServiceStub
STARTING_GRACE_SECONDS = 30


class EventStore:
    """In-memory, append-only list of events with increasing IDs, so the UI can poll `since=<id>`."""

    def __init__(self, limit: int = 40000) -> None:
        self.limit = limit
        self.events: list[dict] = []
        self.first_id = 1
        self.lock = threading.Lock()

    def add_many(self, events: list[dict]) -> None:
        with self.lock:
            for event in events:
                event["id"] = self.first_id + len(self.events)
                self.events.append(event)
            overflow = len(self.events) - self.limit
            if overflow > 0:
                del self.events[:overflow]
                self.first_id += overflow

    def since(self, last_id: int, limit: int = 5000) -> tuple[list[dict], int]:
        with self.lock:
            start = max(0, last_id + 1 - self.first_id)
            chunk = self.events[start:start + limit]
            return list(chunk), (chunk[-1]["id"] if chunk else last_id)

    def clear(self) -> None:
        with self.lock:
            self.first_id += len(self.events)
            self.events.clear()

    def observe(self, op: str, name: str, **details) -> None:
        """An event from the web server itself (no vector clock: it is outside the cluster)."""
        self.add_many([{"process": "web", "seq": 0, "kind": "observer", "name": name, "category": "add", "op": op,
                        "peer": "", "msg_id": "", "vector": None, "time": time.time(), "details": details}])


def status_to_dict(reply, up: bool = True) -> dict:
    return {
        "up": up, "id": reply.process_id, "kind": reply.kind, "role": reply.role, "leader_id": reply.leader_id,
        "epoch": reply.epoch, "stats_version": reply.stats_version, "committed_version": reply.committed_version,
        "ready": reply.ready, "last_beat_age": reply.last_beat_age, "beat_timeout": reply.beat_timeout,
        "beacons_sent": reply.beacons_sent, "beacons_received": reply.beacons_received,
        "doc_count": reply.doc_count, "total_docs": reply.total_docs, "next_doc_id": reply.next_doc_id,
        "node_counts": dict(reply.node_counts), "clock": {key: int(value) for key, value in reply.clock.items()},
        "node_alive": dict(reply.node_alive),
    }


class ClusterView:
    """Polls every process once a second so the pages never wait on slow or dead processes."""

    def __init__(self, config: ClusterConfig, manager: ProcessManager) -> None:
        self.cfg, self.manager = config, manager
        self.status: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.stopping = threading.Event()

    def poll_once(self) -> None:
        def fetch(process_id: str) -> dict:
            is_coordinator = process_id.startswith("C")
            entry = self.cfg.coordinator(process_id) if is_coordinator else self.cfg.node(process_id)
            try:
                reply = quiet_call(entry.address, CoordinatorStub if is_coordinator else NodeStub, "GetStatus",
                                   search_pb2.StatusRequest(), timeout=0.8)
                return status_to_dict(reply)
            except grpc.RpcError:
                return {"up": False, "id": process_id, "kind": "coordinator" if is_coordinator else "node"}

        results = fan_out(self.cfg.process_ids(), fetch)
        with self.lock:
            self.status = {process_id: result for process_id, result in results if isinstance(result, dict)}

    def run(self) -> None:
        while not self.stopping.is_set():
            self.poll_once()
            self.stopping.wait(1.0)

    def leader(self):
        with self.lock:
            leaders = [status for status in self.status.values()
                       if status.get("up") and status["kind"] == "coordinator" and status["role"] == "LEADER"
                       and status["ready"]]
        if not leaders:
            return None
        return self.cfg.coordinator(max(leaders, key=lambda status: status["epoch"])["id"])

    def snapshot(self) -> dict:
        with self.lock:
            status = dict(self.status)
        now = time.time()
        processes = []
        for process_id in self.cfg.process_ids():
            entry = dict(status.get(process_id, {"up": False, "id": process_id,
                                                 "kind": "coordinator" if process_id.startswith("C") else "node"}))
            managed = self.manager.running(process_id)
            if entry["up"]:
                state = "running"
            elif managed and now - self.manager.started_at.get(process_id, 0) < STARTING_GRACE_SECONDS:
                state = "starting"
            elif managed:
                state = "unresponsive"
            else:
                state = "stopped"
            entry.update(state=state, managed=managed)
            processes.append(entry)
        leader = self.leader()
        leader_status = next((item for item in processes if leader and item["id"] == leader.id), None)
        return {"leader": leader.id if leader else None,
                "epoch": leader_status["epoch"] if leader_status else 0,
                "stats_version": leader_status["committed_version"] if leader_status else 0,
                "heartbeat_interval": self.cfg.heartbeat_interval, "beat_timeout": self.cfg.beat_timeout,
                "processes": processes, "server_time": now}


class State:
    cfg: ClusterConfig
    manager: ProcessManager
    cluster: ClusterView
    events = EventStore()
    builder = DocumentBuilder()


state = State()


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=state.cluster.run, name="cluster-poller", daemon=True).start()
    yield
    state.cluster.stopping.set()
    state.manager.stop_all()


app = FastAPI(title="Distributed Search", version="0.2", lifespan=lifespan)


# ---------------------------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------------------------
class SearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int | None = Field(default=None, ge=1, le=50)


def coordinators_in_preference_order():
    """Leader first, then any other coordinator that answered the last poll, then the rest."""
    leader = state.cluster.leader()
    snapshot = {item["id"]: item for item in state.cluster.snapshot()["processes"]}
    others = [entry for entry in state.cfg.coordinators if not leader or entry.id != leader.id]
    others.sort(key=lambda entry: (not snapshot[entry.id]["up"], -entry.rank))
    return ([leader] if leader else []) + others


@app.post("/api/search")
def search(body: SearchBody) -> dict:
    for coordinator in coordinators_in_preference_order():
        try:
            reply = quiet_call(coordinator.address, CoordinatorStub, "Search",
                               search_pb2.SearchRequest(query=body.query.strip(), top_k=body.top_k or 0),
                               timeout=state.cfg.rpc_timeout + 4)
        except grpc.RpcError:
            continue
        return {
            "query": body.query,
            "results": [{"document_id": r.document_id, "score": r.score, "title": r.title, "url": r.url,
                         "snippet": r.snippet, "node_id": r.node_id} for r in reply.results],
            "node_status": [{"node_id": s.node_id, "status": s.status, "latency_ms": s.latency_ms,
                             "candidate_count": s.candidate_count, "stats_version": s.stats_version,
                             "accepted": s.accepted, "error": s.error} for s in reply.node_status],
            "healthy_nodes": reply.healthy_nodes, "total_nodes": reply.total_nodes,
            "candidate_count": reply.candidate_count, "elapsed_ms": reply.elapsed_ms,
            "coordinator_id": reply.coordinator_id, "coordinator_role": reply.role, "epoch": reply.epoch,
            "stats_version": reply.stats_version, "operation_id": reply.operation_id,
        }
    raise HTTPException(status_code=503, detail="No coordinator is reachable. Start the cluster from the Admin page.")


# ---------------------------------------------------------------------------------------------
# Cluster status, events and process control (admin)
# ---------------------------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/cluster")
def cluster() -> dict:
    return state.cluster.snapshot()


@app.post("/internal/events")
def receive_events(events: list[dict] = Body(...)) -> dict[str, int]:
    state.events.add_many(events)
    return {"accepted": len(events)}


@app.get("/api/events")
def events(since: int = 0, limit: int = 5000) -> dict:
    chunk, last_id = state.events.since(since, min(limit, 10000))
    return {"events": chunk, "last_id": last_id}


@app.post("/api/admin/processes/{process_id}/{action}")
def control_process(process_id: str, action: str) -> dict[str, str]:
    if not state.manager.known(process_id) or action not in ("start", "stop"):
        raise HTTPException(status_code=404, detail="Unknown process or action.")
    result = state.manager.start(process_id) if action == "start" else state.manager.stop(process_id)
    return {"process_id": process_id, "state": result}


@app.post("/api/admin/start-all")
def start_all() -> dict[str, str]:
    state.manager.start_all()
    return {"state": "starting"}


@app.post("/api/admin/stop-all")
def stop_all() -> dict[str, str]:
    state.manager.stop_all()
    return {"state": "stopped"}


@app.post("/api/admin/reset")
def reset_demo_data() -> dict[str, object]:
    """Stop everything, forget added documents (delta logs) and restore the original shards."""
    state.manager.stop_all()
    state.cluster.poll_once()
    running = [item["id"] for item in state.cluster.snapshot()["processes"] if item["up"]]
    if running:
        raise HTTPException(status_code=409, detail=f"Processes still running outside this server: {running}")
    data = state.cfg.data_directory
    if not (data / "documents.jsonl").exists():
        raise HTTPException(status_code=400, detail="data/documents.jsonl is missing; cannot restore shards.")
    shutil.rmtree(data / "state", ignore_errors=True)
    manifest = partition_documents(PartitionConfig(
        documents_file=data / "documents.jsonl", output_directory=data / "shards",
        shard_count=len(state.cfg.nodes), strategy="range"))
    state.events.clear()
    return {"restored_documents": manifest["global_document_count"]}


# ---------------------------------------------------------------------------------------------
# Adding documents
# ---------------------------------------------------------------------------------------------
class TextDocument(BaseModel):
    title: str = ""
    content: str = Field(min_length=1)
    url: str = ""


class DocumentsBody(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=10)
    texts: list[TextDocument] = Field(default_factory=list, max_length=10)


def submit_to_leader(document: dict, op: str) -> dict:
    """Send the document to whichever coordinator is leader; follow a NOT_LEADER hint if needed."""
    deadline = time.time() + 12
    while time.time() < deadline:
        leader = state.cluster.leader()
        if leader is None:
            state.cluster.poll_once()
            leader = state.cluster.leader()
        if leader is None:
            time.sleep(1.0)
            continue
        state.events.observe(op, "submitted_to_leader", leader=leader.id)
        request = search_pb2.SubmitRequest(operation_id=op)
        request.document.CopyFrom(search_pb2.Document(
            title=document["title"], url=document["url"], source=document["source"], content=document["content"],
            content_length=document["content_length"]))
        try:
            reply = quiet_call(leader.address, CoordinatorStub, "SubmitDocument", request, timeout=40)
        except grpc.RpcError as error:
            state.events.observe(op, "leader_unreachable", leader=leader.id, error=error.code().name)
            state.cluster.poll_once()
            time.sleep(1.0)
            continue
        if reply.ok:
            state.events.observe(op, "leader_replied", leader=reply.coordinator_id, doc_id=reply.doc_id,
                                 node=reply.node_id, version=reply.version)
            return {"ok": True, "doc_id": reply.doc_id, "node_id": reply.node_id, "version": reply.version,
                    "coordinator_id": reply.coordinator_id, "epoch": reply.epoch}
        if reply.error in ("NOT_LEADER", "STALE_EPOCH"):
            state.cluster.poll_once()
            time.sleep(0.5)
            continue
        return {"ok": False, "error": reply.error}
    return {"ok": False, "error": "No leader is available. Start the cluster, or wait for the election to finish."}


@app.post("/api/admin/documents")
def add_documents(body: DocumentsBody) -> dict:
    tasks = [("url", url) for url in body.urls if url.strip()] + [("text", text) for text in body.texts]
    if not tasks:
        raise HTTPException(status_code=400, detail="Provide at least one URL or text document.")

    def process(task) -> dict:
        kind, payload = task
        op = f"doc-{uuid.uuid4().hex[:8]}"
        label = payload.strip() if kind == "url" else (payload.title or "text document")
        state.events.observe(op, "request_received", source=label, kind=kind)

        def report(name: str, **details) -> None:
            state.events.observe(op, name, **details)

        try:
            document = (state.builder.from_url(payload, report) if kind == "url"
                        else state.builder.from_text(payload.title, payload.content, payload.url, report))
        except IngestError as error:
            state.events.observe(op, "ingest_failed", error=str(error))
            return {"op": op, "source": label, "ok": False, "stage": "parse", "error": str(error)}
        outcome = submit_to_leader(document, op)
        return {"op": op, "source": label, "title": document["title"], "url": document["url"],
                "content_length": document["content_length"], "stage": "index", **outcome}

    # All documents are processed at the same time, so independent adds really are concurrent.
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        results = list(pool.map(process, tasks))
    return {"results": results}


# ---------------------------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Run the web server (search page, admin page, process control).")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    arguments = parser.parse_args()
    state.cfg = load_cluster_config(arguments.config)
    state.manager = ProcessManager(state.cfg)
    state.cluster = ClusterView(state.cfg, state.manager)
    app.mount("/", StaticFiles(directory=WEB_DIRECTORY, html=True), name="web")
    uvicorn.run(app, host=arguments.host or state.cfg.web_host, port=arguments.port or state.cfg.web_port,
                log_level="warning")


if __name__ == "__main__":
    main()
