"""Temporary fixtures and loopback services; never use repository search data."""

import hashlib
import json
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import grpc

from distributed_indexing.builder.build import build_distributed_indexes
from distributed_indexing.builder.config import DistributedIndexConfig
from partitioning.partitioner.config import PartitionConfig
from partitioning.partitioner.partitioner import partition_documents
from proto import search_pb2, search_pb2_grpc


def version_for(statistics):
    payload = {key: value for key, value in statistics.items() if key != "statistics_version"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def write_statistics(path, statistics):
    statistics["statistics_version"] = version_for(statistics)
    Path(path).write_text(json.dumps(statistics), encoding="utf-8")
    return statistics["statistics_version"]


def authority_statistics(hashes):
    statistics = {
        "format_version": 1,
        "global_document_count": len(hashes),
        "terms": {},
        "node_indexes": [
            {"node_id": node_id, "shard_id": ordinal, "file": f"node_{ordinal}_index.json",
             "document_count": 1, "index_hash": index_hash}
            for ordinal, (node_id, index_hash) in enumerate(hashes.items(), 1)
        ],
    }
    statistics["statistics_version"] = version_for(statistics)
    return statistics


def response_for(request, configured_node_id, loaded_version, saved_index_hash, documents=(), **overrides):
    fields = {
        "node_id": configured_node_id,
        "statistics_version": loaded_version,
        "request_id": request.request_id,
        "request_received_timestamp": request.logical_timestamp + 1,
        "response_sent_timestamp": request.logical_timestamp + 2,
        "index_hash": saved_index_hash,
        "expected_index_hash": saved_index_hash,
        "index_consistency": "consistent",
        "results": [search_pb2.SearchResult(document_id=document_id, score=score, node_id=configured_node_id,
                                             title=f"Document {document_id}", url=f"https://example.test/{document_id}",
                                             snippet=request.query)
                    for document_id, score in documents],
    }
    fields.update(overrides)
    return search_pb2.SearchResponse(**fields)


@contextmanager
def mocked_nodes(responders):
    """Replace the transport while keeping real coordinator request/clock logic."""
    class Channel:
        def __init__(self, address):
            self.address = address

        def __enter__(self):
            return self

        def __exit__(self, *arguments):
            return False

    class Stub:
        def __init__(self, channel):
            self.address = channel.address

        def Search(self, request, timeout):
            return responders[self.address](request, timeout)

    with patch("coordinator.engine.coordinator.grpc.insecure_channel", side_effect=Channel), \
            patch("coordinator.engine.coordinator.search_pb2_grpc.SearchServiceStub", Stub):
        yield


class DeadlineExceeded(grpc.RpcError):
    def code(self):
        return grpc.StatusCode.DEADLINE_EXCEEDED


def build_fixture(directory, contents=None):
    """Build deterministic, tiny two-node indexes from temporary parsed documents."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    contents = contents or ["clock clock synchronization", "consistency metadata", "clock search", "web grpc service"]
    documents_file = directory / "documents.jsonl"
    documents = [{"document_id": ordinal, "title": f"Document {ordinal}",
                  "url": f"https://example.test/{ordinal}", "content": content}
                 for ordinal, content in enumerate(contents, 1)]
    documents_file.write_text("".join(json.dumps(document) + "\n" for document in documents), encoding="utf-8")
    shards = directory / "shards"
    indexes = directory / "nodes"
    statistics_path = directory / "global_statistics.json"
    partition_documents(PartitionConfig(documents_file, shards, 2, "range"))
    statistics = build_distributed_indexes(DistributedIndexConfig(
        shards, shards / "partition_manifest.json", indexes, statistics_path, 2, frozenset()))
    return {"directory": directory, "shards": shards, "indexes": indexes,
            "statistics_path": statistics_path, "statistics": statistics}


def service_for(fixture, ordinal):
    from search_node.server import Service
    return Service(f"node_{ordinal}", fixture["indexes"] / f"node_{ordinal}_index.json",
                   fixture["shards"] / f"shard_{ordinal}.jsonl", fixture["statistics_path"])


@contextmanager
def running_node(service):
    """Run an actual gRPC node on an OS-assigned loopback port."""
    workers = ThreadPoolExecutor(max_workers=4)
    server = grpc.server(workers)
    search_pb2_grpc.add_SearchServiceServicer_to_server(service, server)
    port = server.add_insecure_port("127.0.0.1:0")
    if not port:
        raise RuntimeError("Could not bind a local gRPC test port.")
    server.start()
    address = f"127.0.0.1:{port}"
    try:
        with grpc.insecure_channel(address) as channel:
            grpc.channel_ready_future(channel).result(timeout=5)
        yield address
    finally:
        server.stop(0).wait(timeout=5)
        workers.shutdown(wait=True)
