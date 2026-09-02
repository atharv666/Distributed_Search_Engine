"""Command-line interface for the distributed coordinator."""

import argparse
import json
from pathlib import Path

from .config import load_config
from .coordinator import SearchCoordinator


def main() -> None:
    parser = argparse.ArgumentParser(description="Query distributed search nodes through the coordinator.")
    parser.add_argument("query")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--top-k", type=int)
    arguments = parser.parse_args()
    print(json.dumps(SearchCoordinator(load_config(arguments.config)).search(arguments.query, arguments.top_k), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
