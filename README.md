# Distributed Search Engine

An academic Python search engine with an offline document pipeline, shard-local gRPC search services, and a FastAPI coordinator serving a browser UI. The coordinator queries nodes concurrently, merges their local cosine TF-IDF candidates, and returns global Top-K results. A stopped or timed-out node reduces corpus coverage while the remaining nodes can still answer.

## Architecture and scope

The pipeline, gRPC services, concurrent fan-out/fan-in, ranking, RPC timeouts, HTTP API, and browser UI already existed. This extension adds thread-safe Lamport clocks, query-correlated traces, saved-index fingerprints, and authoritative index-generation diagnostics.

```text
ingestion_crawler -> data/raw/*.html + data/metadata.jsonl
parsing_html      -> data/documents.jsonl
partitioning      -> data/shards/shard_*.jsonl + partition_manifest.json
distributed_indexing -> data/indexes/nodes/node_*_index.json
                     + data/indexes/global_statistics.json

Browser --HTTP--> FastAPI / coordinator --concurrent gRPC--> search nodes
                   global Top-K merge <--- local candidates ---+
```

The partitioner sorts document IDs and splits them into non-overlapping ranges. Each search node loads its own shard documents and inverted index, plus shared global document frequencies/IDF values so scores use the same scale. The coordinator owns no inverted index. It requests at least `local_top_k` candidates per node, increasing that limit to the requested final Top-K when needed, then globally sorts accepted candidates by descending score, breaking ties by document ID. The default limits remain 20 candidates per node and 10 final results.

The separate `indexing/` and `local_search/` components provide a single-process reference path; they are not required before a distributed index build.

## Install and build

Use Python 3.10 or newer. From the repository root:

```powershell
python -m pip install -r requirements.txt
```

`requirements.txt` records the runtime and protobuf compiler versions used for this extension. Crawler, parser, partitioner, and index builder use the Python standard library.

If the corpus already exists, start at the appropriate stage below. Crawling requires internet access; review the configured domains, limits, and user agent in `ingestion_crawler/config/crawl_config.json` first.

```powershell
python -m ingestion_crawler.crawler.cli --config ingestion_crawler/config/crawl_config.json
python -m parsing_html.parser.cli --config parsing_html/config/parser_config.json
python -m partitioning.partitioner.cli --config partitioning/config/partition_config.json
python -m distributed_indexing.builder.cli --config distributed_indexing/config/distributed_index_config.json
```

Build indexes with this version before expecting verified consistency: older statistics files have no per-node hashes. Derived shard and index files are replaced on rebuild. Do not commit crawled HTML, generated documents/indexes, caches, or virtual environments.

## Start and search

Start the API/coordinator:

