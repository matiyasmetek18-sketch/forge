def get_or_compute(cache, key, compute):
    if key not in cache:
        cache[key] = None
        cache[key] = compute()
    return cache[key]
