def normalize_key(raw):
    if not isinstance(raw, str) or not raw or "\\" in raw or raw.startswith("/"):
        raise ValueError("invalid key")
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("invalid key")
    return "/".join(parts)
