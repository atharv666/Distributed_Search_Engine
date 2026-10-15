"""Search node: serves one shard, indexes new documents and follows the leader's beacons.

A node keeps its shard file, an in-memory inverted index and a full copy of the global
statistics (N and document frequencies). It never decides anything cluster-wide: it obeys the
leader of the highest epoch it has seen and reports when the leader goes silent.
"""

import argparse
import json
import math
import re
import threading
import time
from collections import Counter, defaultdict
from concurrent import futures
from pathlib import Path

import grpc

from distributed_systems.cluster_config import ClusterConfig, load_cluster_config
from distributed_systems.global_stats import APPLIED, GAP, GlobalStats, delta_from_proto
from distributed_systems.rpc import call, fan_out
from distributed_systems.tracing import Tracer
from indexing.indexer.tokenizer import tokenize
from proto import search_pb2, search_pb2_grpc

MINIMUM_TOKEN_LENGTH = 2
SNIPPET_LENGTH = 240


def category_for(op: str) -> str:
    return "sync" if op.startswith("sync") else "add"


class NodeService(search_pb2_grpc.NodeServiceServicer):
    def __init__(self, node_id: str, config: ClusterConfig) -> None:
        self.id = node_id
        self.cfg = config
        entry = config.node(node_id)
        self.shard_file = config.data_directory / "shards" / f"shard_{entry.shard}.jsonl"
        self.tracer = Tracer(node_id, config.event_sink_url)
        self.stats = GlobalStats(config.data_directory, node_id)

        self.lock = threading.RLock()          # guards the index, norms and statistics together
        self.state_lock = threading.Lock()     # guards epoch / leader bookkeeping
        self.epoch = 0
        self.leader_id = ""
        self.last_beat = time.time()
        self.beacons_received = 0
        self.suspect_until = 0.0

        self.docs: dict[int, dict] = {}
        self.postings: dict[str, dict[int, int]] = defaultdict(dict)   # term -> {doc_id: term frequency}
        self.doc_length: dict[int, int] = {}
        self.norms: dict[int, float] = {}
        self._load_shard()
        self._recompute_norms()
        threading.Thread(target=self._watch_leader, name=f"{node_id}-watch", daemon=True).start()

    # ---- index ------------------------------------------------------------------------------
    def _load_shard(self) -> None:
        if not self.shard_file.exists():
            raise FileNotFoundError(f"Shard file not found: {self.shard_file}")
        with self.shard_file.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    document = json.loads(line)
                    self.docs[document["document_id"]] = document
                    self._index_document(document)

    def _index_document(self, document: dict) -> Counter:
        tokens = tokenize(document["content"], MINIMUM_TOKEN_LENGTH, frozenset())
        self.doc_length[document["document_id"]] = len(tokens)
        counts = Counter(tokens)
        for term, frequency in counts.items():
            self.postings[term][document["document_id"]] = frequency
        return counts

    def _recompute_norms(self) -> None:
        """Document vector norms depend on every IDF, so they are rebuilt whenever N or DF change."""
        squared: dict[int, float] = defaultdict(float)
        for term, postings in self.postings.items():
            idf = self.stats.idf(term)
            if idf <= 0:
                continue
            for document_id, frequency in postings.items():
                squared[document_id] += (frequency / self.doc_length[document_id] * idf) ** 2
        self.norms = {document_id: math.sqrt(value) for document_id, value in squared.items()}

    # ---- epoch bookkeeping --------------------------------------------------------------------
    def _observe_epoch(self, epoch: int, leader_id: str) -> bool:
        """Return True if the sender's epoch is stale (older than one we already follow)."""
        with self.state_lock:
            if epoch < self.epoch:
                return True
            self.epoch = epoch
            if leader_id:
                self.leader_id = leader_id
            return False

    # ---- RPCs: search --------------------------------------------------------------------------
    def Search(self, request, context):
        tracer = self.tracer
        tracer.incoming(request.stamp, "search_received", "search", query=request.query)
        with self.lock:
            results = self._score(request.query, request.top_k or self.cfg.local_top_k)
            version = self.stats.version
        tracer.local("scored_locally", "search", op=request.stamp.op, candidates=len(results), stats_version=version)
        reply = search_pb2.NodeSearchReply(results=results, node_id=self.id, stats_version=version)
        reply.stamp.CopyFrom(tracer.reply(request.stamp, "search_reply_sent", "search"))
        return reply

    def _score(self, query: str, top_k: int):
        """Cosine TF-IDF with GLOBAL IDF for every query term, so scores are comparable across nodes."""
        tokens = tokenize(query, MINIMUM_TOKEN_LENGTH, frozenset())
        if not tokens:
            return []
        weights: dict[str, tuple[float, float]] = {}
        query_norm_squared = 0.0
        for term, count in Counter(tokens).items():
            idf = self.stats.idf(term)
            if idf <= 0:
                continue
            weight = count / len(tokens) * idf
            weights[term] = (weight, idf)
            query_norm_squared += weight * weight
        if query_norm_squared == 0:
            return []
        scores: dict[int, float] = defaultdict(float)
        for term, (weight, idf) in weights.items():
            for document_id, frequency in self.postings.get(term, {}).items():
                scores[document_id] += weight * (frequency / self.doc_length[document_id] * idf)
        query_norm = math.sqrt(query_norm_squared)
        ranked = []
        for document_id, dot in scores.items():
            norm = self.norms.get(document_id, 0.0)
            if norm > 0:
                ranked.append((dot / (query_norm * norm), document_id))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        results = []
        for score, document_id in ranked[:top_k]:
            document = self.docs[document_id]
            results.append(search_pb2.SearchResult(
                document_id=document_id, score=score, title=document["title"], url=document["url"],
                snippet=_snippet(document["content"], tokens), node_id=self.id))
        return results

    # ---- RPCs: adding documents and statistics ----------------------------------------------------
    def AddDocument(self, request, context):
        tracer = self.tracer
        op = request.stamp.op
        tracer.incoming(request.stamp, "add_document_received", category_for(op), doc_id=request.document.document_id)
        reply = search_pb2.AddDocumentReply(node_id=self.id)
        if self._observe_epoch(request.epoch, request.leader_id):
            reply.stale, reply.error = True, "stale epoch"
        else:
            document = {
                "document_id": request.document.document_id, "title": request.document.title,
                "url": request.document.url, "source": request.document.source or "admin",
                "content": request.document.content, "content_length": len(request.document.content),
                "shard_id": self.cfg.node(self.id).shard,
            }
            with self.lock:
                if document["document_id"] in self.docs:       # a retried request: do not index twice
                    existing = self.docs[document["document_id"]]
                    counts = Counter(tokenize(existing["content"], MINIMUM_TOKEN_LENGTH, frozenset()))
                else:
                    with self.shard_file.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(document, ensure_ascii=False) + "\n")
                    self.docs[document["document_id"]] = document
                    counts = self._index_document(document)
                reply.doc_count = len(self.docs)
            reply.ok, reply.doc_length = True, sum(counts.values())
            reply.terms.extend(sorted(counts))
            tracer.local("document_indexed", category_for(op), op=op, doc_id=document["document_id"],
                         tokens=reply.doc_length, unique_terms=len(counts), shard_documents=reply.doc_count)
        reply.epoch = self.epoch
        reply.stamp.CopyFrom(tracer.reply(request.stamp, "add_document_reply_sent", category_for(op)))
        return reply

    def ApplyStatistics(self, request, context):
        tracer = self.tracer
        op = request.stamp.op
        tracer.incoming(request.stamp, "apply_statistics_received", category_for(op),
                        versions=[delta.version for delta in request.deltas])
        reply = search_pb2.ApplyStatisticsReply(process_id=self.id)
        if self._observe_epoch(request.epoch, request.leader_id):
            reply.stale = True
        else:
            applied, behind = 0, False
            started = time.perf_counter()
            with self.lock:
                for message in sorted(request.deltas, key=lambda item: item.version):
                    status = self.stats.apply(delta_from_proto(message))
                    if status == APPLIED:
                        applied += 1
                    elif status == GAP:
                        behind = True
                        break
                if applied:
                    self._recompute_norms()
                version = self.stats.version
            reply.ok, reply.behind, reply.version = not behind, behind, version
            if applied:
                tracer.local("statistics_applied", category_for(op), op=op, version=version, total_docs=self.stats.n,
                             norms_recomputed_ms=round((time.perf_counter() - started) * 1000, 1))
        reply.epoch = self.epoch
        reply.version = self.stats.version
        reply.stamp.CopyFrom(tracer.reply(request.stamp, "apply_statistics_reply_sent", category_for(op)))
        return reply

    # ---- RPCs: beacon, announcements, status ---------------------------------------------------------
    def Heartbeat(self, request, context):
        tracer = self.tracer
        tracer.incoming(request.stamp, "beacon_received", "beacon", beat=request.beat, leader=request.leader_id)
        stale = self._observe_epoch(request.epoch, request.leader_id)
        if not stale:
            with self.state_lock:
                self.last_beat = time.time()
                self.beacons_received += 1
                self.suspect_until = 0.0
        reply = search_pb2.HeartbeatReply(process_id=self.id, ok=not stale, stale=stale, epoch=self.epoch,
                                          leader_id=self.leader_id, stats_version=self.stats.version)
        reply.stamp.CopyFrom(tracer.reply(request.stamp, "beacon_reply_sent", "beacon"))
        return reply

    def Announce(self, request, context):
        tracer = self.tracer
        tracer.incoming(request.stamp, "announce_received", "election", leader=request.leader_id, epoch=request.epoch)
        with self.state_lock:
            accepted = request.epoch > self.epoch or (
                request.epoch == self.epoch and self.leader_id in ("", request.leader_id))
            if accepted:
                self.epoch, self.leader_id = request.epoch, request.leader_id
                self.last_beat, self.suspect_until = time.time(), 0.0
        if accepted:
            tracer.local("leader_accepted", "election", op=request.stamp.op, leader=request.leader_id, epoch=request.epoch)
        reply = search_pb2.AnnounceReply(process_id=self.id, accepted=accepted, epoch=self.epoch, leader_id=self.leader_id)
        reply.stamp.CopyFrom(tracer.reply(request.stamp, "announce_reply_sent", "election"))
        return reply

    def GetStatus(self, request, context):
        with self.state_lock:
            reply = search_pb2.StatusReply(
                process_id=self.id, kind="node", role="FOLLOWER", leader_id=self.leader_id, epoch=self.epoch,
                stats_version=self.stats.version, committed_version=self.stats.version, ready=True,
                last_beat_age=round(time.time() - self.last_beat, 2), beat_timeout=self.cfg.beat_timeout,
                beacons_received=self.beacons_received, doc_count=len(self.docs), total_docs=self.stats.n,
                next_doc_id=self.stats.next_doc_id)
        reply.clock.update(self.tracer.clock.snapshot())
        return reply

    # ---- failure detection --------------------------------------------------------------------------
    def _watch_leader(self) -> None:
        """If no beacon arrives within the timeout, tell every coordinator the leader looks dead."""
        while True:
            time.sleep(1.0)
            now = time.time()
            with self.state_lock:
                silence = now - self.last_beat
                due = silence > self.cfg.beat_timeout and now >= self.suspect_until
                leader, epoch = self.leader_id, self.epoch
                if due:
                    self.suspect_until = now + self.cfg.beat_timeout
            if due:
                self._report_suspect(leader, epoch, silence)

    def _report_suspect(self, leader: str, epoch: int, silence: float) -> None:
        op = f"failover-e{epoch}"
        self.tracer.local("leader_suspected", "election", op=op, leader=leader or "unknown", silent_for=round(silence, 1))

        def report(coordinator):
            request = search_pb2.SuspectRequest(reporter_id=self.id, leader_id=leader, epoch=epoch,
                                                silence_seconds=silence)
            return call(self.tracer, coordinator.address, search_pb2_grpc.CoordinatorServiceStub, "ReportSuspect",
                        request, name="suspect_report", peer=coordinator.id, category="election", op=op,
                        timeout=self.cfg.rpc_timeout)

        fan_out(self.cfg.coordinators, report)


def _snippet(content: str, tokens: list[str]) -> str:
    match = re.search("|".join(re.escape(token) for token in sorted(set(tokens), key=len, reverse=True)),
                      content, re.IGNORECASE)
    start = max(0, (match.start() if match else 0) - SNIPPET_LENGTH // 3)
    end = min(len(content), start + SNIPPET_LENGTH)
    return ("…" if start else "") + content[start:end].strip() + ("…" if end < len(content) else "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one search node.")
    parser.add_argument("--id", required=True, help="Node ID such as N1.")
    parser.add_argument("--config", type=Path, required=True)
    arguments = parser.parse_args()
    config = load_cluster_config(arguments.config)
    service = NodeService(arguments.id, config)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    search_pb2_grpc.add_NodeServiceServicer_to_server(service, server)
    port = config.node(arguments.id).address.rsplit(":", 1)[1]
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"{arguments.id} serving shard {config.node(arguments.id).shard} on port {port} "
          f"(statistics v{service.stats.version}, {len(service.docs)} documents)", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    main()
