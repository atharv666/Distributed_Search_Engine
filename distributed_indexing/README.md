# Distributed Index Build

This offline component turns document shards into the actual distributed index layout.

```text
data/shards/shard_1.jsonl → data/indexes/nodes/node_1_index.json
data/shards/shard_2.jsonl → data/indexes/nodes/node_2_index.json
data/shards/shard_3.jsonl → data/indexes/nodes/node_3_index.json
                              ↓
                    data/indexes/global_statistics.json
```

Each node index contains postings, local term frequencies, positions, document lengths, and document norms for only that node's shard. The shared statistics file aggregates global document frequencies and computes global IDF values. Search nodes load their own index plus this shared file, giving every result the same scoring scale.

Run from the repository root:

```powershell
python -m distributed_indexing.builder.cli --config distributed_indexing/config/distributed_index_config.json
```

Build the parsed documents and partitions first if absent:

```powershell
python -m parsing_html.parser.cli --config parsing_html/config/parser_config.json
python -m partitioning.partitioner.cli --config partitioning/config/partition_config.json
```

Parsing expects crawler metadata/raw HTML; see the [root README](../README.md) for the full pipeline. A separate central `indexing` build is not required here. Relative paths in the distributed config resolve from `config_path.parent.parent`, namely `distributed_indexing/` for the supplied config.

## Saved-artifact fingerprints

This extension adds `index_hash` to each `node_indexes` entry in `global_statistics.json`. The builder saves the node-local index first and hashes the actual saved bytes with SHA-256. It preserves the node ID, shard ID, filename, and document-count fields. Node/shard/filename mappings must agree and be unambiguous.

The statistics generation is the first 16 hexadecimal characters of SHA-256 over canonical JSON (`sort_keys=True`, compact separators), excluding the derived `statistics_version` field itself. The payload includes node-index fingerprints, so index-content changes affect the generation without a circular hash. This is an integrity/version fingerprint, not an authentication mechanism.

With identical shard content and indexing settings, saved indexes and statistics versions are deterministic. The partition manifest's physical creation timestamp is not part of the statistics payload. File formatting affects the exact-byte index hash, even when JSON parses to the same values.

## Publish and restart

Node indexes and statistics are individually replaced atomically, with statistics written after the index files. Their publication is not a cluster-wide atomic transaction. Search nodes load artifacts at startup, while the coordinator rereads and validates authoritative statistics once per query. Restart nodes after a rebuild to make their loaded generation current.

Old statistics without expected node hashes remain unverified. Rebuild using this version before demonstrating verified consistency. A stale node whose old local index still matches its old statistics is detected by the coordinator's authoritative generation comparison. Its candidates are excluded while current nodes can still return partial results.

Run ordinary tests and the no-crawl demo, which build temporary artifacts rather than altering project data:

```powershell
python -m unittest discover -s tests -v
python scripts/smoke_distributed_search.py
```

Do not commit generated index or corpus files. See the [root README](../README.md#tests-and-demonstrations) for demonstration steps and consistency limitations.
