def get_header(headers, name):
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    raise KeyError(name)
