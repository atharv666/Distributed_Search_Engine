"""URL normalization and allowlist checks."""

from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse


def normalize_url(url: str, base_url: str | None = None) -> str | None:
    absolute = urljoin(base_url, url) if base_url else url
    parsed = urlparse(absolute)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    hostname = parsed.hostname.lower()
    netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunparse((parsed.scheme.lower(), netloc, parsed.path or "/", "", query, ""))


def is_allowed(url: str, allowed_domains: frozenset[str]) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains)
