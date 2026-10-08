def resolve_timeout(requested, default=30):
    timeout = requested or default
    if timeout < 0:
        raise ValueError("invalid timeout")
    return timeout
