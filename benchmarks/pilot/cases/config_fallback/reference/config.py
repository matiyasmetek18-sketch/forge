def _port(text):
    value = int(text)
    if not 1 <= value <= 65535:
        raise ValueError("port out of range")
    return value


def load_port(read_setting):
    try:
        primary = read_setting("primary")
    except FileNotFoundError:
        return _port(read_setting("fallback"))
    return _port(primary)
