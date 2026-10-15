"""Thread-safe vector clock plus the comparison used to order or relate two events."""

import threading
from collections.abc import Mapping


class VectorClock:
    """One counter per process. Unknown processes count as 0, so membership can change freely.

    Rules (each call is one event):
      local event / send : V[self] += 1
      receive            : V = element-wise max(V, V_message); then V[self] += 1
    """

    def __init__(self, process_id: str) -> None:
        self.process_id = process_id
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def tick(self) -> dict[str, int]:
        """Record a local event, or the moment just before a message is sent."""
        with self._lock:
            self._counters[self.process_id] = self._counters.get(self.process_id, 0) + 1
            return dict(self._counters)

    def receive(self, remote: Mapping[str, int]) -> dict[str, int]:
        """Merge a received vector, then count the receive itself as an event."""
        with self._lock:
            for process, value in remote.items():
                if value > self._counters.get(process, 0):
                    self._counters[process] = int(value)
            self._counters[self.process_id] = self._counters.get(self.process_id, 0) + 1
            return dict(self._counters)


def compare(a: Mapping[str, int], b: Mapping[str, int]) -> str:
    """Relate two vector timestamps: 'before' (a -> b), 'after' (b -> a), 'equal' or 'concurrent'."""
    keys = set(a) | set(b)
    a_le_b = all(a.get(key, 0) <= b.get(key, 0) for key in keys)
    b_le_a = all(b.get(key, 0) <= a.get(key, 0) for key in keys)
    if a_le_b and b_le_a:
        return "equal"
    if a_le_b:
        return "before"
    if b_le_a:
        return "after"
    return "concurrent"
