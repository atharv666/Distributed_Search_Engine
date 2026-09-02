"""Bounded breadth-first crawler that stores only raw HTML pages."""

import logging
import time
from collections import deque
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import CrawlConfig
from .html_links import extract_links
from .models import CrawlTask
from .robots import RobotsPolicy
from .storage import CrawlStorage
from .url_utils import is_allowed, normalize_url

LOGGER = logging.getLogger(__name__)


class ControlledCrawler:
    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.storage = CrawlStorage(config.output_directory, config.metadata_file)
        self.robots = RobotsPolicy(config.user_agent)
        self.last_request_at: dict[str, float] = {}

    def crawl(self) -> int:
        queue = deque(CrawlTask(normalize_url(seed.url) or seed.url, 0, seed.source) for seed in self.config.seeds)
        # Persisted metadata makes deduplication survive separate crawler runs.
        seen = self.storage.previously_crawled_urls()
        LOGGER.info("loaded %d URL(s) from previous crawl metadata", len(seen))
        downloaded = 0
        while queue and downloaded < self.config.max_pages:
            task = queue.popleft()
            if task.url in seen:
                continue
            seen.add(task.url)
            if not is_allowed(task.url, self.config.allowed_domains) or not self.robots.can_fetch(task.url):
                LOGGER.info("skipping disallowed robots policy URL: %s", task.url)
                continue
            response = self._fetch(task.url)
            if response is None:
                continue
            body, content_type, final_url = response
            document_id = self.storage.next_document_id()
            path = self.storage.save(document_id, body, {
                "url": final_url, "requested_url": task.url, "source": task.source,
                "crawl_depth": task.depth, "content_type": content_type,
            })
            downloaded += 1
            LOGGER.info("saved %s from %s", path, final_url)
            if task.depth < self.config.max_depth:
                for link in extract_links(body.decode("utf-8", errors="replace")):
                    normalized = normalize_url(link, final_url)
                    if normalized and is_allowed(normalized, self.config.allowed_domains):
                        queue.append(CrawlTask(normalized, task.depth + 1, task.source))
        return downloaded

    def _fetch(self, url: str) -> tuple[bytes, str, str] | None:
        origin = "/".join(url.split("/", 3)[:3])
        elapsed = time.monotonic() - self.last_request_at.get(origin, 0)
        if elapsed < self.config.request_delay_seconds:
            time.sleep(self.config.request_delay_seconds - elapsed)
        try:
            request = Request(url, headers={"User-Agent": self.config.user_agent})
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                content_type = response.headers.get_content_type().lower()
                final_url = normalize_url(response.geturl())
                self.last_request_at[origin] = time.monotonic()
                if content_type != "text/html" or not final_url or not is_allowed(final_url, self.config.allowed_domains):
                    LOGGER.info("skipping non-HTML or redirected response: %s", url)
                    return None
                return response.read(), content_type, final_url
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            LOGGER.warning("could not fetch %s: %s", url, error)
            return None
