import threading
import unittest

from distributed_systems.vector_clock import VectorClock, compare


class VectorClockTests(unittest.TestCase):
    def test_local_events_and_sends_increment_only_own_entry(self):
        clock = VectorClock("C1")
        self.assertEqual(clock.tick(), {"C1": 1})
        self.assertEqual(clock.tick(), {"C1": 2})

    def test_receive_merges_elementwise_max_then_increments_own_entry(self):
        clock = VectorClock("N2")
        clock.tick()                                   # N2:1
        merged = clock.receive({"C3": 5, "N2": 0, "N1": 2})
        self.assertEqual(merged, {"N2": 2, "C3": 5, "N1": 2})

    def test_message_exchange_orders_send_before_receive(self):
        coordinator, node = VectorClock("C3"), VectorClock("N1")
        sent = coordinator.tick()
        received = node.receive(sent)
        replied = node.tick()
        coordinator_got = coordinator.receive(replied)
        self.assertEqual(compare(sent, received), "before")
        self.assertEqual(compare(received, replied), "before")
        self.assertEqual(compare(replied, coordinator_got), "before")
        self.assertEqual(compare(sent, coordinator_got), "before")

    def test_independent_events_are_concurrent(self):
        a, b = VectorClock("N1"), VectorClock("N2")
        self.assertEqual(compare(a.tick(), b.tick()), "concurrent")

    def test_compare_relations(self):
        self.assertEqual(compare({"A": 1}, {"A": 1}), "equal")
        self.assertEqual(compare({"A": 2, "B": 1}, {"A": 1}), "after")
        self.assertEqual(compare({}, {"A": 1}), "before")

    def test_thread_safety(self):
        clock = VectorClock("C1")
        workers = [threading.Thread(target=lambda: [clock.tick() for _ in range(500)]) for _ in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(clock.snapshot(), {"C1": 4000})


if __name__ == "__main__":
    unittest.main()
