"""Configuration loading and validation."""

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .models import Seed


@dataclass(frozen=True)
class CrawlConfig:
    seeds: tuple[Seed, ...]
    allowed_domains: frozenset[str]
    max_pages: int
    max_depth: int
    request_delay_seconds: float
    request_timeout_seconds: float
    user_agent: str
    output_directory: Path
    metadata_file: Path


def load_config(config_path: Path) -> CrawlConfig:
    """Load a JSON crawl configuration and reject unsafe/incomplete values."""
    data = json.loads(config_path.read_text(encoding="utf-8"))
    base_directory = config_path.parent.parent
    seeds = tuple(Seed(url=item["url"], source=item["source"]) for item in data["seeds"])
    allowed_domains = frozenset(domain.lower() for domain in data["allowed_domains"])
    if not seeds or not allowed_domains:
        raise ValueError("At least one seed URL and allowed domain are required.")
    if data["max_pages"] <= 0 or data["max_depth"] < 0:
        raise ValueError("max_pages must be positive and max_depth cannot be negative.")
    if data["request_delay_seconds"] < 0 or data["request_timeout_seconds"] <= 0:
        raise ValueError("Request delay must be non-negative and timeout must be positive.")
    for seed in seeds:
        if urlparse(seed.url).scheme not in {"http", "https"}:
            raise ValueError(f"Seed must be HTTP(S): {seed.url}")
    return CrawlConfig(
        seeds=seeds, allowed_domains=allowed_domains, max_pages=data["max_pages"], max_depth=data["max_depth"],
        request_delay_seconds=float(data["request_delay_seconds"]), request_timeout_seconds=float(data["request_timeout_seconds"]),
        user_agent=data["user_agent"], output_directory=base_directory / data["output_directory"],
        metadata_file=base_directory / data["metadata_file"],
    )
