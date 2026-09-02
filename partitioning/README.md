# Document Partitioner

This component converts the central parsed-document dataset into non-overlapping search-node shards.

## Run

From the repository root:

```powershell
python -m partitioning.partitioner.cli --config partitioning/config/partition_config.json
```

It uses sorted `document_id` values and range partitioning. With 30 documents and three shards, the output is ten documents per shard:

```text
data/shards/shard_1.jsonl  → document IDs 1–10
data/shards/shard_2.jsonl  → document IDs 11–20
data/shards/shard_3.jsonl  → document IDs 21–30
```

`data/shards/partition_manifest.json` records the global document count and each shard's range. This manifest is the source for `N_global` during later global-IDF construction.

The shard files are derived artifacts: every run atomically replaces them, avoiding duplicate records when documents are re-partitioned.
