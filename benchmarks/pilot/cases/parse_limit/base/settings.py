def parse_limit(raw, default=20):
    if raw is None:
        return default
    value = int(raw)
    if not 1 <= value <= 100:
        raise ValueError("limit out of range")
    return value
