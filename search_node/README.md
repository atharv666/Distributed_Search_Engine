# Search Node

Run one independent process per shard. Example for Node 1:

```powershell
python -m search_node.server --node-id node_1 --port 50051 --index data/indexes/nodes/node_1_index.json --shard data/shards/shard_1.jsonl --statistics data/indexes/global_statistics.json
```

Use ports `50052`/`50053` and the matching index/shard files for Nodes 2 and 3. Each node loads only its own shard-local index and documents, then calculates local cosine TF-IDF scores using the shared global statistics file.
