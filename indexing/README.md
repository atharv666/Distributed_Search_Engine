# Indexing

This component turns parsed logical documents into a positional inverted index.

## Run

From the repository root:

```powershell
python -m indexing.indexer.cli --config indexing/config/index_config.json
```

## Flow

`tokenizer.py` lowercases text using Unicode case-folding and extracts word tokens, retaining forms such as `object-oriented` and `user's`. `index_builder.py` records each token's document ID, frequency, and zero-based token positions.

The resulting `data/indexes/base_inverted_index.json` is a derived artifact. It is fully rebuilt and atomically replaced each time, so updated parsed documents are included without duplicate postings.

Example term entry:

```json
"python": {
  "document_frequency": 20,
  "postings": [
    {"document_id": 1, "term_frequency": 8, "positions": [0, 47, 90]}
  ]
}
```
