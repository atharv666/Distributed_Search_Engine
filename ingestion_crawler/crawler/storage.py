"""Persistence for untouched HTML response bytes and JSONL metadata."""

import json
from datetime import datetime, timezone
from pathlib import Path


class CrawlStorage:
    def __init__(self, raw_directory: Path, metadata_file: Path) -> None:
        self.raw_directory = raw_directory
        self.metadata_file = metadata_file
        raw_directory.mkdir(parents=True, exist_ok=True)
        metadata_file.parent.mkdir(parents=True, exist_ok=True)

    def next_document_id(self) -> int:
        return len(list(self.raw_directory.glob("*.html"))) + 1

    def previously_crawled_urls(self) -> set[str]:
        """Return URLs from earlier successful crawl records, if any.

        Both the requested URL and the final URL after redirects are retained so
        a future run does not re-fetch either spelling of the same saved page.
        Malformed historic lines are ignored rather than blocking a new crawl.
        """
        if not self.metadata_file.exists():
            return set()

        urls: set[str] = set()
        with self.metadata_file.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for key in ("url", "requested_url"):
                    value = record.get(key)
                    if isinstance(value, str):
                        urls.add(value)
        return urls

    def save(self, document_id: int, body: bytes, metadata: dict[str, object]) -> Path:
        filename = f"{document_id:06d}.html"
        destination = self.raw_directory / filename
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite raw file: {destination}")
        destination.write_bytes(body)
        record = {
            "document_id": document_id,
            "file": f"raw/{filename}",
            "crawled_at": datetime.now(timezone.utc).isoformat(),
            **metadata,
        }
        with self.metadata_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        return destination
