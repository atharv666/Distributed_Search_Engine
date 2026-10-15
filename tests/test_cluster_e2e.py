"""End-to-end test: real processes, real gRPC, real failures.

It starts the web server, which starts three coordinators and three nodes on spare ports with
a temporary copy of the data and fast timers (1 s beacon, 3 s timeout). It then adds documents,
kills the leader, revives it, kills a node, and checks vector-clock invariants on every event.
"""

import tempfile
import unittest
from pathlib import Path

from distributed_systems.rpc import quiet_call
from distributed_systems.vector_clock import compare
from proto import search_pb2, search_pb2_grpc

from .helpers import NODE_PORT_BASE, WebServer, data_available, make_workspace, wait_for

LONG_TEXT = ("The {word} migrates across the plains while the {word} herd studies {word} patterns, "
             "gRPC communication and distributed coordination over long distances.")


def text_document(word: str) -> dict:
    return {"title": f"{word.title()} field guide", "content": LONG_TEXT.format(word=word)}


@unittest.skipUnless(data_available(), "base data (data/documents.jsonl, shards, statistics) is not built")
class ClusterEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.web = WebServer(make_workspace(Path(cls.temporary.name)))
        cls.web.start()
        cls.web.post("/api/admin/start-all")
        wait_for(lambda: cls.running_count() == 6 and cls.web.cluster()["leader"], 45, "cluster did not come up")

    @classmethod
    def tearDownClass(cls):
        cls.web.stop()
        try:
            cls.temporary.cleanup()
        except OSError:
            pass

    @classmethod
    def running_count(cls) -> int:
        return sum(item["state"] == "running" for item in cls.web.cluster()["processes"])

    @classmethod
    def leader_is(cls, process_id: str, minimum_epoch: int = 1) -> bool:
        cluster = cls.web.cluster()
        return cluster["leader"] == process_id and cluster["epoch"] >= minimum_epoch

    def add(self, *words: str) -> list[dict]:
        reply = self.web.post("/api/admin/documents", {"texts": [text_document(word) for word in words]})
        self.assertNotIn("http_error", reply, reply)
        for result in reply["results"]:
            self.assertTrue(result["ok"], result)
        return reply["results"]

    def events_named(self, name: str, **details) -> list[dict]:
        return [event for event in self.web.all_events() if event["name"] == name
                and all(event["details"].get(key) == value for key, value in details.items())]

    # ------------------------------------------------------------------------------------------
    def test_01_cluster_boots_with_highest_ranked_coordinator_as_leader(self):
        cluster = self.web.cluster()
        self.assertEqual(cluster["leader"], "C3")
        self.assertEqual(cluster["epoch"], 1)
        roles = {item["id"]: item["role"] for item in cluster["processes"]}
        self.assertEqual((roles["C1"], roles["C2"], roles["C3"]), ("STANDBY", "STANDBY", "LEADER"))
        for node in ("N1", "N2", "N3"):
            self.assertEqual(self.web.status_of(node)["doc_count"], 10)

    def test_02_search_merges_global_top_k(self):
        reply = self.web.post("/api/search", {"query": "grpc streaming"})
        self.assertEqual(reply["coordinator_id"], "C3")
        self.assertEqual(reply["healthy_nodes"], 3)
        self.assertTrue(reply["results"])
        scores = [result["score"] for result in reply["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_03_add_goes_to_least_loaded_node_and_replicates_everywhere(self):
        result = self.add("zebra")[0]
        self.assertEqual((result["doc_id"], result["node_id"], result["version"], result["coordinator_id"]),
                         (31, "N1", 1, "C3"))
        wait_for(lambda: all(self.web.status_of(pid)["stats_version"] == 1 for pid in ("C1", "C2", "C3", "N1", "N2", "N3")),
                 10, "statistics version 1 should be on every process")
        for pid in ("C1", "C2", "C3"):
            self.assertEqual(self.web.status_of(pid)["node_counts"]["N1"], 11)
            self.assertEqual(self.web.status_of(pid)["total_docs"], 31)
        found = self.web.post("/api/search", {"query": "zebra"})
        self.assertEqual(found["results"][0]["document_id"], 31)
        self.assertEqual(found["stats_version"], 1)

    def test_04_two_simultaneous_adds_are_concurrent_in_vector_time(self):
        first, second = self.add("giraffe", "okapi")
        self.assertEqual({first["node_id"], second["node_id"]}, {"N2", "N3"})
        self.assertEqual(sorted([first["version"], second["version"]]), [2, 3])
        def indexed_events():       # events are pushed asynchronously, so wait until both have arrived
            found = {event["op"]: event for event in self.events_named("document_indexed")}
            return found if first["op"] in found and second["op"] in found else None

        indexed = wait_for(indexed_events, 10, "document_indexed events for both documents")
        a, b = indexed[first["op"]], indexed[second["op"]]
        self.assertEqual(compare(a["vector"], b["vector"]), "concurrent")
        # ...but both are causally before the moment each document became searchable
        for result in (first, second):          # events are pushed asynchronously, so wait for them to arrive
            searchable = wait_for(lambda: [e for e in self.events_named("document_searchable")
                                           if e["op"] == result["op"]], 10, "document_searchable event")[0]
            self.assertEqual(compare(indexed[result["op"]]["vector"], searchable["vector"]), "before")

    def test_05_every_message_orders_send_before_receive(self):
        events = self.web.all_events()
        sends, receives, per_process = {}, {}, {}
        for event in events:
            if event["kind"] == "send":
                sends[event["msg_id"]] = event
            elif event["kind"] == "receive":
                receives.setdefault(event["msg_id"], []).append(event)
            if event["vector"] is not None:
                per_process.setdefault(event["process"], []).append(event)
        checked = 0
        for msg_id, received in receives.items():
            if msg_id in sends:
                for event in received:
                    self.assertEqual(compare(sends[msg_id]["vector"], event["vector"]), "before", (sends[msg_id], event))
                    checked += 1
        self.assertGreater(checked, 50)
        for process, items in per_process.items():          # a process's own clock only ever grows
            items.sort(key=lambda event: event["seq"])
            for earlier, later in zip(items, items[1:]):
                self.assertEqual(compare(earlier["vector"], later["vector"]), "before", (process, earlier, later))

    def test_06_beacons_are_sent_and_received_with_counters(self):
        leader = self.web.status_of("C3")
        self.assertGreaterEqual(leader["beacons_sent"], 2)
        for pid in ("C1", "C2", "N1", "N2", "N3"):
            self.assertGreaterEqual(self.web.status_of(pid)["beacons_received"], 1, pid)
        self.assertTrue(self.events_named("beacon_sent"))
        self.assertTrue(self.events_named("beacon_received"))

    def test_07_killing_the_leader_triggers_node_report_ping_bully_election(self):
        self.web.post("/api/admin/processes/C3/stop")
        wait_for(lambda: self.leader_is("C2", 2), 40, "C2 should win the election with epoch 2")
        failover = [e for e in self.web.all_events() if e["op"] == "failover-e1"]
        names = {(e["process"][0], e["name"]) for e in failover}
        self.assertIn(("N", "leader_suspected"), names)            # a node noticed first
        self.assertIn(("N", "suspect_report_sent"), names)         # ...and told the coordinators
        self.assertIn(("C", "suspect_report_received"), names)
        self.assertIn(("C", "ping_failed"), names)                 # a coordinator pinged the dead leader
        self.assertIn(("C", "election_started"), names)
        self.assertIn(("C", "became_leader"), names)
        became = [e for e in failover if e["name"] == "became_leader"][0]
        self.assertEqual((became["process"], became["details"]["epoch"]), ("C2", 2))
        wait_for(lambda: all(self.web.status_of(pid)["epoch"] == 2 for pid in ("C1", "C2", "N1", "N2", "N3")),
                 10, "everyone should follow epoch 2")
        self.assertEqual(self.web.post("/api/search", {"query": "zebra"})["coordinator_id"], "C2")

    def test_08_old_epoch_commands_are_rejected_by_nodes(self):
        request = search_pb2.ApplyStatisticsRequest(epoch=1, leader_id="C3")       # the dead leader's epoch
        request.stamp.sender = "C3"
        reply = quiet_call(f"127.0.0.1:{NODE_PORT_BASE + 1}", search_pb2_grpc.NodeServiceStub, "ApplyStatistics", request)
        self.assertTrue(reply.stale)
        self.assertEqual(reply.epoch, 2)

    def test_09_new_leader_accepts_writes_and_keeps_replicating(self):
        result = self.add("lemur")[0]
        self.assertEqual((result["coordinator_id"], result["version"], result["epoch"]), ("C2", 4, 2))
        wait_for(lambda: self.web.status_of("C1")["stats_version"] == 4, 10, "standby C1 should replicate version 4")

    def test_10_revived_c3_catches_up_then_takes_over_with_a_higher_epoch(self):
        self.web.post("/api/admin/processes/C3/start")
        wait_for(lambda: self.leader_is("C3", 3), 30, "C3 should bully its way back with epoch 3")
        self.assertEqual(self.web.status_of("C3")["stats_version"], 4)       # replayed log + catch-up from C2
        self.assertEqual(self.web.status_of("C2")["role"], "STANDBY")
        self.assertTrue(self.events_named("catch_up_done", version=4) or self.web.status_of("C3")["stats_version"] == 4)
        self.assertEqual(self.add("tapir")[0]["version"], 5)

    def test_11_dead_node_is_skipped_and_resynced_when_it_returns(self):
        self.web.post("/api/admin/processes/N3/stop")
        wait_for(lambda: self.web.status_of("N3")["state"] == "stopped" and
                 self.web.status_of("C3")["node_alive"].get("N3") is False, 15, "leader should see N3 down")
        down_search = self.web.post("/api/search", {"query": "lemur"})
        self.assertEqual(down_search["healthy_nodes"], 2)
        added = self.add("pangolin")[0]
        self.assertNotEqual(added["node_id"], "N3")
        self.assertEqual(added["version"], 6)
        self.web.post("/api/admin/processes/N3/start")
        wait_for(lambda: self.web.status_of("N3")["state"] == "running" and
                 self.web.status_of("N3")["stats_version"] == 6, 30, "N3 should be resynced to version 6 by a beacon")
        reply = self.web.post("/api/search", {"query": "pangolin"})
        self.assertEqual([s["status"] for s in reply["node_status"]], ["up", "up", "up"])
        self.assertEqual(reply["results"][0]["title"], "Pangolin field guide")


if __name__ == "__main__":
    unittest.main()
