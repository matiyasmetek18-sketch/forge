def get_or_compute(cache, key, compute):
    if key not in cache:
        value = compute()
        cache[key] = value
    return cache[key]
