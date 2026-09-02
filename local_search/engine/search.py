"""Cosine TF-IDF search over the base inverted index."""

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from indexing.indexer.tokenizer import tokenize

from .config import SearchConfig


class LocalSearchEngine:
    def __init__(self, config: SearchConfig) -> None:
        self.config = config
        self.index = self._load_json(config.index_file)
        self.documents = self._load_documents(config.documents_file)

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, object]]:
        tokens = tokenize(query, self.config.minimum_token_length, self.config.excluded_tokens)
        if not tokens:
            return []
        query_counts = Counter(tokens)
        total_query_tokens = len(tokens)
        document_count = self.index["document_count"]
        terms = self.index["terms"]
        scores: dict[int, float] = defaultdict(float)
        query_norm_squared = 0.0

        for term, occurrences in query_counts.items():
            entry = terms.get(term)
            if not entry:
                continue
            idf = math.log(document_count / entry["document_frequency"])
            query_weight = (occurrences / total_query_tokens) * idf
            query_norm_squared += query_weight**2
            for posting in entry["postings"]:
                document_id = posting["document_id"]
                document_length = self.index["document_lengths"][str(document_id)]
                document_weight = (posting["term_frequency"] / document_length) * idf
                scores[document_id] += query_weight * document_weight

        query_norm = math.sqrt(query_norm_squared)
        if query_norm == 0:
            return []
        results: list[dict[str, object]] = []
        norms = self.index["document_vector_norms"]
        for document_id, dot_product in scores.items():
            document_norm = norms.get(str(document_id), 0.0)
            if not document_norm:
                continue
            document = self.documents.get(document_id)
            if not document:
                continue
            score = dot_product / (query_norm * document_norm)
            results.append({
                "document_id": document_id,
                "score": score,
                "title": document["title"],
                "url": document["url"],
                "snippet": self._snippet(document["content"], tokens),
            })
        return sorted(results, key=lambda item: (-item["score"], item["document_id"]))[:top_k or self.config.default_top_k]

    def _snippet(self, content: str, tokens: list[str]) -> str:
        match = re.search("|".join(re.escape(token) for token in sorted(set(tokens), key=len, reverse=True)), content, re.IGNORECASE)
        start = max(0, (match.start() if match else 0) - self.config.snippet_length // 3)
        end = min(len(content), start + self.config.snippet_length)
        prefix = "…" if start else ""
        suffix = "…" if end < len(content) else ""
        return prefix + content[start:end].strip() + suffix

    @staticmethod
    def _load_json(path: Path) -> dict[str, object]:
        if not path.exists():
            raise FileNotFoundError(f"Index not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _load_documents(path: Path) -> dict[int, dict[str, str]]:
        if not path.exists():
            raise FileNotFoundError(f"Documents not found: {path}")
        documents: dict[int, dict[str, str]] = {}
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                documents[record["document_id"]] = record
        return documents
