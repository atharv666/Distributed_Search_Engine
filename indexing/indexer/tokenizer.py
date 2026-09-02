"""Deterministic Unicode-aware tokenization for lexical search."""

import re

_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


def tokenize(text: str, minimum_length: int, excluded_tokens: frozenset[str]) -> list[str]:
    """Normalize text and retain meaningful hyphenated or apostrophe terms."""
    return [
        token
        for match in _TOKEN_PATTERN.finditer(text.casefold())
        if len(token := match.group(0)) >= minimum_length and token not in excluded_tokens
    ]