```powershell
python -m coordinator.api_server --config coordinator/config/coordinator_config.json --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) and use each node's **Start** button. These controls launch the default three local shard processes on ports 50051–50053 using the `data/` paths above.

Alternatively, run each node in its own terminal:

```powershell
python -m search_node.server --node-id node_1 --port 50051 --index data/indexes/nodes/node_1_index.json --shard data/shards/shard_1.jsonl --statistics data/indexes/global_statistics.json
python -m search_node.server --node-id node_2 --port 50052 --index data/indexes/nodes/node_2_index.json --shard data/shards/shard_2.jsonl --statistics data/indexes/global_statistics.json
python -m search_node.server --node-id node_3 --port 50053 --index data/indexes/nodes/node_3_index.json --shard data/shards/shard_3.jsonl --statistics data/indexes/global_statistics.json
```

Use one launch method per port. `/api/nodes` reports only the lifecycle of child processes launched through this API instance. A node started in a separate terminal can appear stopped in the controls even while its search RPC responds. Search diagnostics come from `/api/search`.

Search through the browser, CLI, or HTTP API:

```powershell
python -m coordinator.engine.cli "python data structures" --config coordinator/config/coordinator_config.json --top-k 10
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/search -Method Post -ContentType 'application/json' -Body '{"query":"python data structures","top_k":10}'
```

The CLI creates a coordinator process for that invocation. The API retains one coordinator and its logical clock across searches. Stop a node and repeat a query to see partial results and `rpc_failure_observed` in the trace; the default per-node RPC timeout is three seconds.

## Logical clocks

`distributed_systems/clock.py` implements a process-local clock starting at zero with locked updates. Local/send events increment it; receiving a timestamp performs `C = max(C, received_timestamp) + 1`. Coordinator fan-out workers share one clock, and each node process has its own clock. Physical latency still uses `time.perf_counter()`.

The additive protobuf fields carry a unique query `request_id`, coordinator send timestamp, node receive timestamp, and node response-send timestamp. `/api/search` and the CLI expose `logical_trace` events with request ID, process/node ID, event, and logical timestamp. Expand **Lamport trace** in **Query execution** to inspect a search. Successful exchanges satisfy:

```text
coordinator request_sent < node request_received < node response_sent < coordinator response_received
```

The trace is correlated to one query even when queries run concurrently. Logical clocks demonstrate the causal-order property: if event A causes B, A's timestamp is smaller. Smaller timestamps alone do not prove causality, and the displayed timestamp order is not a formal total causal order or a consistent global snapshot.

## Consistency and result policy

The builder hashes the actual saved index bytes with SHA-256 and stores each `index_hash` beside its node/shard mapping in `global_statistics.json`. The deterministic statistics generation includes those hashes and excludes its own `statistics_version` field. Identical shard input and indexing configuration produce the same artifacts/version; a change to saved index bytes changes its fingerprint.

At startup, each node hashes the exact index bytes it loads, compares them with its loaded statistics, and validates the loaded statistics generation against its canonical payload. A known inconsistent node returns diagnostics and an empty candidate list without scoring. The coordinator reads the configured authoritative statistics once per search, validates its generation fingerprint, then compares each response's version and index hash against that authority. The configuration field is `global_statistics_file`; the default `../data/indexes/global_statistics.json` resolves relative to `config_path.parent.parent`, namely `coordinator/` for the supplied config. The coordinator therefore sees rebuilt statistics on the next query without a restart. Nodes must be restarted to load rebuilt artifacts.

A locally matching old index/statistics pair can still be stale; its generation will disagree with the current authority. Known stale generations, invalid local hashes, or invalid node mappings are excluded from the merge. Missing metadata is explicitly **unverified**. If authority cannot be loaded or validated, otherwise usable responses are retained for compatibility and remain unverified; this favors availability without claiming verified cluster consistency. The coordinator never elects an authoritative version by majority vote.

Diagnostics retain existing fields and distinguish the following counts:

| Field | Meaning |
| --- | --- |
| `healthy_nodes` | Nodes whose RPC responded, including nodes whose results were excluded |
| `eligible_nodes` | Responding nodes whose results were accepted |
| `verified_nodes` | Nodes verified against local and authoritative metadata |
| `total_nodes` | Configured node count |
| `candidate_count` | Accepted candidates merged before final Top-K |
| `received_candidate_count` | All candidates received, including excluded ones |

Each `node_status` preserves `status` (`up`/`unavailable`), latency, candidate count, and statistics version. It adds `rpc_state`, `index_consistency`, `generation_consistency`, overall `consistency`, actual/local-expected/authority-expected hashes, `results_accepted`, and errors. The response also includes `expected_statistics_version` and `authority_error`. The sidebar displays these values with expandable fingerprints.

The checks describe the artifacts loaded at startup. Editing an index on disk does not alter a running node's in-memory index. The hashes are integrity fingerprints, not authentication. Shard document bytes are not fingerprinted by this extension. Publication of all index files plus statistics is not one cluster-wide atomic transaction; rebuild and restart nodes to make the generation current.

## Tests and demonstrations

Tests use standard-library `unittest`, temporary directories, and mocked or local services. No live crawling is needed:

```powershell
python -m unittest discover -s tests -v
python scripts/smoke_distributed_search.py
```

The smoke script builds a temporary corpus and starts two local gRPC services, avoiding changes to `data/`. It demonstrates normal retrieval and Lamport propagation, a timed-out node with partial results, a locally valid stale generation, and a mismatched local artifact. By default it also starts a temporary HTTP API process and checks search, node lifecycle reporting, static UI delivery, and request validation. Use `--skip-http` to run only the gRPC scenarios. Temporary data and services are cleaned up on exit; see its output for per-scenario diagnostics.

To demonstrate stale generations with your corpus, use copies of the shard/index/statistics files in a disposable directory and point the node arguments and coordinator config there. Start all nodes on generation A. Change the copied shard input, rebuild generation B, and restart nodes 1 and 2 on B while leaving node 3 running on A. Search again: node 3 still responds and can pass its local hash check, but reports a mismatching generation; its candidates are excluded while current nodes continue answering. Restart node 3 on B to restore full eligibility. The automated smoke script demonstrates equivalent stale-pair exclusion using separate temporary old/current fixtures.

To demonstrate a local mismatch, change only whitespace in a copied index JSON file after the build, leaving statistics unchanged, then restart the corresponding node. The JSON remains readable but its byte hash differs; the node is marked inconsistent and excluded. Rebuild and restart to recover. Use copies so the demonstration does not alter a working corpus.

Regenerate protobuf bindings after contract changes using the pinned compiler:

```powershell
python -m grpc_tools.protoc -I . --python_out=. --grpc_python_out=. proto/search.proto
```

## Syllabus mapping

| Topic | Project evidence |
| --- | --- |
| Unit III: Synchronization / Lamport clocks | Newly implemented locked logical clocks and gRPC causal traces |
| Unit III: Global state / cluster diagnostics | Newly implemented query-time RPC, artifact, and generation reporting; no formal consistent snapshot algorithm |
| Unit IV: Distributed web-based systems | Existing browser → HTTP coordinator → gRPC shard-service architecture, documented from source |
| Unit IV: Distributed database / consistency trade-offs | Newly implemented generation validation and rejection of known stale sources; availability versus unverifiable consistency is discussed |

Leader election/failover, vector clocks, distributed mutual exclusion, Chandy–Lamport snapshots, heartbeat monitoring, distributed file systems, Hadoop, Kubernetes deployment, serverless services, blockchains, cloud integrations, and messaging platforms are not implemented by this extension.

Component details: [coordinator](coordinator/README.md), [search nodes](search_node/README.md), and [distributed index build](distributed_indexing/README.md).
