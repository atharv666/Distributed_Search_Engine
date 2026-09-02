"""Command-line interface for the local reference search path."""

import argparse
import json
from pathlib import Path

from .config import load_config
from .search import LocalSearchEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the local TF-IDF index.")
    parser.add_argument("query", help="Natural-language query to search for.")
    parser.add_argument("--config", type=Path, required=True, help="Path to search JSON configuration.")
    parser.add_argument("--top-k", type=int, help="Number of results to return.")
    arguments = parser.parse_args()
    if arguments.top_k is not None and arguments.top_k <= 0:
        parser.error("--top-k must be positive")
    results = LocalSearchEngine(load_config(arguments.config)).search(arguments.query, arguments.top_k)
    print(json.dumps({"query": arguments.query, "result_count": len(results), "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
