def top_k(records, k):
    if not 0 <= k <= len(records):
        raise ValueError("invalid k")
    return sorted(records, key=lambda record: (record["score"], record["name"]), reverse=True)[:k]
