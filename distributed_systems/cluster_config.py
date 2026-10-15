"""Cluster layout and timing shared by every process."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CoordinatorEntry:
    id: str
    address: str

    @property
    def rank(self) -> int:
        """Bully priority: C3 outranks C2 outranks C1."""
        return int(self.id[1:])


@dataclass(frozen=True)
class NodeEntry:
    id: str
    address: str
    shard: int


@dataclass(frozen=True)
class ClusterConfig:
    path: Path
    data_directory: Path
    web_host: str
    web_port: int
    coordinators: tuple[CoordinatorEntry, ...]
    nodes: tuple[NodeEntry, ...]
    heartbeat_interval: float      # seconds between beacons
    missed_beats_limit: int        # silent beats tolerated before the leader is suspected
    rpc_timeout: float
    election_wait: float           # how long a candidate waits for the winner's announcement
    boot_grace: float              # a booting coordinator waits this long for its peers
    local_top_k: int
    final_top_k: int

    @property
    def beat_timeout(self) -> float:
        return self.heartbeat_interval * self.missed_beats_limit

    @property
    def event_sink_url(self) -> str:
        host = "127.0.0.1" if self.web_host in ("0.0.0.0", "") else self.web_host
        return f"http://{host}:{self.web_port}/internal/events"

    def coordinator(self, process_id: str) -> CoordinatorEntry:
        return next(entry for entry in self.coordinators if entry.id == process_id)

    def node(self, process_id: str) -> NodeEntry:
        return next(entry for entry in self.nodes if entry.id == process_id)

    def peers_of(self, process_id: str) -> tuple[CoordinatorEntry, ...]:
        return tuple(entry for entry in self.coordinators if entry.id != process_id)

    def process_ids(self) -> list[str]:
        return [entry.id for entry in self.coordinators] + [entry.id for entry in self.nodes]


def load_cluster_config(config_path: Path) -> ClusterConfig:
    """Relative paths in the file resolve from the folder that contains it."""
    config_path = Path(config_path).resolve()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    coordinators = tuple(CoordinatorEntry(item["id"], item["address"]) for item in data["coordinators"])
    nodes = tuple(NodeEntry(item["id"], item["address"], int(item["shard"])) for item in data["nodes"])
    if not coordinators or not nodes:
        raise ValueError("At least one coordinator and one node are required.")
    if len({entry.id for entry in coordinators + nodes}) != len(coordinators) + len(nodes):
        raise ValueError("Process IDs must be unique.")
    if any(node.id != f"N{node.shard}" for node in nodes):
        raise ValueError("Node IDs must be N<shard>, for example N1 for shard 1.")
    timing = data["timing"]
    config = ClusterConfig(
        path=config_path,
        data_directory=(config_path.parent / data["data_directory"]).resolve(),
        web_host=data["web"]["host"], web_port=int(data["web"]["port"]),
        coordinators=coordinators, nodes=nodes,
        heartbeat_interval=float(timing["heartbeat_interval_seconds"]),
        missed_beats_limit=int(timing["missed_beats_before_suspect"]),
        rpc_timeout=float(timing["rpc_timeout_seconds"]),
        election_wait=float(timing["election_wait_seconds"]),
        boot_grace=float(timing["boot_grace_seconds"]),
        local_top_k=int(data["search"]["local_top_k"]), final_top_k=int(data["search"]["final_top_k"]),
    )
    if config.heartbeat_interval <= 0 or config.missed_beats_limit < 1 or config.local_top_k < config.final_top_k:
        raise ValueError("Invalid timing or top-k settings.")
    return config
