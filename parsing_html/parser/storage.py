"""Read crawler metadata and persist logical documents as JSON Lines."""

import json
from pathlib import Path


def read_metadata(metadata_file: Path) -> list[dict[str, object]]:
    if not metadata_file.exists():
        raise FileNotFoundError(f"Crawler metadata not found: {metadata_file}")
    records: list[dict[str, object]] = []
    with metadata_file.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid metadata line {line_number}") from error
            if not isinstance(record.get("document_id"), int) or not isinstance(record.get("file"), str):
                raise ValueError(f"Metadata line {line_number} lacks document_id or file.")
            records.append(record)
    return records


def existing_document_ids(documents_file: Path) -> set[int]:
    if not documents_file.exists():
        return set()
    ids: set[int] = set()
    with documents_file.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                document_id = json.loads(line).get("document_id")
            except json.JSONDecodeError:
                continue
            if isinstance(document_id, int):
                ids.add(document_id)
    return ids


def append_document(documents_file: Path, document: dict[str, object]) -> None:
    documents_file.parent.mkdir(parents=True, exist_ok=True)
    with documents_file.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(document, ensure_ascii=False) + "\n")
