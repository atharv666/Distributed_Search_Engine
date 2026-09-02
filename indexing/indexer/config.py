"""Load inverted-index configuration."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IndexConfig:
    documents_file: Path
    index_file: Path
    minimum_token_length: int
    excluded_tokens: frozenset[str]


def load_config(config_path: Path) -> IndexConfig:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    component_directory = config_path.parent.parent
    minimum = int(data["minimum_token_length"])
    if minimum < 1:
        raise ValueError("minimum_token_length must be at least 1.")
    return IndexConfig(
        documents_file=component_directory / data["documents_file"],
        index_file=component_directory / data["index_file"],
        minimum_token_length=minimum,
        excluded_tokens=frozenset(token.casefold() for token in data["excluded_tokens"]),
    )
