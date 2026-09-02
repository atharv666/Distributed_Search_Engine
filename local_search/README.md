# Local Search

This is a small single-process reference search path. It validates the same tokenization, inverted-index layout, TF-IDF scoring, and result retrieval that later search nodes will use.

## Run

First rebuild the index after changing its schema or parsed documents:

```powershell
python -m indexing.indexer.cli --config indexing/config/index_config.json
```

Then search:

```powershell
python -m local_search.engine.cli "python data structures" --config local_search/config/search_config.json
```

For each result the command returns the document ID, cosine TF-IDF score, title, source URL, and a short snippet. It does not modify source documents or raw HTML.
