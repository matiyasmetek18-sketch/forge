from contextlib import contextmanager


class Settings:
    def __init__(self, values):
        self.values = dict(values)

    @contextmanager
    def override(self, key, value):
        previous = self.values[key]
        self.values[key] = value
        try:
            yield
        finally:
            self.values[key] = previous
