# Ingestion Crawler

This component downloads a controlled corpus of public technology documentation as raw HTML. It does not parse pages into search documents or build an index.

## Run

From the repository root:

```powershell
python -m ingestion_crawler.crawler.cli --config ingestion_crawler/config/crawl_config.json
```

Review `config/crawl_config.json` before every crawl. It defines seed URLs, allowed domains, limits, delay, user agent, and output paths.

## Output contract

The crawler saves byte-for-byte HTTP response bodies in the shared project data area:

```text
data/raw/000001.html
data/raw/000002.html
data/metadata.jsonl
```

Each successful page produces one JSONL metadata record with its document ID, source URL, requested URL, source label, crawl depth, content type, timestamp, and raw file path. The future parser should read these files and create logical documents without altering the raw originals.

## Safety boundaries

- Only configured domains are visited.
- `robots.txt` is checked per origin; an unavailable robots file causes that origin to be skipped.
- Only `text/html` responses are retained.
- Breadth-first traversal stops at `max_pages` or `max_depth`.
- Existing raw files are never overwritten.
- URLs in existing `data/metadata.jsonl` are loaded at startup, preventing
  successful pages from being downloaded again in later runs.
