from contextlib import contextmanager


class Settings:
    def __init__(self, values):
        self.values = dict(values)
        self._previous = None

    @contextmanager
    def override(self, key, value):
        self._previous = self.values[key]
        self.values[key] = value
        try:
            yield
        finally:
            self.values[key] = self._previous
