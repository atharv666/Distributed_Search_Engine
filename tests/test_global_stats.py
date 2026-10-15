import json
import math
import tempfile
import unittest
from pathlib import Path

from distributed_systems.global_stats import APPLIED, DUPLICATE, GAP, GlobalStats


def write_base(directory: Path) -> None:
    (directory / "indexes").mkdir(parents=True)
    (directory / "shards").mkdir(parents=True)
    (directory / "indexes" / "global_statistics.json").write_text(json.dumps({
        "global_document_count": 4,
        "terms": {"alpha": {"document_frequency": 2}, "beta": {"document_frequency": 4}}}), encoding="utf-8")
    (directory / "shards" / "partition_manifest.json").write_text(json.dumps({"shards": [
        {"shard_id": 1, "document_count": 2, "document_id_end": 2},
        {"shard_id": 2, "document_count": 2, "document_id_end": 4}]}), encoding="utf-8")


def delta(version: int, doc_id: int, node: str, *terms: str) -> dict:
    return {"version": version, "doc_id": doc_id, "node_id": node, "terms": list(terms), "title": "t", "url": "u"}


class GlobalStatsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.data = Path(self.temporary.name)
        write_base(self.data)

    def tearDown(self):
        self.temporary.cleanup()

    def test_base_state(self):
        stats = GlobalStats(self.data, "N1")
        self.assertEqual((stats.version, stats.n, stats.next_doc_id), (0, 4, 5))
        self.assertEqual(stats.node_counts, {"N1": 2, "N2": 2})
        self.assertAlmostEqual(stats.idf("alpha"), math.log(4 / 2))
        self.assertEqual(stats.idf("beta"), 0.0)

    def test_delta_changes_n_df_and_every_idf(self):
        stats = GlobalStats(self.data, "N1")
        before = stats.idf("alpha")
        self.assertEqual(stats.apply(delta(1, 5, "N1", "alpha", "gamma", "gamma")), APPLIED)
        self.assertEqual((stats.n, stats.df["alpha"], stats.df["gamma"], stats.node_counts["N1"]), (5, 3, 1, 3))
        self.assertAlmostEqual(stats.idf("alpha"), math.log(5 / 3))
        self.assertNotAlmostEqual(stats.idf("alpha"), before)
        self.assertAlmostEqual(stats.idf("beta"), math.log(5 / 4))     # untouched term, but N changed
        self.assertEqual(stats.next_doc_id, 6)

    def test_ordering_rules(self):
        stats = GlobalStats(self.data, "N1")
        self.assertEqual(stats.apply(delta(2, 6, "N2", "alpha")), GAP)
        self.assertEqual(stats.apply(delta(1, 5, "N1", "alpha")), APPLIED)
        self.assertEqual(stats.apply(delta(1, 5, "N1", "alpha")), DUPLICATE)
        self.assertEqual(stats.n, 5)
        self.assertEqual([d["version"] for d in stats.deltas_since(0)], [1])

    def test_log_replay_restores_state_after_restart(self):
        first = GlobalStats(self.data, "N2")
        first.apply(delta(1, 5, "N2", "alpha"))
        first.apply(delta(2, 6, "N1", "beta"))
        second = GlobalStats(self.data, "N2")
        self.assertEqual((second.version, second.n, second.df["beta"]), (2, 6, 5))
        self.assertEqual(second.node_counts, {"N1": 3, "N2": 3})
        other = GlobalStats(self.data, "N3")                # a different process has its own log
        self.assertEqual(other.version, 0)


if __name__ == "__main__":
    unittest.main()
