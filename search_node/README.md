# Search Node

Each existing gRPC service loads one shard's documents and inverted index, plus shared global IDF statistics. It scores the requested query locally with cosine TF-IDF and sends local Top-K candidates to the coordinator. Ranking and tokenization remain the existing search behavior.

Run one independent process per shard from the repository root. Example for Node 1:

```powershell
python -m search_node.server --node-id node_1 --port 50051 --index data/indexes/nodes/node_1_index.json --shard data/shards/shard_1.jsonl --statistics data/indexes/global_statistics.json
```

Use ports `50052`/`50053`, node IDs `node_2`/`node_3`, and matching index/shard files for Nodes 2 and 3. Index, shard, and statistics files are required at startup. The browser API's Start/Stop controls launch this same module with the default paths. Do not start two services on the same port.

## Index and generation diagnostics

At startup the service reads the index bytes once, computes their SHA-256 hash, and parses those same bytes. It checks the expected `index_hash` in the loaded statistics, including the node/shard/filename mapping, and validates the loaded statistics version against its canonical payload. The response includes actual and expected hashes, loaded `statistics_version`, `index_consistency`, and an explanation when verification fails.

| State | Local meaning |
| --- | --- |
| `consistent` | Valid generation/mapping metadata and matching loaded-index hash |
| `inconsistent` | Known invalid/mismatched index hash, statistics generation, or malformed/ambiguous mapping |
| `unverified` | Required expected hash or statistics version is missing |

A known inconsistent service skips scoring and returns an empty candidate list with diagnostics and logical timestamps. A locally consistent index/statistics pair can still be stale. The coordinator separately checks the returned version and hash against its current authoritative statistics and excludes known stale or inconsistent sources. Missing authority does not imply successful verification.

The node retains its loaded shard, index, statistics, and hashes until restart. Changing files on disk does not change a running service's in-memory artifacts; rebuild and restart to load a new generation. These fingerprints detect index-artifact mismatches, not ongoing filesystem changes or modified shard-document bytes. Invalid JSON can prevent startup instead of yielding an RPC diagnostic, and valid scoring terms are required for usable searches.

## Lamport exchange

Each service process has a locked logical clock starting at zero. On request receipt it applies `max(local, incoming_timestamp) + 1`, then ticks again before sending its response. The additive protobuf fields return the request ID, receipt timestamp, and response-send timestamp alongside the existing results and node/version fields. Concurrent gRPC handlers share the service clock; no physical clock synchronization is required.

Successful node events appear in the coordinator's query-specific `logical_trace`. The node does not expose a separate heartbeat endpoint or implement a formal distributed snapshot.

Reproducible temporary-data verification:

```powershell
python -m unittest discover -s tests -v
python scripts/smoke_distributed_search.py
```

See the [root README](../README.md#tests-and-demonstrations) for how to keep one node on an old generation, restart it, or demonstrate a readable index file with mismatched bytes.
