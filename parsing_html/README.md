# HTML Parser

This component converts crawler output into logical documents without modifying raw HTML.

## Run

From the repository root:

```powershell
python -m parsing_html.parser.cli --config parsing_html/config/parser_config.json
```

It reads `data/metadata.jsonl` and the matching files in `data/raw/`, removes HTML markup and common page noise (`script`, `style`, navigation, footer, etc.), extracts a title, and appends logical records to `data/documents.jsonl`.

The parser preserves the crawler-assigned `document_id`. It is idempotent: document IDs already present in `documents.jsonl` are skipped on later runs, while newly crawled raw pages are added.
