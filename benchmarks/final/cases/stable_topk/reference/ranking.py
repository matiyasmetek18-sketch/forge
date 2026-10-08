def top_k(records, k):
    if not 0 <= k <= len(records):
        raise ValueError("invalid k")
    indexed = enumerate(records)
    return [record for _, record in sorted(indexed, key=lambda pair: (-pair[1]["score"], pair[0]))[:k]]
