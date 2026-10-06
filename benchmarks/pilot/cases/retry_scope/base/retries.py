class TransientError(Exception):
    pass


def retry_transient(operation, attempts=3):
    for number in range(attempts):
        try:
            return operation()
        except Exception:
            if number + 1 == attempts:
                raise
