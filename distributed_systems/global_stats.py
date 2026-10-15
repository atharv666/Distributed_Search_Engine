"""Replicated global statistics: N, document frequencies and the delta log that extends them.

Every coordinator and every node starts from the same base files produced by the offline
pipeline (version 0) and then applies the same ordered deltas, one per added document.
Each applied delta is appended to a small per-process log so a restarted process can replay it,
and a process that is behind can be sent exactly the deltas it is missing.
"""

import json
import math
import threading
from pathlib import Path

APPLIED, DUPLICATE, GAP = "applied", "duplicate", "gap"


class GlobalStats:
    def __init__(self, data_directory: Path, process_id: str) -> None:
        self.lock = threading.RLock()
        self.data_directory = Path(data_directory)
        statistics_file = self.data_directory / "indexes" / "global_statistics.json"
        manifest_file = self.data_directory / "shards" / "partition_manifest.json"
        for required in (statistics_file, manifest_file):
            if not required.exists():
                raise FileNotFoundError(f"Base data not found: {required}. Run the offline pipeline first.")
        statistics = json.loads(statistics_file.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        self.version = 0
        self.n: int = int(statistics["global_document_count"])
        self.df: dict[str, int] = {term: int(entry["document_frequency"]) for term, entry in statistics["terms"].items()}
        self.node_counts: dict[str, int] = {f"N{shard['shard_id']}": int(shard["document_count"]) for shard in manifest["shards"]}
        self.next_doc_id: int = max(int(shard["document_id_end"]) for shard in manifest["shards"]) + 1
        self.deltas: list[dict] = []
        self.log_path = self.data_directory / "state" / f"{process_id}_deltas.jsonl"
        self._replay_log()

    # -- reading -------------------------------------------------------------------------
    def idf(self, term: str) -> float:
        with self.lock:
            df = self.df.get(term, 0)
            return math.log(self.n / df) if df > 0 and self.n > 0 else 0.0

    def deltas_since(self, version: int) -> list[dict]:
        with self.lock:
            return [delta for delta in self.deltas if delta["version"] > version]

    # -- writing -------------------------------------------------------------------------
    def apply(self, delta: dict) -> str:
        """Apply the next delta in order. Older deltas are ignored; a gap is refused."""
        with self.lock:
            if delta["version"] <= self.version:
                return DUPLICATE
            if delta["version"] != self.version + 1:
                return GAP
            self._apply_in_memory(delta)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(delta, ensure_ascii=False) + "\n")
            return APPLIED

    def _apply_in_memory(self, delta: dict) -> None:
        self.n += 1
        for term in set(delta["terms"]):
            self.df[term] = self.df.get(term, 0) + 1
        self.node_counts[delta["node_id"]] = self.node_counts.get(delta["node_id"], 0) + 1
        self.next_doc_id = max(self.next_doc_id, delta["doc_id"] + 1)
        self.version = delta["version"]
        self.deltas.append(delta)

    def _replay_log(self) -> None:
        if not self.log_path.exists():
            return
        with self.log_path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    delta = json.loads(line)
                    if delta["version"] == self.version + 1:
                        self._apply_in_memory(delta)


def delta_to_proto(delta: dict, message) -> None:
    message.version = delta["version"]
    message.doc_id = delta["doc_id"]
    message.node_id = delta["node_id"]
    message.terms.extend(delta["terms"])
    message.title = delta.get("title", "")
    message.url = delta.get("url", "")


def delta_from_proto(message) -> dict:
    return {"version": message.version, "doc_id": message.doc_id, "node_id": message.node_id,
            "terms": list(message.terms), "title": message.title, "url": message.url}
