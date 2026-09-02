"""Concurrent gRPC fan-out, degraded-mode handling, and global Top-K merge."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import grpc

from proto import search_pb2, search_pb2_grpc

from .config import CoordinatorConfig, NodeAddress


class SearchCoordinator:
    def __init__(self, config: CoordinatorConfig) -> None:
        self.config = config

    def search(self, query: str, top_k: int | None = None) -> dict[str, object]:
        final_top_k = top_k or self.config.final_top_k
        if final_top_k <= 0:
            raise ValueError("top_k must be positive.")
        started = time.perf_counter()
        responses = []
        statuses = []
        with ThreadPoolExecutor(max_workers=len(self.config.nodes)) as pool:
            futures = {pool.submit(self._search_node, node, query): node for node in self.config.nodes}
            for future in as_completed(futures):
                node = futures[future]
                try:
                    response, latency_ms = future.result()
                    responses.append(response)
                    statuses.append({"node_id": node.node_id, "address": node.address, "status": "up", "latency_ms": latency_ms,
                                     "candidate_count": len(response.results), "statistics_version": response.statistics_version})
                except grpc.RpcError as error:
                    statuses.append({"node_id": node.node_id, "address": node.address, "status": "unavailable", "error": error.code().name})

        candidates = [result for response in responses for result in response.results]
        candidates.sort(key=lambda result: (-result.score, result.document_id))
        return {
            "query": query,
            "results": [self._result_to_dict(result) for result in candidates[:final_top_k]],
            "node_status": sorted(statuses, key=lambda status: status["node_id"]),
            "healthy_nodes": len(responses),
            "total_nodes": len(self.config.nodes),
            "candidate_count": len(candidates),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def _search_node(self, node: NodeAddress, query: str):
        started = time.perf_counter()
        with grpc.insecure_channel(node.address) as channel:
            stub = search_pb2_grpc.SearchServiceStub(channel)
            response = stub.Search(search_pb2.SearchRequest(query=query, top_k=self.config.local_top_k), timeout=self.config.node_timeout_seconds)
        return response, round((time.perf_counter() - started) * 1000, 2)

    @staticmethod
    def _result_to_dict(result) -> dict[str, object]:
        return {"document_id": result.document_id, "score": result.score, "title": result.title, "url": result.url,
                "snippet": result.snippet, "node_id": result.node_id}
