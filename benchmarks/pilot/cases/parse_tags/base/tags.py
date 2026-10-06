def parse_tags(raw):
    if not isinstance(raw, str):
        raise ValueError("tags must be text")
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())
