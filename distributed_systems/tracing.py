"""Vector-clock tracing: every clocked event is timestamped and reported to the web server.

A process owns one Tracer. Each send, receive or local event goes through it, so the vector
clock and the event record can never disagree. Events are pushed in the background to the
web server's observer endpoint; the observer never takes part in the clocks.
"""

import json
import queue
import threading
import time
import uuid
from urllib.request import Request, urlopen

from proto import search_pb2

from .vector_clock import VectorClock


class Tracer:
    def __init__(self, process_id: str, sink_url: str = "") -> None:
        self.process_id = process_id
        self.clock = VectorClock(process_id)
        self._lock = threading.Lock()
        self._seq = 0
        self._queue: queue.Queue = queue.Queue(maxsize=50000)
        self.sink_url = sink_url
        if sink_url:
            threading.Thread(target=self._pump, name=f"{process_id}-events", daemon=True).start()

    # -- recording -------------------------------------------------------------------------
    def local(self, name: str, category: str, op: str = "", peer: str = "", **details) -> dict[str, int]:
        with self._lock:
            vector = self.clock.tick()
            self._record("local", name, category, op, peer, "", vector, details)
            return vector

    def outgoing(self, name: str, peer: str, category: str, op: str = "", reply_to: str = "", **details):
        """Record a send event and return the Stamp to place in the outgoing message."""
        msg_id = f"{reply_to}:reply" if reply_to else uuid.uuid4().hex[:10]
        with self._lock:
            vector = self.clock.tick()
            self._record("send", name, category, op, peer, msg_id, vector, details)
        stamp = search_pb2.Stamp(msg_id=msg_id, op=op, sender=self.process_id)
        stamp.clock.update(vector)
        return stamp

    def incoming(self, stamp, name: str, category: str, **details) -> dict[str, int]:
        """Merge the sender's vector (max, then +1) and record the receive event."""
        with self._lock:
            vector = self.clock.receive(dict(stamp.clock))
            self._record("receive", name, category, stamp.op, stamp.sender, stamp.msg_id, vector, details)
            return vector

    def reply(self, request_stamp, name: str, category: str, **details):
        """Send-event for the reply to a request whose stamp we received."""
        return self.outgoing(name, request_stamp.sender, category, op=request_stamp.op,
                             reply_to=request_stamp.msg_id, **details)

    def _record(self, kind, name, category, op, peer, msg_id, vector, details) -> None:
        self._seq += 1
        event = {"process": self.process_id, "seq": self._seq, "kind": kind, "name": name,
                 "category": category, "op": op, "peer": peer, "msg_id": msg_id,
                 "vector": vector, "time": time.time(), "details": details}
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass

    # -- delivery to the observer ----------------------------------------------------------
    def _pump(self) -> None:
        while True:
            batch = [self._queue.get()]
            deadline = time.monotonic() + 0.25
            while len(batch) < 300 and time.monotonic() < deadline:
                try:
                    batch.append(self._queue.get(timeout=0.05))
                except queue.Empty:
                    pass
            try:
                request = Request(self.sink_url, data=json.dumps(batch).encode("utf-8"),
                                  headers={"Content-Type": "application/json"}, method="POST")
                urlopen(request, timeout=2).read()
            except Exception:
                time.sleep(0.5)  # the observer may be restarting; losing a batch is acceptable
