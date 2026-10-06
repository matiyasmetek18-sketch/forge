import unittest

from events import Dispatcher


class DispatcherTests(unittest.TestCase):
    def test_listener_added_during_emit_waits_until_next_event(self):
        bus = Dispatcher()
        received = []

        def first(value):
            received.append(("first", value))
            if value == 1:
                bus.subscribe(lambda later: received.append(("late", later)))

        bus.subscribe(first)
        bus.emit(1)
        self.assertEqual(received, [("first", 1)])
        bus.emit(2)
        self.assertEqual(received, [("first", 1), ("first", 2), ("late", 2)])

    def test_unsubscribe_during_emit_does_not_skip_current_listener(self):
        bus = Dispatcher()
        received = []

        def first(value):
            received.append("first")
            bus.unsubscribe(first)

        def second(value):
            received.append("second")

        bus.subscribe(first)
        bus.subscribe(second)
        bus.emit(1)
        self.assertEqual(received, ["first", "second"])
        bus.emit(2)
        self.assertEqual(received, ["first", "second", "second"])

    def test_order_without_mutation(self):
        bus = Dispatcher()
        seen = []
        bus.subscribe(lambda value: seen.append((1, value)))
        bus.subscribe(lambda value: seen.append((2, value)))
        bus.emit("x")
        self.assertEqual(seen, [(1, "x"), (2, "x")])
