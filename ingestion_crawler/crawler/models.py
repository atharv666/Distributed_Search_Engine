"""Shared immutable data structures for the crawl pipeline."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Seed:
    url: str
    source: str


@dataclass(frozen=True)
class CrawlTask:
    url: str
    depth: int
    source: str
