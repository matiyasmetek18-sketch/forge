def resolve_timeout(requested, default=30):
    timeout = default if requested is None else requested
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0:
        raise ValueError("invalid timeout")
    return timeout
