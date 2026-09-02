"""Load parser configuration."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParserConfig:
    raw_directory: Path
    metadata_file: Path
    documents_file: Path
    minimum_content_characters: int


def load_config(config_path: Path) -> ParserConfig:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    component_directory = config_path.parent.parent
    minimum = int(data["minimum_content_characters"])
    if minimum < 0:
        raise ValueError("minimum_content_characters cannot be negative.")
    return ParserConfig(
        raw_directory=component_directory / data["raw_directory"],
        metadata_file=component_directory / data["metadata_file"],
        documents_file=component_directory / data["documents_file"],
        minimum_content_characters=minimum,
    )
