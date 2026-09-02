"""Configuration for the distributed indexing build."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DistributedIndexConfig:
    shards_directory: Path
    partition_manifest: Path
    indexes_directory: Path
    global_statistics_file: Path
    minimum_token_length: int
    excluded_tokens: frozenset[str]


def load_config(config_path: Path) -> DistributedIndexConfig:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    root = config_path.parent.parent
    if data["minimum_token_length"] < 1:
        raise ValueError("minimum_token_length must be at least 1.")
    return DistributedIndexConfig(
        shards_directory=root / data["shards_directory"], partition_manifest=root / data["partition_manifest"],
        indexes_directory=root / data["indexes_directory"], global_statistics_file=root / data["global_statistics_file"],
        minimum_token_length=int(data["minimum_token_length"]),
        excluded_tokens=frozenset(token.casefold() for token in data["excluded_tokens"]),
    )
