"""Turn a URL (or pasted text) into the document JSON that the leader coordinator will index."""

import time
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ingestion_crawler.crawler.robots import RobotsPolicy
from ingestion_crawler.crawler.url_utils import normalize_url
from parsing_html.parser.html_extractor import decode_html_bytes, extract_document_fields

USER_AGENT = "DistributedSearchEngineAdmin/0.1 (academic demo)"
MINIMUM_CONTENT_CHARACTERS = 80
MAXIMUM_BYTES = 3_000_000
FETCH_TIMEOUT_SECONDS = 15

Report = Callable[..., None]


class IngestError(Exception):
    """The URL could not be turned into a document; the message is shown in the admin page."""


class DocumentBuilder:
    def __init__(self) -> None:
        self.robots = RobotsPolicy(USER_AGENT)

    def from_url(self, url: str, report: Report) -> dict:
        normalized = normalize_url(url.strip())
        if not normalized:
            raise IngestError("Only absolute http(s) URLs are supported.")
        report("fetch_started", url=normalized)
        if not self.robots.can_fetch(normalized):
            raise IngestError("robots.txt disallows this URL (or could not be read).")
        began = time.perf_counter()
        try:
            request = Request(normalized, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
                content_type = response.headers.get_content_type().lower()
                final_url = normalize_url(response.geturl()) or normalized
                body = response.read(MAXIMUM_BYTES)
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            raise IngestError(f"Could not fetch the page: {error}") from error
        if content_type != "text/html":
            raise IngestError(f"Not an HTML page (content type {content_type}).")
        report("html_fetched", bytes=len(body), content_type=content_type,
               fetch_ms=round((time.perf_counter() - began) * 1000))
        title, content = extract_document_fields(decode_html_bytes(body))
        report("html_parsed", title=title or final_url, characters=len(content))
        document = self._finish(title or final_url, final_url, content, report)
        return document

    def from_text(self, title: str, content: str, url: str, report: Report) -> dict:
        report("text_received", characters=len(content))
        return self._finish(title.strip() or "Untitled document", url.strip() or "text://admin", content.strip(), report)

    @staticmethod
    def _finish(title: str, url: str, content: str, report: Report) -> dict:
        if len(content) < MINIMUM_CONTENT_CHARACTERS:
            raise IngestError(f"Page text is too short to index ({len(content)} characters; "
                              f"at least {MINIMUM_CONTENT_CHARACTERS} are needed).")
        document = {"title": title, "url": url, "source": "admin", "content": content, "content_length": len(content)}
        report("document_json_built", title=title, url=url, content_length=len(content), preview=content[:240])
        return document
