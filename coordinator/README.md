# Coordinator

The coordinator contains no inverted index. It sends one query concurrently to every configured gRPC search node, waits only up to the configured per-node timeout, and globally sorts the successful nodes' local Top-K candidates.

Run a query from the repository root after starting the three search nodes:

```powershell
python -m coordinator.engine.cli "python data structures" --config coordinator/config/coordinator_config.json
```

It returns normal results and distributed diagnostics: each node's status, latency, candidate count, the combined candidate count, and end-to-end elapsed time. If a node is stopped, its timeout is recorded and results from healthy shards are still returned.

The coordinator takes `local_top_k` candidates from each node and returns `final_top_k` globally. `local_top_k` must be at least `final_top_k` to preserve correct global Top-K retrieval.
