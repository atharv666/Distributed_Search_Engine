"""Load coordinator node and query settings."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NodeAddress:
    node_id: str
    address: str


@dataclass(frozen=True)
class CoordinatorConfig:
    nodes: tuple[NodeAddress, ...]
    node_timeout_seconds: float
    local_top_k: int
    final_top_k: int


def load_config(config_path: Path) -> CoordinatorConfig:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    nodes = tuple(NodeAddress(**node) for node in data["nodes"])
    if not nodes or data["node_timeout_seconds"] <= 0 or data["local_top_k"] < data["final_top_k"]:
        raise ValueError("Nodes/timeout must be valid and local_top_k must be at least final_top_k.")
    return CoordinatorConfig(nodes, float(data["node_timeout_seconds"]), int(data["local_top_k"]), int(data["final_top_k"]))
