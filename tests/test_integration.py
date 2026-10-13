"""Actual saved indexes and loopback gRPC verify the full query boundary."""

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path

from coordinator.engine.config import CoordinatorConfig, NodeAddress
from coordinator.engine.coordinator import SearchCoordinator
from tests.helpers import build_fixture, running_node, service_for


class DistributedSearchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = build_fixture(self.root / "current")

    def search_with(self, services):
        with ExitStack() as stack:
            addresses = [stack.enter_context(running_node(service)) for service in services]
            config = CoordinatorConfig(tuple(NodeAddress(f"node_{ordinal}", address)
                                             for ordinal, address in enumerate(addresses, 1)),
                                       0.5, 5, 3, self.fixture["statistics_path"])
            return SearchCoordinator(config).search("clock")

    def test_real_grpc_search_returns_ranked_results_and_causal_trace(self):
        result = self.search_with([service_for(self.fixture, 1), service_for(self.fixture, 2)])
        self.assertEqual((result["healthy_nodes"], result["eligible_nodes"], result["verified_nodes"]), (2, 2, 2))
        self.assertEqual({item["document_id"] for item in result["results"]}, {1, 3})
        scores = [item["score"] for item in result["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertGreater(result["elapsed_ms"], 0)
        for node_id in ("node_1", "node_2"):
            events = {event["event"]: event["logical_timestamp"] for event in result["logical_trace"]
                      if event.get("node_id") == node_id}
            self.assertLess(events["request_sent"], events["request_received"])
            self.assertLess(events["request_received"], events["response_sent"])
            self.assertLess(events["response_sent"], events["response_received"])

    def test_real_stale_node_matches_its_local_pair_but_is_excluded(self):
        old = build_fixture(self.root / "old", ["old clock document", "metadata old", "clock archive", "web archived"])
        result = self.search_with([service_for(self.fixture, 1), service_for(old, 2)])
        self.assertEqual((result["healthy_nodes"], result["eligible_nodes"], result["verified_nodes"]), (2, 1, 1))
        self.assertEqual([item["document_id"] for item in result["results"]], [1])
        stale = result["node_status"][1]
        self.assertEqual(stale["index_consistency"], "consistent")
        self.assertEqual(stale["generation_consistency"], "mismatching")
        self.assertFalse(stale["results_accepted"])

    def test_real_invalid_saved_index_is_excluded_with_useful_partial_results(self):
        index_path = self.fixture["indexes"] / "node_2_index.json"
        # Whitespace changes actual saved bytes while keeping a valid search index.
        index_path.write_bytes(index_path.read_bytes() + b"\n")
        result = self.search_with([service_for(self.fixture, 1), service_for(self.fixture, 2)])
        self.assertEqual((result["healthy_nodes"], result["eligible_nodes"]), (2, 1))
        self.assertEqual([item["document_id"] for item in result["results"]], [1])
        invalid = result["node_status"][1]
        self.assertEqual(invalid["index_consistency"], "inconsistent")
        self.assertNotEqual(invalid["index_hash"], invalid["expected_index_hash"])
        self.assertTrue(invalid["consistency_error"])


if __name__ == "__main__":
    unittest.main()
