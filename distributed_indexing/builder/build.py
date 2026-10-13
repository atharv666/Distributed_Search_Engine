"""Create node-local indexes, then aggregate globally comparable IDF values."""

import json
import math
from collections import defaultdict

from distributed_systems.integrity import sha256_bytes, statistics_version
from indexing.indexer.config import IndexConfig
from indexing.indexer.index_builder import build_index, save_index

from .config import DistributedIndexConfig


def build_distributed_indexes(config: DistributedIndexConfig) -> dict[str, object]:
    manifest = _read_json(config.partition_manifest)
    global_document_count = manifest["global_document_count"]
    if global_document_count < 1:
        raise ValueError("At least one document is required to build an index.")

    shard_ids = set()
    for shard in manifest["shards"]:
        shard_id = shard["shard_id"]
        if isinstance(shard_id, bool) or not isinstance(shard_id, int) or shard_id < 0:
            raise ValueError("Each shard ID must be a nonnegative integer.")
        if shard_id in shard_ids:
            raise ValueError(f"Duplicate shard ID {shard_id} in partition manifest.")
        shard_ids.add(shard_id)

    config.indexes_directory.mkdir(parents=True, exist_ok=True)
    global_df: dict[str, int] = defaultdict(int)
    node_indexes: list[dict[str, object]] = []
    for shard in manifest["shards"]:
        shard_id = shard["shard_id"]
        shard_file = config.shards_directory / shard["file"]
        index_file = config.indexes_directory / f"node_{shard_id}_index.json"
        local_config = IndexConfig(
            documents_file=shard_file, index_file=index_file,
            minimum_token_length=config.minimum_token_length, excluded_tokens=config.excluded_tokens,
        )
        local_index = build_index(local_config)
        if local_index["document_count"] != shard["document_count"]:
            raise ValueError(f"Shard {shard_id} document count does not match manifest.")
        save_index(local_index, index_file)
        index_hash = sha256_bytes(index_file.read_bytes())
        for term, entry in local_index["terms"].items():
            global_df[term] += entry["document_frequency"]
        node_indexes.append({"node_id": f"node_{shard_id}", "shard_id": shard_id, "file": index_file.name,
                             "document_count": local_index["document_count"], "index_hash": index_hash})

    statistics = {
        "format_version": 1,
        "global_document_count": global_document_count,
        "terms": {term: {"document_frequency": df, "idf": math.log(global_document_count / df)}
                  for term, df in sorted(global_df.items())},
        "node_indexes": node_indexes,
    }
    statistics["statistics_version"] = _statistics_version(statistics)
    _save_json(config.global_statistics_file, statistics)
    return statistics


def _statistics_version(statistics: dict[str, object]) -> str:
    return statistics_version(statistics)


def _read_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Partition manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(destination, value: dict[str, object]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(destination)
