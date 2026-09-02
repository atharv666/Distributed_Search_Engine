"""Minimal, dependency-free HTML link extraction for crawl discovery."""

from html.parser import HTMLParser


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def extract_links(html: str) -> list[str]:
    parser = LinkExtractor()
    parser.feed(html)
    parser.close()
    return parser.links
