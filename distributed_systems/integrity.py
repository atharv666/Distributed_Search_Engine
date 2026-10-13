"""Deterministic generation fingerprints and node-index metadata validation."""

import hashlib
import json
import re


def sha256_bytes(data: bytes) -> str:
    """Fingerprint the exact index bytes saved by the builder or loaded by a node."""
    return hashlib.sha256(data).hexdigest()


def statistics_version(statistics: dict[str, object]) -> str:
    """Hash the statistics payload without its own derived version field."""
    payload = {key: value for key, value in statistics.items() if key != "statistics_version"}
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(serialized)[:16]


def index_metadata(statistics: dict[str, object], node_id: str) -> tuple[str, str, str]:
    """Return (expected hash, metadata state, explanation) for one node.

    A consistent metadata state means that the mapping and expected hash are
    well formed. The caller still compares that expected hash with actual bytes.
    Missing metadata cannot verify an index; malformed or ambiguous mappings
    must never be used to identify an expected artifact.
    """
    if not isinstance(statistics, dict):
        return "", "inconsistent", "Global statistics must be a JSON object."
    entries = statistics.get("node_indexes")
    if entries is None:
        return "", "unverified", "Global statistics contain no node_indexes metadata."
    if not isinstance(entries, list):
        return "", "inconsistent", "node_indexes metadata must be a list."

    nodes, shards, files = set(), set(), set()
    selected = None
    for entry in entries:
        if not isinstance(entry, dict):
            return "", "inconsistent", "Each node_indexes entry must be an object."
        shard_id = entry.get("shard_id")
        if isinstance(shard_id, bool) or not isinstance(shard_id, int) or shard_id < 0:
            return "", "inconsistent", "Each index must have a nonnegative integer shard_id."
        expected_node = f"node_{shard_id}"
        expected_file = f"{expected_node}_index.json"
        if entry.get("node_id") != expected_node or entry.get("file") != expected_file:
            return "", "inconsistent", "Node ID, shard ID and index filename mapping do not agree."
        if expected_node in nodes or shard_id in shards or expected_file in files:
            return "", "inconsistent", "Duplicate node or shard index metadata is ambiguous."
        nodes.add(expected_node)
        shards.add(shard_id)
        files.add(expected_file)
        if expected_node == node_id:
            selected = entry

    if selected is None:
        return "", "unverified", f"No index metadata found for {node_id}."
    expected_hash = selected.get("index_hash")
    if expected_hash is None or expected_hash == "":
        return "", "unverified", f"No expected index hash found for {node_id}."
    if not isinstance(expected_hash, str) or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
        return "", "inconsistent", f"Expected index hash for {node_id} is not a SHA-256 hexadecimal digest."
    return expected_hash, "consistent", ""
