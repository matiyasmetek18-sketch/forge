def parse_limit(raw, default=20):
    if raw is None:
        return default
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
        raise ValueError("limit must be ASCII decimal digits")
    value = int(raw)
    if not 1 <= value <= 100:
        raise ValueError("limit out of range")
    return value
