"""Coordinator process: beacons, Bully election with epochs, replicated statistics and the write path.

Three of these run (C1, C2, C3). The one with the highest live ID is the leader; the others are
standbys that hold a replica of the global statistics, so any of them can take over. Only the
leader accepts documents. Any coordinator can answer searches.

Every message between coordinators and nodes carries the sender's full vector clock.
"""

import argparse
import threading
import time
import uuid
from collections import Counter
from concurrent import futures
from pathlib import Path

import grpc

from distributed_systems.cluster_config import ClusterConfig, NodeEntry, load_cluster_config
from distributed_systems.global_stats import APPLIED, GAP, GlobalStats, delta_from_proto, delta_to_proto
from distributed_systems.rpc import call, fan_out, quiet_call
from distributed_systems.tracing import Tracer
from proto import search_pb2, search_pb2_grpc

NodeStub = search_pb2_grpc.NodeServiceStub
CoordinatorStub = search_pb2_grpc.CoordinatorServiceStub


def rank_of(process_id: str) -> int:
    return int(process_id[1:]) if process_id[:1] == "C" and process_id[1:].isdigit() else 0


def category_for(op: str) -> str:
    return "sync" if op.startswith("sync") else "add"


class CoordinatorService(search_pb2_grpc.CoordinatorServiceServicer):
    def __init__(self, coordinator_id: str, config: ClusterConfig) -> None:
        self.id = coordinator_id
        self.rank = rank_of(coordinator_id)
        self.cfg = config
        self.peers = config.peers_of(coordinator_id)
        self.tracer = Tracer(coordinator_id, config.event_sink_url)
        self.stats = GlobalStats(config.data_directory, coordinator_id)

        # Cluster role (guarded by state_lock)
        self.state_lock = threading.RLock()
        self.role = "STANDBY"          # STANDBY | CANDIDATE | LEADER
        self.epoch = 0
        self.leader_id = ""
        self.ready = False             # a leader is ready for writes once it has announced itself
        self.last_beat = time.time()
        self.beacons_sent = 0
        self.beacons_received = 0
        self.committed_version = self.stats.version   # statistics version that every node should be serving
        self.electing = False
        self.verifying = False
        self.verify_until = 0.0
        self.announce_event = threading.Event()
        self.booted = threading.Event()
        self.wake_beacon = threading.Event()

        # Write path (leader only)
        self.id_lock = threading.Lock()
        self.stats_lock = threading.Lock()
        self.next_doc_id = self.stats.next_doc_id
        self.inflight: Counter = Counter()
        self.node_alive: dict[str, bool] = {}
        self.peer_versions: dict[str, int] = {}

    def start(self) -> None:
        self.tracer.local("coordinator_started", "election", stats_version=self.stats.version)
        for target in (self._boot, self._beacon_loop, self._monitor_loop):
            threading.Thread(target=target, name=f"{self.id}-{target.__name__}", daemon=True).start()

    # ---- helpers --------------------------------------------------------------------------------
    def _call(self, target, method, request, name, category, op="", **details):
        stub = NodeStub if isinstance(target, NodeEntry) else CoordinatorStub
        return call(self.tracer, target.address, stub, method, request, name=name, peer=target.id,
                    category=category, op=op, timeout=self.cfg.rpc_timeout, **details)

    def _should_yield(self, epoch: int, leader_id: str) -> bool:
        with self.state_lock:
            return epoch > self.epoch or (epoch == self.epoch and rank_of(leader_id) > self.rank)

    def _step_down(self, leader_id: str, epoch: int, op: str = "") -> None:
        with self.state_lock:
            was_leader = self.role == "LEADER"
            self.role, self.ready = "STANDBY", False
            self.epoch = max(self.epoch, epoch)
            self.leader_id = leader_id
            self.last_beat = time.time()
        if was_leader:
            self.tracer.local("stepped_down", "election", op=op, new_leader=leader_id, epoch=epoch)

    # ---- boot -----------------------------------------------------------------------------------
    def _boot(self) -> None:
        """Join an existing higher-ranked leader, otherwise start an election."""
        time.sleep(self.cfg.boot_grace)
        found = fan_out(self.peers, lambda peer: quiet_call(peer.address, CoordinatorStub, "GetStatus",
                                                            search_pb2.StatusRequest()))
        leaders = [status for _, status in found if not isinstance(status, Exception)
                   and status.role == "LEADER" and status.ready]
        if leaders:
            best = max(leaders, key=lambda status: status.epoch)
            if rank_of(best.process_id) > self.rank:
                with self.state_lock:
                    self.epoch, self.leader_id, self.last_beat = best.epoch, best.process_id, time.time()
                    self.committed_version = best.committed_version
                self.tracer.local("joined_as_standby", "election", leader=best.process_id, epoch=best.epoch)
                self.booted.set()
                return
            with self.state_lock:      # a lower-ranked leader exists: learn its epoch, then bully it
                self.epoch = max(self.epoch, best.epoch)
        self.start_election("boot: no higher-ranked leader found")
        self.booted.set()

    # ---- failure detection -------------------------------------------------------------------------
    def _monitor_loop(self) -> None:
        """Standbys also watch the beacon, a little later than nodes so node reports usually come first."""
        while True:
            time.sleep(1.0)
            if not self.booted.is_set():
                continue
            now = time.time()
            with self.state_lock:
                if self.role == "LEADER" or self.electing or self.verifying:
                    continue
                silence = now - self.last_beat
                due = silence > self.cfg.beat_timeout + self.cfg.heartbeat_interval and now >= self.verify_until
                if due:
                    self.verifying, self.verify_until, epoch = True, now + self.cfg.beat_timeout, self.epoch
            if due:
                threading.Thread(target=self._verify_leader_and_elect, daemon=True,
                                 args=(f"failover-e{epoch}", f"no beacon for {silence:.0f}s")).start()

    def _verify_leader_and_elect(self, op: str, reason: str) -> None:
        """Ping the suspected leader; only if it does not answer as leader, start an election."""
        try:
            with self.state_lock:
                leader, epoch = self.leader_id, self.epoch
            self.tracer.local("verifying_leader", "election", op=op, leader=leader or "unknown", reason=reason)
            alive = False
            if leader and leader != self.id:
                try:
                    reply = self._call(self.cfg.coordinator(leader), "Ping",
                                       search_pb2.PingRequest(from_id=self.id), "ping", "election", op)
                    alive = reply.role == "LEADER" and reply.epoch >= epoch
                except grpc.RpcError:
                    pass
            if alive:
                with self.state_lock:
                    self.last_beat = time.time()
                self.tracer.local("leader_alive_false_alarm", "election", op=op, leader=leader)
                return
            self.tracer.local("leader_confirmed_down", "election", op=op, leader=leader or "unknown")
            self.start_election(reason, op)
        finally:
            with self.state_lock:
                self.verifying = False

    # ---- election (Bully) ----------------------------------------------------------------------------
    def start_election(self, reason: str, op: str = "") -> None:
        op = op or f"election-{self.id}-{uuid.uuid4().hex[:4]}"
        with self.state_lock:
            if self.electing or self.role == "LEADER":
                return
            self.electing, self.role = True, "CANDIDATE"
            self.announce_event.clear()
        try:
            self.tracer.local("election_started", "election", op=op, reason=reason, epoch=self.epoch)
            for _ in range(3):
                higher = [peer for peer in self.peers if peer.rank > self.rank]
                replies = fan_out(higher, lambda peer: self._call(
                    peer, "Election", search_pb2.ElectionRequest(from_id=self.id, epoch=self.epoch),
                    "election", "election", op))
                answered = [peer.id for peer, reply in replies if not isinstance(reply, Exception) and reply.ok]
                if not answered:
                    self._become_leader(op)
                    return
                self.tracer.local("waiting_for_winner", "election", op=op, higher_alive=answered)
                if self.announce_event.wait(self.cfg.election_wait):
                    return
                self.tracer.local("winner_never_announced", "election", op=op)
        finally:
            with self.state_lock:
                self.electing = False
                if self.role == "CANDIDATE":
                    self.role = "STANDBY"

    def _become_leader(self, op: str) -> None:
        self.tracer.local("won_election", "election", op=op, reason="no higher coordinator answered")
        self._catch_up_from_peers(op)
        new_epoch = 0
        for _ in range(4):
            with self.state_lock:
                new_epoch = self.epoch + 1
            targets = list(self.peers) + list(self.cfg.nodes)
            replies = fan_out(targets, lambda target: self._call(
                target, "Announce", search_pb2.AnnounceRequest(
                    leader_id=self.id, epoch=new_epoch, stats_version=self.stats.version),
                "announce", "election", op))
            rejected = [reply.epoch for _, reply in replies
                        if not isinstance(reply, Exception) and not reply.accepted]
            if not rejected:
                break
            with self.state_lock:
                self.epoch = max(self.epoch, *rejected)
            self.tracer.local("announce_rejected_retrying", "election", op=op, highest_epoch=self.epoch)
        with self.state_lock:
            self.role, self.epoch, self.leader_id, self.ready = "LEADER", new_epoch, self.id, True
            self.last_beat = time.time()
            self.committed_version = self.stats.version
        self.next_doc_id = max(self.next_doc_id, self.stats.next_doc_id)
        self.tracer.local("became_leader", "election", op=op, epoch=new_epoch, stats_version=self.stats.version)
        self.wake_beacon.set()

    def _catch_up_from_peers(self, op: str) -> None:
        """Before leading, fetch any statistics deltas this coordinator missed while it was down."""
        found = fan_out(self.peers, lambda peer: quiet_call(peer.address, CoordinatorStub, "GetStatus",
                                                            search_pb2.StatusRequest()))
        ahead = [(peer, status) for peer, status in found
                 if not isinstance(status, Exception) and status.stats_version > self.stats.version]
        if not ahead:
            return
        peer, status = max(ahead, key=lambda item: item[1].stats_version)
        self.tracer.local("catch_up_started", "sync", op=op, source=peer.id,
                          my_version=self.stats.version, their_version=status.stats_version)
        try:
            reply = self._call(peer, "GetDeltasSince", search_pb2.DeltasRequest(
                requester_id=self.id, since_version=self.stats.version), "catch_up", "sync", op)
        except grpc.RpcError:
            return
        for message in sorted(reply.deltas, key=lambda item: item.version):
            self.stats.apply(delta_from_proto(message))
        self.tracer.local("catch_up_done", "sync", op=op, version=self.stats.version)

    # ---- election RPCs ---------------------------------------------------------------------------------
    def Election(self, request, context):
        tracer = self.tracer
        op = request.stamp.op
        tracer.incoming(request.stamp, "election_received", "election", challenger=request.from_id)
        with self.state_lock:
            leading = self.role == "LEADER"
            reply = search_pb2.ElectionReply(process_id=self.id, ok=True, epoch=self.epoch, leader_id=self.leader_id)
        reply.stamp.CopyFrom(tracer.reply(request.stamp, "election_ok_sent", "election"))
        challenger = self.cfg.coordinator(request.from_id)
        if leading:
            threading.Thread(target=self._announce_to, args=(challenger, op), daemon=True).start()
        else:
            threading.Thread(target=self.start_election, daemon=True,
                             args=(f"challenged by {request.from_id}", op)).start()
        return reply

    def _announce_to(self, target, op: str) -> None:
        try:
            with self.state_lock:
                epoch = self.epoch
            self._call(target, "Announce", search_pb2.AnnounceRequest(
                leader_id=self.id, epoch=epoch, stats_version=self.stats.version), "announce", "election", op)
        except grpc.RpcError:
            pass

    def Announce(self, request, context):
        tracer = self.tracer
        tracer.incoming(request.stamp, "announce_received", "election", leader=request.leader_id, epoch=request.epoch)
        with self.state_lock:
            conflict = self.role == "LEADER" and request.leader_id != self.id and request.epoch == self.epoch
            accepted = not conflict and (request.epoch > self.epoch or (
                request.epoch == self.epoch and self.leader_id in ("", request.leader_id)))
            was_leader = self.role == "LEADER"
            if accepted:
                self.epoch, self.leader_id, self.role, self.ready = request.epoch, request.leader_id, "STANDBY", False
                self.last_beat = time.time()
                self.committed_version = request.stats_version
            reply = search_pb2.AnnounceReply(process_id=self.id, accepted=accepted, epoch=self.epoch,
                                             leader_id=self.leader_id)
        if accepted:
            self.announce_event.set()
            name = "stepped_down" if was_leader and request.leader_id != self.id else "leader_accepted"
            tracer.local(name, "election", op=request.stamp.op, leader=request.leader_id, epoch=request.epoch)
        reply.stamp.CopyFrom(tracer.reply(request.stamp, "announce_reply_sent", "election"))
        return reply

    def Ping(self, request, context):
        self.tracer.incoming(request.stamp, "ping_received", "election")
        with self.state_lock:
            reply = search_pb2.PingReply(process_id=self.id, role=self.role, epoch=self.epoch)
        reply.stamp.CopyFrom(self.tracer.reply(request.stamp, "ping_reply_sent", "election"))
        return reply

    def ReportSuspect(self, request, context):
        tracer = self.tracer
        tracer.incoming(request.stamp, "suspect_report_received", "election", reporter=request.reporter_id,
                        silent_for=round(request.silence_seconds, 1))
        with self.state_lock:
            if self.role == "LEADER":
                action = "ignored_i_am_leader"
            elif request.epoch < self.epoch or (self.leader_id and request.leader_id
                                                and request.leader_id != self.leader_id):
                action = "ignored_outdated"
            elif self.electing or self.verifying:
                action = "already_handling"
            else:
                self.verifying, action = True, "verifying"
        reply = search_pb2.SuspectReply(process_id=self.id, action=action)
        reply.stamp.CopyFrom(tracer.reply(request.stamp, "suspect_reply_sent", "election", action=action))
        if action == "verifying":
            threading.Thread(target=self._verify_leader_and_elect, daemon=True,
                             args=(request.stamp.op, f"reported by {request.reporter_id}")).start()
        return reply

    # ---- beacon -------------------------------------------------------------------------------------------
    def _beacon_loop(self) -> None:
        while True:
            self.wake_beacon.wait(self.cfg.heartbeat_interval)
            self.wake_beacon.clear()
            with self.state_lock:
                leading = self.role == "LEADER" and self.ready
                if leading:
                    self.beacons_sent += 1
                    beat, epoch, committed = self.beacons_sent, self.epoch, self.committed_version
            if leading:
                fan_out(list(self.peers) + list(self.cfg.nodes), lambda target: self._beat(target, beat, epoch, committed))

    def _beat(self, target, beat: int, epoch: int, committed: int) -> None:
        is_node = isinstance(target, NodeEntry)
        request = search_pb2.HeartbeatRequest(leader_id=self.id, epoch=epoch, stats_version=committed, beat=beat)
        try:
            reply = self._call(target, "Heartbeat", request, "beacon", "beacon", beat=beat)
        except grpc.RpcError:
            if is_node:
                self.node_alive[target.id] = False
            return
        if reply.stale:
            if self._should_yield(reply.epoch, reply.leader_id):
                self._step_down(reply.leader_id, reply.epoch)
            return
        if is_node:
            self.node_alive[target.id] = True
        self.peer_versions[target.id] = reply.stats_version
        if reply.stats_version < self.stats.version:
            self._push_deltas(target, f"sync-{target.id}")

    def Heartbeat(self, request, context):
        tracer = self.tracer
        tracer.incoming(request.stamp, "beacon_received", "beacon", beat=request.beat, leader=request.leader_id)
        stale, stepped_down = False, False
        with self.state_lock:
            if request.epoch < self.epoch or (request.epoch == self.epoch and self.role == "LEADER"
                                              and request.leader_id != self.id
                                              and rank_of(request.leader_id) < self.rank):
                stale = True
            else:
                stepped_down = self.role == "LEADER" and request.leader_id != self.id
                self.epoch, self.leader_id = request.epoch, request.leader_id
                if self.role != "LEADER" or stepped_down:
                    self.role, self.ready = "STANDBY", False
                self.last_beat = time.time()
                self.beacons_received += 1
                self.committed_version = request.stats_version
                self.verify_until = 0.0
                self.announce_event.set()   # a candidate that hears a live leader stops campaigning
            reply = search_pb2.HeartbeatReply(process_id=self.id, ok=not stale, stale=stale, epoch=self.epoch,
                                              leader_id=self.leader_id, stats_version=self.stats.version)
        if stepped_down:
            tracer.local("stepped_down", "election", new_leader=request.leader_id, epoch=request.epoch)
        reply.stamp.CopyFrom(tracer.reply(request.stamp, "beacon_reply_sent", "beacon"))
        return reply

    # ---- statistics replication -------------------------------------------------------------------------------
    def _push_deltas(self, target, op: str) -> bool:
        """Send `target` every delta it is missing; resend from its own version if it reports a gap."""
        is_node = isinstance(target, NodeEntry)
        method, name = ("ApplyStatistics", "apply_statistics") if is_node else ("ReplicateDelta", "replicate_delta")
        known = self.peer_versions.get(target.id, self.stats.version - 1)
        for _ in range(3):
            deltas = self.stats.deltas_since(known)
            if not deltas:
                return True
            with self.state_lock:
                request = search_pb2.ApplyStatisticsRequest(epoch=self.epoch, leader_id=self.id)
            for delta in deltas:
                delta_to_proto(delta, request.deltas.add())
            try:
                reply = self._call(target, method, request, name, category_for(op), op)
            except grpc.RpcError:
                if is_node:
                    self.node_alive[target.id] = False
                return False
            if reply.stale:
                if self._should_yield(reply.epoch, ""):
                    self._step_down("", reply.epoch, op)
                return False
            if reply.behind:
                known = reply.version
                continue
            self.peer_versions[target.id] = reply.version
            return reply.ok
        return False

    def ReplicateDelta(self, request, context):
        tracer = self.tracer
        op = request.stamp.op
        tracer.incoming(request.stamp, "replicate_delta_received", category_for(op),
                        versions=[delta.version for delta in request.deltas])
        reply = search_pb2.ApplyStatisticsReply(process_id=self.id)
        with self.state_lock:
            if request.epoch < self.epoch:
                reply.stale = True
            else:
                if self.role == "LEADER" and request.leader_id != self.id:
                    self.role, self.ready = "STANDBY", False
                self.epoch, self.leader_id = request.epoch, request.leader_id or self.leader_id
        if not reply.stale:
            applied, behind = 0, False
            for message in sorted(request.deltas, key=lambda item: item.version):
                status = self.stats.apply(delta_from_proto(message))
                if status == APPLIED:
                    applied += 1
                elif status == GAP:
                    behind = True
                    break
            reply.ok, reply.behind = not behind, behind
            if applied:
                tracer.local("statistics_replicated", category_for(op), op=op, version=self.stats.version,
                             total_docs=self.stats.n)
        reply.epoch, reply.version = self.epoch, self.stats.version
        reply.stamp.CopyFrom(tracer.reply(request.stamp, "replicate_delta_reply_sent", category_for(op)))
        return reply

    def GetDeltasSince(self, request, context):
        self.tracer.incoming(request.stamp, "catch_up_requested", "sync", requester=request.requester_id,
                             since=request.since_version)
        reply = search_pb2.DeltasReply(process_id=self.id, version=self.stats.version)
        for delta in self.stats.deltas_since(request.since_version):
            delta_to_proto(delta, reply.deltas.add())
        reply.stamp.CopyFrom(self.tracer.reply(request.stamp, "catch_up_reply_sent", "sync"))
        return reply

    # ---- write path: SubmitDocument ------------------------------------------------------------------------------------
    def _choose_node(self, exclude) -> NodeEntry:
        """Least-loaded node (stored documents plus in-flight adds); ties go to the lowest ID."""
        candidates = [node for node in self.cfg.nodes if node.id not in exclude]
        alive = [node for node in candidates if self.node_alive.get(node.id) is not False]
        return min(alive or candidates, key=lambda node: (
            self.stats.node_counts.get(node.id, 0) + self.inflight[node.id], node.id))

    def SubmitDocument(self, request, context):
        tracer = self.tracer
        op = request.operation_id or f"doc-{uuid.uuid4().hex[:8]}"
        with self.state_lock:
            leading, hint, epoch = self.role == "LEADER" and self.ready, self.leader_id, self.epoch
        if not leading:
            return search_pb2.SubmitReply(ok=False, error="NOT_LEADER", leader_hint=hint, coordinator_id=self.id,
                                          epoch=epoch, operation_id=op)
        document = request.document
        tracer.local("document_received", "add", op=op, title=document.title, url=document.url,
                     content_length=len(document.content), preview=document.content[:200])
        with self.id_lock:
            self.next_doc_id = max(self.next_doc_id, self.stats.next_doc_id)
            doc_id, self.next_doc_id = self.next_doc_id, self.next_doc_id + 1
        tracer.local("doc_id_assigned", "add", op=op, doc_id=doc_id)

        tried: list[str] = []
        node, added = None, None
        while True:
            with self.id_lock:
                node = self._choose_node(tried)
                self.inflight[node.id] += 1
                load = {entry.id: self.stats.node_counts.get(entry.id, 0) + self.inflight[entry.id]
                        for entry in self.cfg.nodes}
            tracer.local("node_selected", "add", op=op, node=node.id, load=load)
            message = search_pb2.AddDocumentRequest(epoch=epoch, leader_id=self.id)
            message.document.CopyFrom(search_pb2.Document(
                document_id=doc_id, title=document.title, url=document.url, source=document.source or "admin",
                content=document.content, content_length=len(document.content)))
            try:
                added = self._call(node, "AddDocument", message, "add_document", "add", op)
            except grpc.RpcError:
                added = None
            if added is not None and added.ok:
                break
            with self.id_lock:
                self.inflight[node.id] -= 1
            if added is not None and added.stale:
                self._step_down("", added.epoch, op)
                return search_pb2.SubmitReply(ok=False, error="STALE_EPOCH", coordinator_id=self.id,
                                              epoch=added.epoch, operation_id=op)
            self.node_alive[node.id] = False
            tried.append(node.id)
            if len(tried) == len(self.cfg.nodes):
                return search_pb2.SubmitReply(ok=False, error="NO_NODE_AVAILABLE", coordinator_id=self.id,
                                              epoch=epoch, operation_id=op)
        try:
            with self.stats_lock:
                delta = {"version": self.stats.version + 1, "doc_id": doc_id, "node_id": node.id,
                         "terms": list(added.terms), "title": document.title, "url": document.url}
                self.stats.apply(delta)
                tracer.local("statistics_updated", "add", op=op, version=delta["version"], total_docs=self.stats.n,
                             new_terms=len(delta["terms"]))
                standbys = fan_out(self.peers, lambda peer: self._push_deltas(peer, op))
                tracer.local("replicated_to_standbys", "add", op=op, version=delta["version"],
                             acknowledged=[peer.id for peer, ok in standbys if ok is True])
                nodes = fan_out(self.cfg.nodes, lambda entry: self._push_deltas(entry, op))
                self.committed_version = delta["version"]
                tracer.local("statistics_applied_on_nodes", "add", op=op, version=delta["version"],
                             acknowledged=[entry.id for entry, ok in nodes if ok is True])
            tracer.local("document_searchable", "add", op=op, doc_id=doc_id, node=node.id, version=delta["version"])
        finally:
            with self.id_lock:
                self.inflight[node.id] -= 1
        return search_pb2.SubmitReply(ok=True, coordinator_id=self.id, epoch=epoch, doc_id=doc_id, node_id=node.id,
                                      version=delta["version"], operation_id=op)

    # ---- read path: Search -------------------------------------------------------------------------------------------------
    def Search(self, request, context):
        tracer = self.tracer
        started = time.perf_counter()
        op = f"search-{uuid.uuid4().hex[:6]}"
        with self.state_lock:
            committed, epoch, role = self.committed_version, self.epoch, self.role
        top_k = request.top_k or self.cfg.final_top_k
        tracer.local("search_started", "search", op=op, query=request.query)

        def ask(node):
            began = time.perf_counter()
            message = search_pb2.NodeSearchRequest(query=request.query, top_k=max(self.cfg.local_top_k, top_k),
                                                   epoch=epoch)
            return self._call(node, "Search", message, "search", "search", op), (time.perf_counter() - began) * 1000

        statuses, candidates = [], []
        for node, outcome in fan_out(self.cfg.nodes, ask):
            if isinstance(outcome, Exception):
                code = outcome.code().name if isinstance(outcome, grpc.RpcError) else type(outcome).__name__
                statuses.append(search_pb2.NodeStatus(node_id=node.id, address=node.address, status="unavailable",
                                                      error=code))
                continue
            reply, latency = outcome
            accepted = reply.stats_version == committed
            statuses.append(search_pb2.NodeStatus(
                node_id=node.id, address=node.address, status="up" if accepted else "stale_version",
                latency_ms=round(latency, 2), candidate_count=len(reply.results), stats_version=reply.stats_version,
                accepted=accepted))
            if accepted:
                candidates.extend(reply.results)
        candidates.sort(key=lambda result: (-result.score, result.document_id))
        final = candidates[:top_k]
        tracer.local("results_merged", "search", op=op, candidates=len(candidates), returned=len(final),
                     stats_version=committed)
        statuses.sort(key=lambda status: status.node_id)
        return search_pb2.SearchReply(
            results=final, node_status=statuses, healthy_nodes=sum(s.status != "unavailable" for s in statuses),
            total_nodes=len(self.cfg.nodes), candidate_count=len(candidates),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2), coordinator_id=self.id, epoch=epoch,
            stats_version=committed, role=role, operation_id=op)

    # ---- observer ---------------------------------------------------------------------------------------------------------------
    def GetStatus(self, request, context):
        with self.state_lock:
            reply = search_pb2.StatusReply(
                process_id=self.id, kind="coordinator", role=self.role, leader_id=self.leader_id, epoch=self.epoch,
                stats_version=self.stats.version, committed_version=self.committed_version, ready=self.ready,
                last_beat_age=0.0 if self.role == "LEADER" else round(time.time() - self.last_beat, 2),
                beat_timeout=self.cfg.beat_timeout, beacons_sent=self.beacons_sent,
                beacons_received=self.beacons_received, total_docs=self.stats.n,
                next_doc_id=max(self.next_doc_id, self.stats.next_doc_id))
        reply.node_counts.update(self.stats.node_counts)
        reply.clock.update(self.tracer.clock.snapshot())
        if self.role == "LEADER":
            reply.node_alive.update({node.id: self.node_alive.get(node.id, True) for node in self.cfg.nodes})
        return reply


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one coordinator.")
    parser.add_argument("--id", required=True, help="Coordinator ID such as C1.")
    parser.add_argument("--config", type=Path, required=True)
    arguments = parser.parse_args()
    config = load_cluster_config(arguments.config)
    service = CoordinatorService(arguments.id, config)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=32))
    search_pb2_grpc.add_CoordinatorServiceServicer_to_server(service, server)
    port = config.coordinator(arguments.id).address.rsplit(":", 1)[1]
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    service.start()
    print(f"{arguments.id} (rank {service.rank}) listening on port {port}, statistics v{service.stats.version}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    main()
