"""Process-local Lamport logical clocks."""

from threading import Lock


class LamportClock:
    """Serialize local and receive events across a process's worker threads."""

    def __init__(self) -> None:
        self._value = 0
        self._lock = Lock()

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

    def tick(self) -> int:
        """Advance for a local event or immediately before sending a message."""
        with self._lock:
            self._value += 1
            return self._value

    def receive(self, timestamp: int) -> int:
        """Advance on message receipt according to max(local, remote) + 1."""
        if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0:
            raise ValueError("A logical timestamp must be a nonnegative integer.")
        with self._lock:
            self._value = max(self._value, timestamp) + 1
            return self._value
