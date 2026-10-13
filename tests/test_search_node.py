import copy
import json
import math
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from distributed_systems.integrity import sha256_bytes, statistics_version
from indexing.indexer.config import IndexConfig
from indexing.indexer.index_builder import build_index, save_index
from proto import search_pb2
from search_node.server import Service


class SearchNodeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.shard = root / "shard_1.jsonl"
        self.index = root / "node_1_index.json"
        self.stats = root / "global_statistics.json"
        documents = [{
            "document_id": document_id, "title": f"Title {document_id}",
            "url": f"http://example/{document_id}", "content": content,
        } for document_id, content in ((1, "alpha beta beta gamma"), (2, "alpha beta"), (3, "delta"))]
        self.shard.write_text("".join(json.dumps(document) + "\n" for document in documents), encoding="utf-8")
        index = build_index(IndexConfig(self.shard, self.index, 2, frozenset()))
        save_index(index, self.index)
        self.statistics = {
            "global_document_count": 4,
            "terms": {term: {"idf": math.log(4 / entry["document_frequency"])}
                      for term, entry in index["terms"].items()},
            "node_indexes": [{"node_id": "node_1", "shard_id": 1, "file": self.index.name,
                              "index_hash": sha256_bytes(self.index.read_bytes())}],
        }
        self.statistics["statistics_version"] = statistics_version(self.statistics)
        self.write_stats(self.statistics)

    def write_stats(self, statistics, regenerate_version=True):
        if regenerate_version:
            statistics["statistics_version"] = statistics_version(statistics)
        self.stats.write_text(json.dumps(statistics), encoding="utf-8")

    def service(self):
        return Service("node_1", self.index, self.shard, self.stats)

    def test_correct_hash_and_request_timestamps_are_propagated(self):
        service = self.service()
        self.assertEqual(service.clock.value, 0)
        response = service.Search(search_pb2.SearchRequest(
            query="alpha beta", top_k=2, request_id="query-1", logical_timestamp=41,
        ), None)
        self.assertEqual(response.request_id, "query-1")
        self.assertEqual(response.request_received_timestamp, 42)
        self.assertEqual(response.response_sent_timestamp, 43)
        self.assertEqual(response.statistics_version, self.statistics["statistics_version"])
        self.assertEqual(response.index_hash, self.statistics["node_indexes"][0]["index_hash"])
        self.assertEqual(response.index_hash, response.expected_index_hash)
        self.assertEqual(response.index_consistency, "consistent")
        self.assertEqual(response.index_consistency_error, "")

    def test_existing_cosine_scores_tokenization_and_top_k(self):
        service = self.service()
        response = service.Search(search_pb2.SearchRequest(query="ALPHA, beta!", top_k=2), None)
        self.assertEqual([result.document_id for result in response.results], [2, 1])
        self.assertAlmostEqual(response.results[0].score, 1)
        self.assertAlmostEqual(response.results[1].score, math.sqrt(2) / 2)
        self.assertEqual(response.results[1].snippet, "alpha beta beta gamma")
        limited = service.Search(search_pb2.SearchRequest(query="alpha beta", top_k=1), None)
        self.assertEqual([result.document_id for result in limited.results], [2])
        default = service.Search(search_pb2.SearchRequest(query="alpha beta"), None)
        self.assertEqual(len(default.results), 2)

    def test_empty_and_unknown_queries_still_return_diagnostics(self):
        service = self.service()
        for query in ("", "zzzz"):
            response = service.Search(search_pb2.SearchRequest(query=query, request_id=query), None)
            self.assertEqual(list(response.results), [])
            self.assertEqual(response.request_id, query)
            self.assertEqual(response.index_consistency, "consistent")
            self.assertGreater(response.response_sent_timestamp, response.request_received_timestamp)

    def test_mismatched_hash_is_inconsistent(self):
        self.statistics["node_indexes"][0]["index_hash"] = "0" * 64
        self.write_stats(self.statistics)
        response = self.service().Search(search_pb2.SearchRequest(query="alpha"), None)
        self.assertEqual(response.index_consistency, "inconsistent")
        self.assertNotEqual(response.index_hash, response.expected_index_hash)
        self.assertTrue(response.index_consistency_error)
        self.assertEqual(list(response.results), [])

    def test_missing_hash_or_metadata_is_unverified(self):
        missing_hash = copy.deepcopy(self.statistics)
        del missing_hash["node_indexes"][0]["index_hash"]
        missing_metadata = copy.deepcopy(self.statistics)
        del missing_metadata["node_indexes"]
        for statistics in (missing_hash, missing_metadata):
            with self.subTest(statistics=statistics):
                self.write_stats(statistics)
                response = self.service().Search(search_pb2.SearchRequest(query="alpha"), None)
                self.assertEqual(response.index_consistency, "unverified")
                self.assertEqual(response.expected_index_hash, "")
                self.assertTrue(response.index_consistency_error)
                self.assertTrue(response.results)

    def test_missing_version_is_reported_as_empty(self):
        del self.statistics["statistics_version"]
        self.write_stats(self.statistics, regenerate_version=False)
        response = self.service().Search(search_pb2.SearchRequest(query="alpha"), None)
        self.assertEqual(response.statistics_version, "")
        self.assertEqual(response.index_consistency, "unverified")
        self.assertIn("no statistics_version", response.index_consistency_error)
        self.assertTrue(response.results)

    def test_tampered_statistics_with_retained_version_are_inconsistent(self):
        original_version = self.statistics["statistics_version"]
        self.statistics["terms"]["alpha"]["idf"] = 99
        self.write_stats(self.statistics, regenerate_version=False)
        response = self.service().Search(search_pb2.SearchRequest(
            query="alpha", request_id="tampered", logical_timestamp=8,
        ), None)
        self.assertEqual(response.statistics_version, original_version)
        self.assertEqual(response.index_hash, response.expected_index_hash)
        self.assertEqual(response.index_consistency, "inconsistent")
        self.assertIn("Loaded statistics_version does not match its payload.", response.index_consistency_error)
        self.assertEqual(list(response.results), [])
        self.assertEqual(response.request_id, "tampered")
        self.assertEqual(response.request_received_timestamp, 9)
        self.assertEqual(response.response_sent_timestamp, 10)

    def test_invalid_statistics_versions_return_diagnostics(self):
        for value in (123, None, "wrong-version"):
            with self.subTest(value=value):
                self.statistics["statistics_version"] = value
                self.write_stats(self.statistics, regenerate_version=False)
                response = self.service().Search(search_pb2.SearchRequest(query="alpha"), None)
                self.assertEqual(response.index_consistency, "inconsistent")
                self.assertIn("does not match its payload", response.index_consistency_error)
                self.assertEqual(list(response.results), [])
                self.assertEqual(response.statistics_version, value if isinstance(value, str) else "")

    def test_empty_statistics_version_is_unverified(self):
        self.statistics["statistics_version"] = ""
        self.write_stats(self.statistics, regenerate_version=False)
        response = self.service().Search(search_pb2.SearchRequest(query="alpha"), None)
        self.assertEqual(response.statistics_version, "")
        self.assertEqual(response.index_consistency, "unverified")
        self.assertIn("no statistics_version", response.index_consistency_error)
        self.assertTrue(response.results)

    def test_known_index_mismatch_with_foreign_term_returns_diagnostics(self):
        index = json.loads(self.index.read_bytes())
        index["terms"]["foreign"] = index["terms"].pop("alpha")
        self.index.write_text(json.dumps(index), encoding="utf-8")
        service = self.service()
        response = service.Search(search_pb2.SearchRequest(
            query="foreign", request_id="foreign-index", logical_timestamp=15,
        ), None)
        self.assertEqual(service.norm, {})
        self.assertEqual(response.index_consistency, "inconsistent")
        self.assertIn("Loaded index hash does not match", response.index_consistency_error)
        self.assertNotEqual(response.index_hash, response.expected_index_hash)
        self.assertEqual(list(response.results), [])
        self.assertEqual(response.request_id, "foreign-index")
        self.assertEqual(response.request_received_timestamp, 16)
        self.assertEqual(response.response_sent_timestamp, 17)

    def test_unexpected_required_schema_error_is_not_suppressed(self):
        del self.statistics["terms"]
        self.write_stats(self.statistics)
        with self.assertRaises(KeyError):
            self.service()

    def test_malformed_or_duplicate_metadata_is_inconsistent(self):
        malformed = copy.deepcopy(self.statistics)
        malformed["node_indexes"][0]["index_hash"] = "not-a-hash"
        duplicate = copy.deepcopy(self.statistics)
        duplicate["node_indexes"].append(dict(duplicate["node_indexes"][0]))
        for statistics in (malformed, duplicate):
            with self.subTest(statistics=statistics):
                self.write_stats(statistics)
                response = self.service().Search(search_pb2.SearchRequest(query="alpha"), None)
                self.assertEqual(response.index_consistency, "inconsistent")
                self.assertTrue(response.index_consistency_error)

    def test_concurrent_searches_share_clock_and_keep_request_ids(self):
        service = self.service()

        def search(index):
            return service.Search(search_pb2.SearchRequest(
                query="alpha", request_id=f"query-{index}", logical_timestamp=0,
            ), None)

        with ThreadPoolExecutor(max_workers=8) as executor:
            responses = list(executor.map(search, range(100)))
        timestamps = []
        for index, response in enumerate(responses):
            self.assertEqual(response.request_id, f"query-{index}")
            self.assertGreater(response.response_sent_timestamp, response.request_received_timestamp)
            timestamps.extend((response.request_received_timestamp, response.response_sent_timestamp))
        self.assertEqual(sorted(timestamps), list(range(1, 201)))
        self.assertEqual(service.clock.value, 200)

    def test_fingerprint_and_parse_use_one_loaded_byte_sequence(self):
        original_bytes = self.index.read_bytes()
        real_read_bytes = Path.read_bytes
        reads = []

        def read_bytes(path):
            if path == self.index:
                reads.append(path)
                return original_bytes
            return real_read_bytes(path)

        with patch.object(Path, "read_bytes", read_bytes):
            service = self.service()
        self.assertEqual(reads, [self.index])
        # A later file replacement does not change the loaded search artifact.
        self.index.write_bytes(b"{}")
        response = service.Search(search_pb2.SearchRequest(query="alpha"), None)
        self.assertEqual(response.index_hash, sha256_bytes(original_bytes))
        self.assertEqual(response.index_consistency, "consistent")
        self.assertTrue(response.results)


if __name__ == "__main__":
    unittest.main()
