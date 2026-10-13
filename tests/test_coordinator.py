"""Exercise fan-out, authoritative consistency decisions, and causal traces."""

import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from coordinator.engine.config import CoordinatorConfig, NodeAddress, load_config
from coordinator.engine.coordinator import SearchCoordinator
from tests.helpers import DeadlineExceeded, authority_statistics, mocked_nodes, response_for, write_statistics


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.authority = Path(self.temporary.name) / "statistics.json"
        self.hashes = {"node_1": "a" * 64, "node_2": "b" * 64}
        self.statistics = authority_statistics(self.hashes)
        self.version = write_statistics(self.authority, self.statistics)
        self.nodes = tuple(NodeAddress(node_id, node_id) for node_id in self.hashes)

    def coordinator(self, authority=True):
        return SearchCoordinator(CoordinatorConfig(self.nodes, 0.25, 5, 3, self.authority if authority else None))

    def responders(self, **overrides):
        callbacks = {}
        for ordinal, node in enumerate(self.nodes, 1):
            callbacks[node.address] = lambda request, timeout, node=node, ordinal=ordinal: response_for(
                request, node.node_id, self.version, self.hashes[node.node_id], [(ordinal, 0.5)],
                **overrides.get(node.node_id, {}))
        return callbacks

    @staticmethod
    def statuses(result):
        return {status["node_id"]: status for status in result["node_status"]}

    def test_verified_results_keep_global_top_k_tie_order_and_latency(self):
        captured = []
        lock = threading.Lock()

        def search(request, timeout, node_id, documents):
            with lock:
                captured.append((request.request_id, request.query, request.top_k, request.logical_timestamp, timeout))
            time.sleep(0.005)
            return response_for(request, node_id, self.version, self.hashes[node_id], documents)

        callbacks = {"node_1": lambda request, timeout: search(request, timeout, "node_1", [(7, 0.9), (4, 0.7)]),
                     "node_2": lambda request, timeout: search(request, timeout, "node_2", [(3, 0.9), (8, 0.2)])}
        with mocked_nodes(callbacks):
            result = self.coordinator().search("clock", top_k=3)
        self.assertEqual([item["document_id"] for item in result["results"]], [3, 7, 4])
        self.assertEqual((result["healthy_nodes"], result["eligible_nodes"], result["verified_nodes"]), (2, 2, 2))
        self.assertEqual((result["candidate_count"], result["received_candidate_count"]), (4, 4))
        self.assertEqual(result["expected_statistics_version"], self.version)
        self.assertGreater(result["elapsed_ms"], 0)
        self.assertTrue(all(status["latency_ms"] > 0 for status in result["node_status"]))
        self.assertTrue(all(value[0] == result["request_id"] and value[1] == "clock" and value[2] == 5
                            and value[3] > 0 and value[4] == 0.25 for value in captured))

    def test_request_response_trace_has_lamport_causal_chain(self):
        with mocked_nodes(self.responders()):
            result = self.coordinator().search("clock")
        trace = result["logical_trace"]
        self.assertTrue(all(event["request_id"] == result["request_id"] for event in trace))
        for node in self.nodes:
            events = {event["event"]: event["logical_timestamp"] for event in trace if event.get("node_id") == node.node_id}
            self.assertLess(events["request_sent"], events["request_received"])
            self.assertLess(events["request_received"], events["response_sent"])
            self.assertLess(events["response_sent"], events["response_received"])

    def test_stale_correct_local_pair_is_excluded_against_current_authority(self):
        stale = {"statistics_version": "stale-generation", "index_hash": "c" * 64, "expected_index_hash": "c" * 64}
        with mocked_nodes(self.responders(node_2=stale)):
            result = self.coordinator().search("clock")
        self.assertEqual([item["document_id"] for item in result["results"]], [1])
        self.assertEqual((result["healthy_nodes"], result["eligible_nodes"], result["verified_nodes"]), (2, 1, 1))
        self.assertEqual((result["candidate_count"], result["received_candidate_count"]), (1, 2))
        status = self.statuses(result)["node_2"]
        self.assertEqual(status["status"], "up")
        self.assertEqual(status["index_consistency"], "consistent")
        self.assertEqual(status["generation_consistency"], "mismatching")
        self.assertEqual(status["consistency"], "inconsistent")
        self.assertFalse(status["results_accepted"])
        self.assertEqual(status["merged_candidate_count"], 0)
        self.assertTrue(status["consistency_error"])

    def test_changed_actual_hash_is_excluded_even_if_node_claims_consistent(self):
        with mocked_nodes(self.responders(node_2={"index_hash": "c" * 64})):
            result = self.coordinator().search("clock")
        self.assertEqual([item["document_id"] for item in result["results"]], [1])
        self.assertEqual(self.statuses(result)["node_2"]["consistency"], "inconsistent")

    def test_explicit_local_hash_mismatch_is_excluded_without_authority(self):
        override = {"index_hash": "c" * 64, "index_consistency": "inconsistent",
                    "index_consistency_error": "Saved index fingerprint differs."}
        with mocked_nodes(self.responders(node_2=override)):
            result = self.coordinator(authority=False).search("clock")
        self.assertEqual(result["verified_nodes"], 0)
        self.assertEqual([item["document_id"] for item in result["results"]], [1])
        self.assertEqual(self.statuses(result)["node_1"]["consistency"], "unverified")
        self.assertEqual(self.statuses(result)["node_2"]["consistency"], "inconsistent")

    def test_unavailable_authority_preserves_explicitly_unverified_results(self):
        for authority in (False, True):
            with self.subTest(configured=authority):
                if authority:
                    self.authority.unlink()
                with mocked_nodes(self.responders()):
                    result = self.coordinator(authority=authority).search("clock")
                self.assertEqual((result["eligible_nodes"], result["verified_nodes"]), (2, 0))
                self.assertEqual(len(result["results"]), 2)
                self.assertTrue(result["authority_error"])
                self.assertTrue(all(status["consistency"] == "unverified" for status in result["node_status"]))

    def test_missing_expected_hash_never_verifies_a_node(self):
        del self.statistics["node_indexes"][1]["index_hash"]
        self.version = write_statistics(self.authority, self.statistics)
        with mocked_nodes(self.responders(node_2={"expected_index_hash": "", "index_consistency": "unverified"})):
            result = self.coordinator().search("clock")
        status = self.statuses(result)["node_2"]
        self.assertEqual(status["consistency"], "unverified")
        self.assertTrue(status["results_accepted"])
        self.assertEqual(result["verified_nodes"], 1)

    def test_malformed_authority_and_invalid_version_are_reported(self):
        for payload in ("{not json", json.dumps({**self.statistics, "statistics_version": "incorrect"})):
            with self.subTest(payload=payload):
                self.authority.write_text(payload, encoding="utf-8")
                with mocked_nodes(self.responders()):
                    result = self.coordinator().search("clock")
                self.assertEqual(result["verified_nodes"], 0)
                self.assertTrue(result["authority_error"])
                self.assertTrue(all(status["generation_consistency"] == "unverified" for status in result["node_status"]))

    def test_invalid_metadata_hash_is_not_reported_verified(self):
        self.statistics["node_indexes"][1]["index_hash"] = "not-a-sha256"
        self.version = write_statistics(self.authority, self.statistics)
        with mocked_nodes(self.responders()):
            result = self.coordinator().search("clock")
        self.assertNotEqual(self.statuses(result)["node_2"]["consistency"], "consistent")
        self.assertTrue(self.statuses(result)["node_2"]["consistency_error"] or result["authority_error"])

    def test_authority_is_reloaded_for_next_search(self):
        coordinator = self.coordinator()
        with mocked_nodes(self.responders()):
            first = coordinator.search("clock")
            self.statistics["global_document_count"] += 1
            new_version = write_statistics(self.authority, self.statistics)
            second = coordinator.search("clock")
        self.assertEqual(first["verified_nodes"], 2)
        self.assertEqual(second["expected_statistics_version"], new_version)
        self.assertEqual(second["eligible_nodes"], 0)

    def test_timeout_keeps_partial_results_and_records_failure_event(self):
        def fail(request, timeout):
            raise DeadlineExceeded()

        callbacks = self.responders()
        callbacks["node_2"] = fail
        with mocked_nodes(callbacks):
            result = self.coordinator().search("clock")
        self.assertEqual((result["healthy_nodes"], result["eligible_nodes"]), (1, 1))
        self.assertEqual([item["document_id"] for item in result["results"]], [1])
        status = self.statuses(result)["node_2"]
        self.assertEqual(status["status"], "unavailable")
        self.assertEqual(status["error"], "DEADLINE_EXCEEDED")
        failures = [event for event in result["logical_trace"] if event["event"] == "rpc_failure_observed"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["node_id"], "node_2")
        self.assertGreater(failures[0]["logical_timestamp"], 0)

    def test_response_identity_mismatches_reject_candidates(self):
        overrides = [{"request_id": "another-request"}, {"node_id": "another-node"}, {"node_id": ""}]
        for override in overrides:
            with self.subTest(override=override):
                with mocked_nodes(self.responders(node_2=override)):
                    result = self.coordinator().search("clock")
                self.assertEqual(result["eligible_nodes"], 1)
                self.assertFalse(self.statuses(result)["node_2"]["results_accepted"])
                self.assertTrue(self.statuses(result)["node_2"]["consistency_error"])
                self.assertFalse(any(event["process_id"] == "node_2" and event["event"] in {"request_received", "response_sent"}
                                     for event in result["logical_trace"]))

    def test_mismatched_result_node_identity_rejects_candidates(self):
        callbacks = self.responders()
        original = callbacks["node_2"]

        def wrong_result(request, timeout):
            response = original(request, timeout)
            response.results[0].node_id = "another-node"
            return response

        callbacks["node_2"] = wrong_result
        with mocked_nodes(callbacks):
            result = self.coordinator().search("clock")
        self.assertEqual(result["eligible_nodes"], 1)

    def test_response_with_invalid_causal_timestamps_is_rejected(self):
        callbacks = self.responders()
        original = callbacks["node_2"]

        def impossible_receive(request, timeout):
            response = original(request, timeout)
            response.request_received_timestamp = request.logical_timestamp
            return response

        callbacks["node_2"] = impossible_receive
        with mocked_nodes(callbacks):
            result = self.coordinator().search("clock")
        self.assertEqual(result["eligible_nodes"], 1)
        self.assertFalse(self.statuses(result)["node_2"]["results_accepted"])

    def test_explicit_nonpositive_top_k_is_rejected(self):
        for top_k in (0, -1):
            with self.subTest(top_k=top_k), self.assertRaises(ValueError):
                self.coordinator().search("clock", top_k=top_k)

    def test_larger_top_k_override_fetches_enough_candidates_from_each_node(self):
        observed = []

        def respond(request, timeout, node_id):
            observed.append(request.top_k)
            documents = [(ordinal, 1 - ordinal / 10) for ordinal in range(1, request.top_k + 1)]
            return response_for(request, node_id, self.version, self.hashes[node_id], documents)

        coordinator = SearchCoordinator(CoordinatorConfig(self.nodes, 0.25, 2, 2, self.authority))
        callbacks = {node.node_id: (lambda request, timeout, node=node: respond(request, timeout, node.node_id))
                     for node in self.nodes}
        with mocked_nodes(callbacks):
            result = coordinator.search("clock", top_k=3)
        self.assertEqual(observed, [3, 3])
        self.assertEqual(len(result["results"]), 3)

    def test_legacy_response_is_accepted_but_unverified(self):
        legacy = {"request_id": "", "request_received_timestamp": 0, "response_sent_timestamp": 0,
                  "index_hash": "", "expected_index_hash": "", "index_consistency": ""}
        with mocked_nodes(self.responders(node_1=legacy, node_2=legacy)):
            result = self.coordinator().search("clock")
        self.assertEqual((result["healthy_nodes"], result["eligible_nodes"], result["verified_nodes"]), (2, 2, 0))
        self.assertTrue(all(status["consistency"] == "unverified" for status in result["node_status"]))

    def test_modern_response_missing_request_correlation_is_rejected_despite_matching_hashes(self):
        uncorrelated = {"request_id": "", "request_received_timestamp": 0, "response_sent_timestamp": 0}
        with mocked_nodes(self.responders(node_1=uncorrelated, node_2=uncorrelated)):
            result = self.coordinator().search("clock")
        self.assertEqual((result["healthy_nodes"], result["eligible_nodes"], result["verified_nodes"]), (2, 0, 0))
        self.assertTrue(all(status["consistency"] == "inconsistent" and not status["results_accepted"]
                            for status in result["node_status"]))
        self.assertFalse(any(event["event"] in {"request_received", "response_sent"} for event in result["logical_trace"]))

    def test_simultaneous_queries_have_unique_ids_isolated_traces_and_shared_clock(self):
        coordinator = self.coordinator()
        barrier = threading.Barrier(8)

        def respond(request, timeout, node_id, ordinal):
            barrier.wait(timeout=5)
            return response_for(request, node_id, self.version, self.hashes[node_id], [(ordinal, 0.5)])

        callbacks = {node.node_id: (lambda request, timeout, node=node, ordinal=ordinal:
                                     respond(request, timeout, node.node_id, ordinal))
                     for ordinal, node in enumerate(self.nodes, 1)}
        with mocked_nodes(callbacks), ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(coordinator.search, ["query one", "query two", "query three", "query four"]))
        self.assertEqual(len({result["request_id"] for result in results}), 4)
        coordinator_timestamps = []
        for result in results:
            self.assertTrue(all(event["request_id"] == result["request_id"] for event in result["logical_trace"]))
            self.assertTrue(all(item["snippet"] == result["query"] for item in result["results"]))
            self.assertEqual(sum(event["event"] == "request_sent" for event in result["logical_trace"]), 2)
            coordinator_timestamps.extend(event["logical_timestamp"] for event in result["logical_trace"]
                                          if event["process_id"] == "coordinator")
        self.assertEqual(len(coordinator_timestamps), len(set(coordinator_timestamps)))
        with mocked_nodes(self.responders()):
            next_result = coordinator.search("next request")
        self.assertGreater(min(event["logical_timestamp"] for event in next_result["logical_trace"]
                               if event["process_id"] == "coordinator"), max(coordinator_timestamps))

    def test_coordinator_config_resolves_authority_relative_to_component(self):
        config_dir = Path(self.temporary.name) / "coordinator" / "config"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "coordinator_config.json"
        config_path.write_text(json.dumps({"nodes": [{"node_id": "node_1", "address": "127.0.0.1:1"}],
                                         "node_timeout_seconds": 1, "local_top_k": 5, "final_top_k": 3,
                                         "global_statistics_file": "../../statistics.json"}), encoding="utf-8")
        config = load_config(config_path)
        self.assertEqual(config.global_statistics_file.resolve(), (config_dir.parent / "../../statistics.json").resolve())


if __name__ == "__main__":
    unittest.main()
