def matches(text, pattern):
    if "*" not in pattern:
        return len(text) == len(pattern) and all(p == "?" or p == c for c, p in zip(text, pattern))
    prefix, suffix = pattern.split("*", 1)
    if len(text) < len(prefix) + len(suffix):
        return False
    return matches(text[:len(prefix)], prefix) and matches(text[-len(suffix):] if suffix else "", suffix)
