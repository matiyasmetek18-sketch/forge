def _port(text):
    value = int(text)
    if not 1 <= value <= 65535:
        raise ValueError("port out of range")
    return value


def load_port(read_setting):
    try:
        return _port(read_setting("primary"))
    except (FileNotFoundError, ValueError):
        return _port(read_setting("fallback"))
