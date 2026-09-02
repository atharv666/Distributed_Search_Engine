"""Command-line entry point for building the base inverted index."""

import argparse
import logging
from pathlib import Path

from .config import load_config
from .index_builder import build_index, save_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Tokenize parsed documents and build an inverted index.")
    parser.add_argument("--config", type=Path, required=True, help="Path to index JSON configuration.")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(arguments.config)
    index = build_index(config)
    save_index(index, config.index_file)
    logging.info("index complete: %d documents, %d terms", index["document_count"], len(index["terms"]))


if __name__ == "__main__":
    main()
