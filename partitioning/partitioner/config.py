"""Load partitioning configuration."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PartitionConfig:
    documents_file: Path
    output_directory: Path
    shard_count: int
    strategy: str


def load_config(config_path: Path) -> PartitionConfig:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    component_directory = config_path.parent.parent
    if data["shard_count"] < 1:
        raise ValueError("shard_count must be at least 1.")
    if data["strategy"] != "range":
        raise ValueError("Only the range partitioning strategy is currently supported.")
    return PartitionConfig(
        documents_file=component_directory / data["documents_file"],
        output_directory=component_directory / data["output_directory"],
        shard_count=int(data["shard_count"]), strategy=data["strategy"],
    )
