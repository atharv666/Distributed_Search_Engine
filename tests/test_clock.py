import unittest
from concurrent.futures import ThreadPoolExecutor

from distributed_systems.clock import LamportClock


class LamportClockTests(unittest.TestCase):
    def test_initial_value_and_local_ticks(self):
        clock = LamportClock()
        self.assertEqual(clock.value, 0)
        self.assertEqual(clock.tick(), 1)
        self.assertEqual(clock.tick(), 2)
        self.assertEqual(clock.value, 2)

    def test_receive_advances_past_larger_remote_timestamp(self):
        clock = LamportClock()
        clock.tick()
        self.assertEqual(clock.receive(50), 51)
        self.assertEqual(clock.tick(), 52)

    def test_receive_advances_when_local_timestamp_is_larger(self):
        clock = LamportClock()
        clock.receive(50)
        self.assertEqual(clock.receive(3), 52)
        self.assertEqual(clock.receive(52), 53)

    def test_concurrent_updates_are_unique_and_do_not_lose_events(self):
        clock = LamportClock()

        def update(index):
            return clock.tick() if index % 2 else clock.receive(0)

        with ThreadPoolExecutor(max_workers=16) as executor:
            timestamps = list(executor.map(update, range(2000)))
        self.assertEqual(sorted(timestamps), list(range(1, 2001)))
        self.assertEqual(clock.value, 2000)

    def test_invalid_timestamp_does_not_mutate_clock(self):
        clock = LamportClock()
        for timestamp in (-1, 1.5, "2", True, None):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                clock.receive(timestamp)
        self.assertEqual(clock.value, 0)


if __name__ == "__main__":
    unittest.main()
