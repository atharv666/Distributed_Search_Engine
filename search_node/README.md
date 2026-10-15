# Search node

Each node (`N1`, `N2`, `N3`) serves one shard (`data/shards/shard_<k>.jsonl`). It builds an in-memory inverted index at
start-up, keeps a full copy of the global statistics (N and document frequencies) and obeys the leader of the highest
epoch it has seen.

```powershell
python -m search_node.server --id N1 --config coordinator/config/cluster_config.json
```

## Messages (`NodeService`)

| RPC | Purpose |
|---|---|
| `Search` | Score the shard with the global IDF of every query term (so scores are comparable across nodes) and return the local top-K |
| `AddDocument` | Append the document to the shard file, index it, return its unique terms |
| `ApplyStatistics` | Apply ordered statistics deltas, then recompute every document norm. A gap in versions is reported so the leader can resend |
| `Heartbeat` | The leader's beacon. The reply carries the node's statistics version so the leader can push missing deltas |
| `Announce` | A new leader announces its epoch |
| `GetStatus` | Observer query for the admin page |

Commands from an older epoch are rejected (`stale`). If no beacon arrives for 3 beats the node reports the leader as
suspected to every coordinator (`ReportSuspect`).

Applied deltas are appended to `data/state/<id>_deltas.jsonl`; on restart the node replays them, and the leader pushes any
it missed.
