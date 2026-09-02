"""Command-line entry point for the controlled crawler."""

import argparse
import logging
from pathlib import Path

from .config import load_config
from .crawler import ControlledCrawler


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a bounded corpus of raw HTML pages.")
    parser.add_argument("--config", type=Path, required=True, help="Path to crawl JSON configuration.")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(arguments.config)
    downloaded = ControlledCrawler(config).crawl()
    logging.info("crawl complete: %d page(s) downloaded", downloaded)


if __name__ == "__main__":
    main()
