"""Concurrent gRPC fan-out, causal tracing, consistency checks and Top-K merge."""

import json
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import grpc

from distributed_systems.clock import LamportClock
from distributed_systems.integrity import index_metadata, statistics_version
from proto import search_pb2, search_pb2_grpc

from .config import CoordinatorConfig, NodeAddress

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class _QueryTrace:
    """One query's events; fan-out workers never share this with another query."""

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        self.events: list[dict[str, object]] = []
        self.lock = threading.Lock()

    def record(self, process_id: str, node_id: str, event: str, timestamp: int) -> None:
        with self.lock:
            self.events.append({
                "request_id": self.request_id, "process_id": process_id, "node_id": node_id,
                "event": event, "logical_timestamp": timestamp,
            })


class SearchCoordinator:
    def __init__(self, config: CoordinatorConfig) -> None:
        self.config = config
        self.clock = LamportClock()

    def search(self, query: str, top_k: int | None = None) -> dict[str, object]:
        final_top_k = self.config.final_top_k if top_k is None else top_k
        if final_top_k <= 0:
            raise ValueError("top_k must be positive.")
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        trace = _QueryTrace(request_id)
        trace.record("coordinator", "", "search_started", self.clock.tick())
        # Read one authoritative generation per query. Atomic builder replacement
        # lets subsequent queries see a rebuild without restarting the coordinator.
        expected, authority_error = self._load_expected_statistics()
        responses = []
        statuses = []
        with ThreadPoolExecutor(max_workers=len(self.config.nodes)) as pool:
            futures = {
                pool.submit(self._search_node, node, query, request_id, trace,
                            max(self.config.local_top_k, final_top_k)): node
                for node in self.config.nodes
            }
            for future in as_completed(futures):
                node = futures[future]
                try:
                    response, latency_ms, protocol_error = future.result()
                    status = self._response_status(node, response, expected, protocol_error)
                    status["latency_ms"] = latency_ms
                    statuses.append(status)
                    if status["results_accepted"]:
                        responses.append(response)
                    if protocol_error:
                        trace.record("coordinator", node.node_id, "response_rejected", self.clock.tick())
                except grpc.RpcError as error:
                    statuses.append({
                        "node_id": node.node_id, "address": node.address, "status": "unavailable",
                        "rpc_state": "unavailable", "error": error.code().name,
                        "index_consistency": "unverified", "generation_consistency": "unverified",
                        "consistency": "unverified", "results_accepted": False,
                        "merged_candidate_count": 0,
                    })

        candidates = [result for response in responses for result in response.results]
        candidates.sort(key=lambda result: (-result.score, result.document_id))
        trace.record("coordinator", "", "search_completed", self.clock.tick())
        return {
            "query": query,
            "results": [self._result_to_dict(result) for result in candidates[:final_top_k]],
            "node_status": sorted(statuses, key=lambda status: status["node_id"]),
            # Retain the existing meaning: a completed RPC, even if its results
            # were rejected. Separate counts describe safe/verified sources.
            "healthy_nodes": sum(status["status"] == "up" for status in statuses),
            "eligible_nodes": len(responses),
            "verified_nodes": sum(status["consistency"] == "consistent" for status in statuses),
            "total_nodes": len(self.config.nodes),
            "candidate_count": len(candidates),
            "received_candidate_count": sum(status.get("candidate_count", 0) for status in statuses),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "expected_statistics_version": expected["statistics_version"] if expected else None,
            "authority_error": authority_error,
            "request_id": request_id,
            # This is a presentation order, not proof of a total causal order.
            "logical_trace": sorted(trace.events, key=lambda event: (event["logical_timestamp"], event["process_id"])),
        }

    def _load_expected_statistics(self):
        path = self.config.global_statistics_file
        if path is None:
            return None, "Authoritative global_statistics_file is not configured."
        try:
            statistics = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            return None, f"Authoritative statistics could not be loaded: {error}"
        if not isinstance(statistics, dict):
            return None, "Authoritative statistics must be a JSON object."
        version = statistics.get("statistics_version")
        if not isinstance(version, str) or version != statistics_version(statistics):
            return None, "Authoritative statistics_version is missing or does not match its payload."
        return statistics, None

    def _search_node(self, node: NodeAddress, query: str, request_id: str, trace: _QueryTrace,
                     local_top_k: int | None = None):
        started = time.perf_counter()
        with grpc.insecure_channel(node.address) as channel:
            stub = search_pb2_grpc.SearchServiceStub(channel)
            sent = self.clock.tick()
            trace.record("coordinator", node.node_id, "request_sent", sent)
            try:
                response = stub.Search(search_pb2.SearchRequest(
                    query=query, top_k=local_top_k if local_top_k is not None else self.config.local_top_k,
                    request_id=request_id, logical_timestamp=sent,
                ), timeout=self.config.node_timeout_seconds)
            except grpc.RpcError:
                trace.record("coordinator", node.node_id, "rpc_failure_observed", self.clock.tick())
                raise
            received = self.clock.receive(response.response_sent_timestamp)
            trace.record("coordinator", node.node_id, "response_received", received)

        protocol_error = ""
        if response.node_id != node.node_id:
            protocol_error = "Response node ID does not match the configured node."
        elif not response.request_id and (
            response.request_received_timestamp or response.response_sent_timestamp or response.index_hash
            or response.expected_index_hash or response.index_consistency or response.index_consistency_error
        ):
            protocol_error = "Response contains modern diagnostics but no request ID for correlation."
        elif response.request_id and response.request_id != request_id:
            protocol_error = "Response request ID does not match this query."
        elif any(result.node_id != node.node_id for result in response.results):
            protocol_error = "Result node ID does not match the configured node."
        elif response.request_id and not (
            sent < response.request_received_timestamp < response.response_sent_timestamp
        ):
            protocol_error = "Response logical timestamps violate the request/response causal chain."
        if not protocol_error and response.request_id == request_id:
            trace.record(node.node_id, node.node_id, "request_received", response.request_received_timestamp)
            trace.record(node.node_id, node.node_id, "response_sent", response.response_sent_timestamp)
        return response, round((time.perf_counter() - started) * 1000, 2), protocol_error

    @staticmethod
    def _response_status(node, response, expected, protocol_error):
        errors = []
        local_state = response.index_consistency
        if local_state not in {"consistent", "inconsistent", "unverified"}:
            local_state = "unverified"
        actual_hash = response.index_hash
        local_expected = response.expected_index_hash
        if actual_hash and not _SHA256.fullmatch(actual_hash):
            local_state = "inconsistent"
            errors.append("Node reported a malformed actual index hash.")
        if local_expected and not _SHA256.fullmatch(local_expected):
            local_state = "inconsistent"
            errors.append("Node reported a malformed expected index hash.")
        if actual_hash and local_expected and actual_hash != local_expected:
            local_state = "inconsistent"
            errors.append("Node's actual index hash differs from its loaded metadata.")
        if local_state == "consistent" and not (actual_hash and local_expected):
            local_state = "unverified"
            errors.append("Node did not provide both hashes needed to verify its index.")
        if response.index_consistency_error:
            errors.append(response.index_consistency_error)

        generation_state = "unverified"
        authoritative_hash = ""
        authority_state = "unverified"
        if expected is not None:
            if response.statistics_version:
                generation_state = (
                    "matching" if response.statistics_version == expected["statistics_version"] else "mismatching"
                )
                if generation_state == "mismatching":
                    errors.append("Node statistics generation differs from the authoritative generation.")
            else:
                errors.append("Node did not report a statistics generation.")
            authoritative_hash, authority_state, metadata_error = index_metadata(expected, node.node_id)
            if metadata_error:
                errors.append(metadata_error)
            if authoritative_hash and actual_hash and actual_hash != authoritative_hash:
                authority_state = "inconsistent"
                errors.append("Node's actual index hash differs from the authoritative index hash.")
        else:
            errors.append("Authoritative generation is unavailable; cluster consistency is unverified.")

        if protocol_error:
            errors.append(protocol_error)
        if (protocol_error or local_state == "inconsistent" or authority_state == "inconsistent"
                or generation_state == "mismatching"):
            consistency = "inconsistent"
        elif local_state == "consistent" and authority_state == "consistent" and generation_state == "matching":
            consistency = "consistent"
        else:
            consistency = "unverified"
        accepted = consistency != "inconsistent"
        return {
            "node_id": node.node_id, "address": node.address, "status": "up", "rpc_state": "responding",
            "candidate_count": len(response.results), "statistics_version": response.statistics_version,
            "index_hash": actual_hash, "expected_index_hash": local_expected,
            "authoritative_index_hash": authoritative_hash,
            "index_consistency": local_state, "generation_consistency": generation_state,
            "consistency": consistency, "consistency_error": " ".join(errors),
            "results_accepted": accepted, "merged_candidate_count": len(response.results) if accepted else 0,
        }

    @staticmethod
    def _result_to_dict(result) -> dict[str, object]:
        return {"document_id": result.document_id, "score": result.score, "title": result.title, "url": result.url,
                "snippet": result.snippet, "node_id": result.node_id}
