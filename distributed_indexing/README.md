# Distributed Index Build

This offline component turns document shards into the actual distributed index layout.

```text
data/shards/shard_1.jsonl → data/indexes/nodes/node_1_index.json
data/shards/shard_2.jsonl → data/indexes/nodes/node_2_index.json
data/shards/shard_3.jsonl → data/indexes/nodes/node_3_index.json
                              ↓
                    data/indexes/global_statistics.json
```

Each node index contains postings, local term frequencies, positions, document lengths, and document norms for only that node's shard. The shared statistics file aggregates global document frequencies and computes global IDF values. Future search nodes load their own index plus this shared file, giving every result the same scoring scale.

Run from the repository root:

```powershell
python -m distributed_indexing.builder.cli --config distributed_indexing/config/distributed_index_config.json
```
