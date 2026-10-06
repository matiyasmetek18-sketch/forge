class Dispatcher:
    def __init__(self):
        self._listeners = []

    def subscribe(self, listener):
        self._listeners.append(listener)

    def unsubscribe(self, listener):
        self._listeners.remove(listener)

    def emit(self, value):
        for listener in self._listeners:
            listener(value)
