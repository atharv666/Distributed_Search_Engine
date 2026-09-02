"""Dependency-free visible-text and title extraction from HTML."""

import re
from html.parser import HTMLParser

_SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "canvas"}
_NOISE_TAGS = {"nav", "footer", "aside", "form"}
_BLOCK_TAGS = {"article", "section", "main", "div", "p", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "table", "tr"}


class VisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._in_h1 = False
        self._title_parts: list[str] = []
        self._heading_parts: list[str] = []
        self._content_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS or tag in _NOISE_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        self._in_title = self._in_title or tag == "title"
        self._in_h1 = self._in_h1 or tag == "h1"
        if tag in _BLOCK_TAGS:
            self._content_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS or tag in _NOISE_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag == "h1":
            self._in_h1 = False
        if tag in _BLOCK_TAGS:
            self._content_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
        if self._in_h1:
            self._heading_parts.append(data)
        self._content_parts.append(data)

    def result(self) -> tuple[str, str]:
        title = _normalize(" ".join(self._title_parts)) or _normalize(" ".join(self._heading_parts))
        return title, _normalize(" ".join(self._content_parts))


def extract_document_fields(html: str) -> tuple[str, str]:
    parser = VisibleTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.result()


def decode_html_bytes(raw_html: bytes) -> str:
    """Decode UTF-8 HTML and repair a common UTF-8-as-Windows-1252 artifact."""
    text = raw_html.decode("utf-8", errors="replace")
    if any(marker in text for marker in ("â€", "â€”", "â€™", "Â ")):
        try:
            return text.encode("cp1252").decode("utf-8")
        except UnicodeError:
            pass
    return text


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
