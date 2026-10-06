class Cart:
    def __init__(self, initial=None):
        self._items = list(initial) if initial is not None else []

    def add(self, sku):
        self._items.append(sku)

    def items(self):
        return list(self._items)
