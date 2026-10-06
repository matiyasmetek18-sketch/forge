def parse_tags(raw):
    if not isinstance(raw, str):
        raise ValueError("tags must be text")
    result = []
    seen = set()
    for part in raw.split(","):
        tag = part.strip().lower()
        if not tag or tag in seen:
            raise ValueError("empty or duplicate tag")
        seen.add(tag)
        result.append(tag)
    return tuple(result)
