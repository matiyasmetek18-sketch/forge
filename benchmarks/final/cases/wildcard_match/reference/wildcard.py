def matches(text, pattern):
    reachable = {0}
    for token in pattern:
        if token == "*":
            start = min(reachable, default=len(text) + 1)
            reachable = set(range(start, len(text) + 1))
        else:
            reachable = {
                index + 1 for index in reachable
                if index < len(text) and (token == "?" or token == text[index])
            }
    return len(text) in reachable
