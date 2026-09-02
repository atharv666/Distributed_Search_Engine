"""Build a positional inverted index from parsed logical documents."""

import json
import math
from collections import defaultdict
from pathlib import Path

from .config import IndexConfig
from .tokenizer import tokenize


def build_index(config: IndexConfig) -> dict[str, object]:
    """Build a deterministic index; each run fully reflects documents.jsonl."""
    postings: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    document_lengths: dict[int, int] = {}
    document_count = 0

    if not config.documents_file.exists():
        raise FileNotFoundError(f"Parsed documents not found: {config.documents_file}")

    with config.documents_file.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                document = json.loads(line)
                document_id = document["document_id"]
                content = document["content"]
            except (json.JSONDecodeError, KeyError) as error:
                raise ValueError(f"Invalid document on line {line_number}") from error
            if not isinstance(document_id, int) or not isinstance(content, str):
                raise ValueError(f"Document on line {line_number} has invalid ID or content.")

            tokens = tokenize(content, config.minimum_token_length, config.excluded_tokens)
            document_lengths[document_id] = len(tokens)
            document_count += 1
            for position, token in enumerate(tokens):
                postings[token][document_id].append(position)

    terms = {
        term: {
            "document_frequency": len(term_postings),
            "postings": [
                {
                    "document_id": document_id,
                    "term_frequency": len(positions),
                    "positions": positions,
                }
                for document_id, positions in sorted(term_postings.items())
            ],
        }
        for term, term_postings in sorted(postings.items())
    }
    document_vector_norms: dict[int, float] = defaultdict(float)
    for entry in terms.values():
        idf = math.log(document_count / entry["document_frequency"])
        for posting in entry["postings"]:
            document_id = posting["document_id"]
            tf = posting["term_frequency"] / document_lengths[document_id]
            document_vector_norms[document_id] += (tf * idf) ** 2
    return {
        "format_version": 1,
        "document_count": document_count,
        "document_lengths": document_lengths,
        "document_vector_norms": {
            document_id: math.sqrt(squared_norm)
            for document_id, squared_norm in sorted(document_vector_norms.items())
        },
        "terms": terms,
    }


def save_index(index: dict[str, object], destination: Path) -> None:
    """Atomically replace this derived artifact rather than appending duplicates."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(destination)
