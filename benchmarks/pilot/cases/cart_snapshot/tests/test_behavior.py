import unittest

from cart import Cart


class CartTests(unittest.TestCase):
    def test_constructor_takes_ownership(self):
        initial = ["a"]
        cart = Cart(initial)
        initial.append("b")
        self.assertEqual(cart.items(), ["a"])

    def test_snapshot_is_not_live_state(self):
        cart = Cart(["a"])
        snapshot = cart.items()
        snapshot.append("b")
        self.assertEqual(cart.items(), ["a"])

    def test_add_changes_only_this_cart(self):
        initial = ["a"]
        first = Cart(initial)
        second = Cart(initial)
        first.add("b")
        self.assertEqual(first.items(), ["a", "b"])
        self.assertEqual(second.items(), ["a"])
        self.assertEqual(initial, ["a"])
