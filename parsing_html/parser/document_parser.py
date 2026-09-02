"""Convert crawled raw HTML files and metadata records into logical documents."""

import logging
from pathlib import Path

from .config import ParserConfig
from .html_extractor import decode_html_bytes, extract_document_fields
from .storage import append_document, existing_document_ids, read_metadata

LOGGER = logging.getLogger(__name__)


class DocumentParser:
    def __init__(self, config: ParserConfig) -> None:
        self.config = config

    def parse_all(self) -> int:
        parsed_ids = existing_document_ids(self.config.documents_file)
        added = 0
        for metadata in read_metadata(self.config.metadata_file):
            document_id = metadata["document_id"]
            if document_id in parsed_ids:
                continue
            raw_file = self.config.raw_directory / Path(metadata["file"]).name
            if not raw_file.exists():
                LOGGER.warning("raw HTML file missing for document %s: %s", document_id, raw_file)
                continue
            title, content = extract_document_fields(decode_html_bytes(raw_file.read_bytes()))
            if len(content) < self.config.minimum_content_characters:
                LOGGER.info("skipping short document %s (%d characters)", document_id, len(content))
                continue
            document = {
                "document_id": document_id,
                "title": title or metadata["url"],
                "url": metadata["url"],
                "source": metadata.get("source"),
                "crawl_depth": metadata.get("crawl_depth"),
                "raw_file": metadata["file"],
                "content": content,
                "content_length": len(content),
            }
            append_document(self.config.documents_file, document)
            parsed_ids.add(document_id)
            added += 1
            LOGGER.info("parsed document %s: %s", document_id, document["title"])
        return added
