import unittest

from routes import cheapest_route


class RouteTests(unittest.TestCase):
    def test_cheaper_detour_beats_direct_edge(self):
        graph = {"a": [("d", 20), ("b", 2)], "b": [("c", 3)], "c": [("d", 4)]}
        self.assertEqual(cheapest_route(graph, "a", "d"), 9)

    def test_later_relaxation_beats_first_discovery(self):
        graph = {"a": [("b", 9), ("c", 1)], "c": [("b", 1)], "b": [("d", 1)]}
        self.assertEqual(cheapest_route(graph, "a", "d"), 3)

    def test_cycle_and_unreachable_destination(self):
        graph = {"a": [("b", 2)], "b": [("a", 1)]}
        self.assertEqual(cheapest_route(graph, "a", "a"), 0)
        self.assertIsNone(cheapest_route(graph, "a", "missing"))
