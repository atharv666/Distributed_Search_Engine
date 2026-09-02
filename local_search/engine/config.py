"""Load local-search settings."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SearchConfig:
    documents_file: Path
    index_file: Path
    default_top_k: int
    minimum_token_length: int
    excluded_tokens: frozenset[str]
    snippet_length: int


def load_config(config_path: Path) -> SearchConfig:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    component_directory = config_path.parent.parent
    if data["default_top_k"] <= 0 or data["minimum_token_length"] < 1 or data["snippet_length"] <= 0:
        raise ValueError("top-K, token length, and snippet length must be positive.")
    return SearchConfig(
        documents_file=component_directory / data["documents_file"],
        index_file=component_directory / data["index_file"],
        default_top_k=int(data["default_top_k"]), minimum_token_length=int(data["minimum_token_length"]),
        excluded_tokens=frozenset(token.casefold() for token in data["excluded_tokens"]), snippet_length=int(data["snippet_length"]),
    )
