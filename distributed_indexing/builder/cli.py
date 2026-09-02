"""Command-line entry point for the distributed-index build."""

import argparse
from pathlib import Path

from .build import build_distributed_indexes
from .config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Build shard-local indexes and global TF-IDF statistics.")
    parser.add_argument("--config", required=True, type=Path)
    arguments = parser.parse_args()
    statistics = build_distributed_indexes(load_config(arguments.config))
    print(f"Built {len(statistics['node_indexes'])} node indexes; global terms: {len(statistics['terms'])}; version: {statistics['statistics_version']}")


if __name__ == "__main__":
    main()
