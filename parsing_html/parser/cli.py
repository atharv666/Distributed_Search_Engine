"""Command-line entry point for raw HTML parsing."""

import argparse
import logging
from pathlib import Path

from .config import load_config
from .document_parser import DocumentParser


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert crawled raw HTML into logical documents.")
    parser.add_argument("--config", type=Path, required=True, help="Path to parser JSON configuration.")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    count = DocumentParser(load_config(arguments.config)).parse_all()
    logging.info("parsing complete: %d document(s) added", count)


if __name__ == "__main__":
    main()
