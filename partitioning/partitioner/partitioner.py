"""Range-partition parsed documents and produce a shard manifest."""

import json
from datetime import datetime, timezone

from .config import PartitionConfig


def partition_documents(config: PartitionConfig) -> dict[str, object]:
    documents = _read_documents(config.documents_file)
    documents.sort(key=lambda document: document["document_id"])
    _validate_unique_ids(documents)

    config.output_directory.mkdir(parents=True, exist_ok=True)
    base_size, remainder = divmod(len(documents), config.shard_count)
    offset = 0
    shard_records: list[dict[str, object]] = []

    for shard_id in range(1, config.shard_count + 1):
        size = base_size + (1 if shard_id <= remainder else 0)
        shard_documents = documents[offset:offset + size]
        offset += size
        output_file = config.output_directory / f"shard_{shard_id}.jsonl"
        _write_shard(output_file, shard_documents, shard_id)
        document_ids = [document["document_id"] for document in shard_documents]
        shard_records.append({
            "shard_id": shard_id,
            "file": output_file.name,
            "document_count": len(shard_documents),
            "document_id_start": min(document_ids) if document_ids else None,
            "document_id_end": max(document_ids) if document_ids else None,
        })

    manifest = {
        "format_version": 1,
        "strategy": config.strategy,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "global_document_count": len(documents),
        "shards": shard_records,
    }
    _write_json_atomically(config.output_directory / "partition_manifest.json", manifest)
    return manifest


def _read_documents(documents_file):
    if not documents_file.exists():
        raise FileNotFoundError(f"Parsed documents not found: {documents_file}")
    documents = []
    with documents_file.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                document = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON document on line {line_number}") from error
            if not isinstance(document.get("document_id"), int):
                raise ValueError(f"Document on line {line_number} has no integer document_id.")
            documents.append(document)
    return documents


def _validate_unique_ids(documents) -> None:
    identifiers = [document["document_id"] for document in documents]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("documents.jsonl contains duplicate document IDs.")


def _write_shard(destination, documents, shard_id: int) -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for document in documents:
            stream.write(json.dumps({**document, "shard_id": shard_id}, ensure_ascii=False) + "\n")
    temporary.replace(destination)


def _write_json_atomically(destination, value: dict[str, object]) -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(destination)
