"""Command-line entry point for document partitioning."""

import argparse
import json
from pathlib import Path

from .config import load_config
from .partitioner import partition_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Split parsed documents into deterministic shard files.")
    parser.add_argument("--config", type=Path, required=True, help="Path to partition JSON configuration.")
    arguments = parser.parse_args()
    manifest = partition_documents(load_config(arguments.config))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
