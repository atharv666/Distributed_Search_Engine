# Coordinator

The existing coordinator contains no inverted index. `SearchCoordinator` uses a thread pool to send one query concurrently to every configured gRPC node with a per-RPC timeout, collects responding nodes' candidates, and returns global Top-K sorted by descending score and document ID. Known inconsistent responses are now excluded; otherwise useful partial results still return when a node is unavailable.

Run from the repository root after building indexes and starting nodes (see the [root README](../README.md)):

```powershell
python -m coordinator.engine.cli "python data structures" --config coordinator/config/coordinator_config.json --top-k 10
python -m coordinator.api_server --config coordinator/config/coordinator_config.json --host 127.0.0.1 --port 8000
```

The second command serves the browser UI at [http://127.0.0.1:8000](http://127.0.0.1:8000) and `/api/search`. HTTP search example:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/search -Method Post -ContentType 'application/json' -Body '{"query":"python data structures","top_k":10}'
```

## Configuration and authority

`coordinator/config/coordinator_config.json` configures node IDs/addresses, a three-second timeout, `local_top_k: 20`, `final_top_k: 10`, and `global_statistics_file: "../data/indexes/global_statistics.json"`. Relative statistics paths resolve from `config_path.parent.parent`, so the supplied path reaches repository `data/indexes/global_statistics.json`. No machine-specific path is needed.

Configured `local_top_k` must be at least configured `final_top_k`. A CLI/API Top-K override increases the per-node request limit to `max(local_top_k, requested_top_k)`, preserving global Top-K coverage.

The coordinator loads one authoritative statistics generation per query and validates `statistics_version` against the canonical payload. It never guesses the authority from a majority of nodes. A successful rebuild is visible on the next query without restarting the API. Search nodes hold their startup data and must be restarted to load that rebuild.

Known stale generations, mismatched local/authoritative index hashes, invalid metadata mappings, or invalid response correlation are excluded. If authority or required verification metadata is missing, consistency is `unverified`; otherwise usable results are retained for compatibility. Malformed authority/version produces `authority_error`, and no node is reported cluster-verified from that authority. This explicitly trades verified consistency for availability when verification is impossible.

## Diagnostics

`/api/search` and the CLI preserve query, results, node statuses, elapsed milliseconds, and original counters, while adding:

| Field | Meaning |
| --- | --- |
| `healthy_nodes` | RPC responders, even when their candidates are excluded |
| `eligible_nodes` | Responders whose results are accepted |
| `verified_nodes` | Sources verified against both local and authoritative metadata |
| `total_nodes` | Number of configured nodes |
| `candidate_count` | Accepted candidates merged before final Top-K |
| `received_candidate_count` | All returned candidates, including excluded candidates |
| `expected_statistics_version` | Authoritative version, or `null` when unavailable/invalid |
| `authority_error` | Authority loading/validation explanation, or `null` |

Per-node `status` retains `up`/`unavailable` RPC semantics. `rpc_state` states `responding`/`unavailable`; `index_consistency` is `consistent`/`inconsistent`/`unverified`; `generation_consistency` is `matching`/`mismatching`/`unverified`. Overall `consistency` combines those checks. Hashes, `statistics_version`, `results_accepted`, `merged_candidate_count`, and errors explain exclusions. `latency_ms` measures the gRPC exchange using `time.perf_counter()`, independently of the logical clock.

`/api/nodes` remains a lifecycle endpoint for subprocesses started through this API instance. It does not perform a search RPC or validate index generations. Externally launched nodes can appear stopped there while responding to searches. Query-time cluster diagnostics are in `/api/search`.

## Lamport tracing

One locked `LamportClock` is shared across coordinator workers and searches. Each query owns a unique `request_id` and a separate locked trace. Outgoing requests carry a send tick; responses update the coordinator using `max(local, node_send) + 1`. RPC failures receive a local tick even without a node response. Correlation checks associate responses with the configured node and current query.

`logical_trace` records `request_id`, `process_id`, `node_id`, `event`, and `logical_timestamp`. Events include search start/completion, request send/receipt, response send/receipt, RPC failure observation, and response rejection when applicable. Expand **Lamport trace** in the sidebar or inspect CLI JSON. Concurrent searches can interleave clock values while their traces remain separate.

For an individual successful RPC, send < node receipt < node send < coordinator receipt. Sorting timestamps is a presentation order; timestamp comparison alone does not prove a causal relationship or create a formal consistent global snapshot. A one-shot CLI invocation starts a new process/clock, while the API retains its clock across searches.

Run the tests and temporary-data demonstrations with:

```powershell
python -m unittest discover -s tests -v
python scripts/smoke_distributed_search.py
```

See the [root README](../README.md#tests-and-demonstrations) for stale-generation and local-mismatch demonstrations and limitations.
