"""Serve a local shard using shared global IDF and process-local logical time."""

import argparse
import json
import math
from collections import Counter, defaultdict
from concurrent import futures
from pathlib import Path

import grpc

from distributed_systems.clock import LamportClock
from distributed_systems.integrity import index_metadata, sha256_bytes, statistics_version
from indexing.indexer.tokenizer import tokenize
from proto import search_pb2, search_pb2_grpc


class Service(search_pb2_grpc.SearchServiceServicer):
    def __init__(self, node_id, index, shard, stats):
        self.node_id = node_id
        self.clock = LamportClock()
        # Parse exactly the bytes whose fingerprint we report. Reading twice
        # could validate another file if a rebuild replaces it between reads.
        index_bytes = Path(index).read_bytes()
        self.i = json.loads(index_bytes)
        self.index_hash = sha256_bytes(index_bytes)
        self.s = json.loads(Path(stats).read_bytes())
        self.expected_index_hash, self.index_consistency, self.index_consistency_error = index_metadata(
            self.s, self.node_id
        )
        if self.index_consistency == "consistent" and self.index_hash != self.expected_index_hash:
            self.index_consistency = "inconsistent"
            self.index_consistency_error = "Loaded index hash does not match global statistics metadata."
        loaded_version = self.s.get("statistics_version")
        self.statistics_version = loaded_version if isinstance(loaded_version, str) else ""
        if "statistics_version" not in self.s or loaded_version == "":
            if self.index_consistency != "inconsistent":
                self.index_consistency = "unverified"
                self.index_consistency_error = " ".join(filter(None, (
                    self.index_consistency_error, "Loaded statistics contain no statistics_version.",
                )))
        elif not isinstance(loaded_version, str) or loaded_version != statistics_version(self.s):
            self.index_consistency = "inconsistent"
            self.index_consistency_error = " ".join(filter(None, (
                self.index_consistency_error, "Loaded statistics_version does not match its payload.",
            )))
        with Path(shard).open(encoding="utf-8") as stream:
            self.docs = {d["document_id"]: d for d in map(json.loads, stream)}
        self.norm = defaultdict(float)
        if self.index_consistency != "inconsistent":
            for term, entry in self.i["terms"].items():
                for posting in entry["postings"]:
                    self.norm[posting["document_id"]] += (
                        (posting["term_frequency"] / self.i["document_lengths"][str(posting["document_id"])])
                        * self.s["terms"][term]["idf"]
                    ) ** 2
        self.norm = {key: math.sqrt(value) for key, value in self.norm.items()}

    def Search(self, request, context):
        received_timestamp = self.clock.receive(request.logical_timestamp)
        if self.index_consistency == "inconsistent":
            return self._response(request, received_timestamp, [])
        tokens = tokenize(request.query, 2, frozenset())
        query_counts = Counter(tokens)
        scores = defaultdict(float)
        query_norm = 0
        for term, count in query_counts.items():
            entry = self.i["terms"].get(term)
            idf = self.s["terms"].get(term, {}).get("idf", 0)
            if not entry or not idf:
                continue
            weight = count / len(tokens) * idf
            query_norm += weight * weight
            for posting in entry["postings"]:
                scores[posting["document_id"]] += weight * (
                    posting["term_frequency"] / self.i["document_lengths"][str(posting["document_id"])] * idf
                )
        results = []
        for document_id, dot in scores.items():
            if self.norm[document_id]:
                document = self.docs[document_id]
                results.append(search_pb2.SearchResult(
                    document_id=document_id,
                    score=dot / (math.sqrt(query_norm) * self.norm[document_id]),
                    title=document["title"], url=document["url"], snippet=document["content"][:240],
                    node_id=self.node_id,
                ))
        selected = sorted(results, key=lambda result: -result.score)[:request.top_k or 20]
        return self._response(request, received_timestamp, selected)

    def _response(self, request, received_timestamp, results):
        sent_timestamp = self.clock.tick()
        return search_pb2.SearchResponse(
            results=results, node_id=self.node_id, statistics_version=self.statistics_version,
            request_id=request.request_id, request_received_timestamp=received_timestamp,
            response_sent_timestamp=sent_timestamp, index_hash=self.index_hash,
            expected_index_hash=self.expected_index_hash, index_consistency=self.index_consistency,
            index_consistency_error=self.index_consistency_error,
        )

def main():
 p=argparse.ArgumentParser();[p.add_argument(x,required=True) for x in ('--node-id','--index','--shard','--statistics')];p.add_argument('--port',type=int,required=True);a=p.parse_args();s=grpc.server(futures.ThreadPoolExecutor(max_workers=4));search_pb2_grpc.add_SearchServiceServicer_to_server(Service(a.node_id,a.index,a.shard,a.statistics),s);s.add_insecure_port(f'[::]:{a.port}');s.start();print(f'{a.node_id} on {a.port}');s.wait_for_termination()
if __name__=='__main__':main()
