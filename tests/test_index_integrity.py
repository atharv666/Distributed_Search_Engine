import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from distributed_indexing.builder.build import build_distributed_indexes
from distributed_indexing.builder.config import DistributedIndexConfig
from distributed_systems.integrity import index_metadata, sha256_bytes, statistics_version


class IndexMetadataTests(unittest.TestCase):
    def setUp(self):
        self.statistics = {"node_indexes": [{
            "node_id": "node_1", "shard_id": 1, "file": "node_1_index.json", "index_hash": "a" * 64,
        }]}

    def test_valid_metadata_identifies_expected_hash(self):
        self.assertEqual(index_metadata(self.statistics, "node_1"), ("a" * 64, "consistent", ""))

    def test_missing_metadata_or_hash_is_unverified(self):
        cases = ({}, {"node_indexes": []}, {"node_indexes": None})
        for statistics in cases:
            with self.subTest(statistics=statistics):
                self.assertEqual(index_metadata(statistics, "node_1")[1], "unverified")
        del self.statistics["node_indexes"][0]["index_hash"]
        expected_hash, state, error = index_metadata(self.statistics, "node_1")
        self.assertEqual(expected_hash, "")
        self.assertEqual(state, "unverified")
        self.assertTrue(error)

    def test_duplicate_or_conflicting_mapping_is_inconsistent(self):
        entry = self.statistics["node_indexes"][0]
        self.statistics["node_indexes"].append(dict(entry))
        self.assertEqual(index_metadata(self.statistics, "node_1")[1], "inconsistent")
        self.statistics["node_indexes"] = [dict(entry, shard_id=2)]
        self.assertEqual(index_metadata(self.statistics, "node_1")[1], "inconsistent")
        self.statistics["node_indexes"] = [dict(entry, file="wrong_index.json")]
        self.assertEqual(index_metadata(self.statistics, "node_1")[1], "inconsistent")

    def test_malformed_metadata_is_inconsistent(self):
        cases = ([], {"node_indexes": {}}, {"node_indexes": [None]})
        for statistics in cases:
            with self.subTest(statistics=statistics):
                self.assertEqual(index_metadata(statistics, "node_1")[1], "inconsistent")
        for key, value in (("index_hash", "bad"), ("index_hash", 123), ("shard_id", True)):
            statistics = copy.deepcopy(self.statistics)
            statistics["node_indexes"][0][key] = value
            with self.subTest(key=key, value=value):
                self.assertEqual(index_metadata(statistics, "node_1")[1], "inconsistent")

    def test_version_is_canonical_and_excludes_its_derived_field(self):
        first = {"terms": {"alpha": {"idf": 1, "document_frequency": 2}}, **self.statistics}
        reverse = {"node_indexes": first["node_indexes"], "terms": first["terms"], "statistics_version": "old"}
        self.assertEqual(statistics_version(first), statistics_version(reverse))
        changed = copy.deepcopy(first)
        changed["node_indexes"][0]["index_hash"] = "b" * 64
        self.assertNotEqual(statistics_version(first), statistics_version(changed))

    def test_hash_is_of_exact_bytes(self):
        data = b'{"data": 1}\n'
        self.assertEqual(sha256_bytes(data), hashlib.sha256(data).hexdigest())
        self.assertNotEqual(sha256_bytes(data), sha256_bytes(data.rstrip()))


class DistributedBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.shards = root / "shards"
        self.shards.mkdir()
        self.manifest = self.shards / "partition_manifest.json"
        self.manifest_data = {"global_document_count": 2, "shards": [
            {"shard_id": 1, "file": "shard_1.jsonl", "document_count": 1},
            {"shard_id": 2, "file": "shard_2.jsonl", "document_count": 1},
        ]}
        self.manifest.write_text(json.dumps(self.manifest_data), encoding="utf-8")
        for shard_id, content in ((1, "alpha beta"), (2, "beta gamma")):
            (self.shards / f"shard_{shard_id}.jsonl").write_text(json.dumps({
                "document_id": shard_id, "content": content, "title": content, "url": f"http://example/{shard_id}",
            }) + "\n", encoding="utf-8")
        self.config = DistributedIndexConfig(
            shards_directory=self.shards, partition_manifest=self.manifest,
            indexes_directory=root / "indexes", global_statistics_file=root / "global_statistics.json",
            minimum_token_length=2, excluded_tokens=frozenset(),
        )

    def test_saved_index_fingerprints_and_version_are_written(self):
        statistics = build_distributed_indexes(self.config)
        self.assertEqual(statistics, json.loads(self.config.global_statistics_file.read_bytes()))
        for entry in statistics["node_indexes"]:
            artifact = (self.config.indexes_directory / entry["file"]).read_bytes()
            self.assertEqual(entry["index_hash"], hashlib.sha256(artifact).hexdigest())
            self.assertEqual(index_metadata(statistics, entry["node_id"])[1], "consistent")
        self.assertEqual(statistics["statistics_version"], statistics_version(statistics))

    def test_rebuild_is_stable_and_document_change_changes_generation(self):
        first = build_distributed_indexes(self.config)
        first_bytes = self.config.global_statistics_file.read_bytes()
        self.assertEqual(first, build_distributed_indexes(self.config))
        self.assertEqual(first_bytes, self.config.global_statistics_file.read_bytes())
        # Changing word order preserves global DF/IDF, but changes saved postings.
        shard = self.shards / "shard_1.jsonl"
        document = json.loads(shard.read_bytes())
        document["content"] = "beta alpha"
        shard.write_text(json.dumps(document) + "\n", encoding="utf-8")
        changed = build_distributed_indexes(self.config)
        self.assertEqual(first["terms"], changed["terms"])
        self.assertNotEqual(first["node_indexes"][0]["index_hash"], changed["node_indexes"][0]["index_hash"])
        self.assertNotEqual(first["statistics_version"], changed["statistics_version"])

    def test_duplicate_shard_ids_are_rejected_before_artifacts_are_written(self):
        self.manifest_data["shards"].append(dict(self.manifest_data["shards"][0]))
        self.manifest.write_text(json.dumps(self.manifest_data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate shard ID"):
            build_distributed_indexes(self.config)
        self.assertFalse(self.config.indexes_directory.exists())
        self.assertFalse(self.config.global_statistics_file.exists())


if __name__ == "__main__":
    unittest.main()
